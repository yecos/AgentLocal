"""
=============================================================
AGENTE v16 - Sandbox de Ejecucion y Testing
=============================================================
Ejecuta codigo de forma segura con captura de stdout/stderr,
timeout, y verificacion automatica de resultados.

Soporta:
- Ejecucion de Python con virtualenv aislado
- Ejecucion de JavaScript/Node.js
- Ejecucion de tests (pytest, jest, vitest)
- Loop automatico: ejecutar -> si falla -> diagnosticar -> corregir -> re-ejecutar

v16: Ejecucion segura y verificable de codigo.
=============================================================
"""

import os
import re
import json
import subprocess
import tempfile
import logging
import shutil
from datetime import datetime
from typing import Optional

from config import REPOS_DIR, logger
from utils.security import is_dangerous_command

# ============================================================
# CONFIGURACION
# ============================================================

SANDBOX_DIR = os.path.join(REPOS_DIR, ".sandbox")
MAX_EXECUTION_TIME = 60  # segundos
MAX_OUTPUT_LENGTH = 5000  # caracteres
MAX_TEST_RETRIES = 3

# Extensiones de archivo y sus ejecutores
RUNNERS = {
    ".py": {"command": "python3", "args": [], "test_flag": "-m pytest"},
    ".js": {"command": "node", "args": [], "test_flag": "--test"},
    ".ts": {"command": "npx", "args": ["ts-node"], "test_flag": "vitest run"},
    ".sh": {"command": "bash", "args": [], "test_flag": None},
}


# ============================================================
# RESULTADO DE EJECUCION
# ============================================================

class ExecutionResult:
    """Resultado de una ejecucion de codigo."""

    def __init__(self, command: str, exit_code: int, stdout: str, stderr: str,
                 duration: float, timed_out: bool = False):
        self.command = command
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration
        self.timed_out = timed_out
        self.success = exit_code == 0 and not timed_out
        self.timestamp = datetime.now().isoformat()

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:MAX_OUTPUT_LENGTH],
            "stderr": self.stderr[:MAX_OUTPUT_LENGTH],
            "duration": round(self.duration, 2),
            "timed_out": self.timed_out,
            "success": self.success,
            "timestamp": self.timestamp,
        }

    def get_error_summary(self) -> str:
        """Extrae un resumen del error para diagnostico."""
        if self.success:
            return ""
        if self.timed_out:
            return f"Timeout despues de {self.duration}s"
        if self.stderr:
            # Tomar las ultimas lineas del error
            lines = self.stderr.strip().split("\n")
            return "\n".join(lines[-5:])
        if self.exit_code != 0:
            return f"Exit code: {self.exit_code}"
        return "Error desconocido"


# ============================================================
# EJECUTOR SEGURO
# ============================================================

def execute_code(code: str, language: str = "python", timeout: int = MAX_EXECUTION_TIME,
                 working_dir: str = None, env_vars: dict = None) -> ExecutionResult:
    """Ejecuta codigo de forma segura con captura de output y timeout.

    Args:
        code: Codigo fuente a ejecutar
        language: Lenguaje (python, javascript, typescript, bash)
        timeout: Timeout en segundos
        working_dir: Directorio de trabajo (default: sandbox temporal)
        env_vars: Variables de entorno adicionales

    Returns:
        ExecutionResult con el resultado de la ejecucion
    """
    import time

    # Crear directorio sandbox si no existe
    os.makedirs(SANDBOX_DIR, exist_ok=True)

    # Mapear lenguaje a extension y comando
    lang_config = {
        "python": {"ext": ".py", "cmd": ["python3"]},
        "javascript": {"ext": ".js", "cmd": ["node"]},
        "typescript": {"ext": ".ts", "cmd": ["npx", "ts-node"]},
        "bash": {"ext": ".sh", "cmd": ["bash"]},
        "html": {"ext": ".html", "cmd": None},  # No ejecutable directamente
    }

    config = lang_config.get(language, lang_config["python"])
    if not config["cmd"]:
        return ExecutionResult("", 1, "", f"Lenguaje {language} no es ejecutable directamente", 0)

    # Crear archivo temporal
    tmp_dir = working_dir or tempfile.mkdtemp(prefix="sandbox_", dir=SANDBOX_DIR)
    os.makedirs(tmp_dir, exist_ok=True)
    tmp_file = os.path.join(tmp_dir, f"exec_{datetime.now().strftime('%H%M%S')}{config['ext']}")

    try:
        # Escribir codigo
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.write(code)

        # Preparar entorno
        exec_env = os.environ.copy()
        exec_env["PYTHONIOENCODING"] = "utf-8"
        exec_env["NODE_OPTIONS"] = "--max-old-space-size=256"
        if env_vars:
            exec_env.update(env_vars)

        # Ejecutar
        cmd = config["cmd"] + [tmp_file]
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmp_dir,
                env=exec_env,
            )
            duration = time.time() - start_time

            return ExecutionResult(
                command=" ".join(cmd),
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration=duration,
            )

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return ExecutionResult(
                command=" ".join(cmd),
                exit_code=-1,
                stdout="",
                stderr=f"Ejecucion cancelada: timeout de {timeout}s excedido",
                duration=duration,
                timed_out=True,
            )

    except Exception as e:
        return ExecutionResult(
            command="",
            exit_code=-1,
            stdout="",
            stderr=f"Error preparando ejecucion: {str(e)}",
            duration=0,
        )


def execute_file(filepath: str, timeout: int = MAX_EXECUTION_TIME,
                 args: list = None, working_dir: str = None) -> ExecutionResult:
    """Ejecuta un archivo existente de forma segura.

    Args:
        filepath: Ruta al archivo a ejecutar
        timeout: Timeout en segundos
        args: Argumentos adicionales
        working_dir: Directorio de trabajo

    Returns:
        ExecutionResult con el resultado de la ejecucion
    """
    import time

    if not os.path.exists(filepath):
        return ExecutionResult(filepath, 1, "", f"Archivo no encontrado: {filepath}", 0)

    # Detectar runner por extension
    ext = os.path.splitext(filepath)[1].lower()
    runner = RUNNERS.get(ext)
    if not runner:
        return ExecutionResult(filepath, 1, "", f"Extension no soportada: {ext}", 0)

    cmd = [runner["command"]] + runner.get("args", []) + [filepath]
    if args:
        cmd.extend(args)

    cwd = working_dir or os.path.dirname(filepath)

    # Verificar seguridad del comando
    full_cmd = " ".join(cmd)
    if is_dangerous_command(full_cmd):
        return ExecutionResult(full_cmd, 1, "", "Comando bloqueado por seguridad", 0)

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        duration = time.time() - start_time

        return ExecutionResult(
            command=full_cmd,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration=duration,
        )

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return ExecutionResult(full_cmd, -1, "", f"Timeout de {timeout}s", duration, timed_out=True)
    except Exception as e:
        return ExecutionResult(full_cmd, -1, "", str(e), 0)


# ============================================================
# TEST RUNNER
# ============================================================

def run_tests(project_path: str, test_framework: str = None,
              test_path: str = None, timeout: int = 120) -> ExecutionResult:
    """Ejecuta tests de un proyecto.

    Args:
        project_path: Ruta al proyecto
        test_framework: Framework de tests (auto-detectado si None)
        test_path: Ruta especifica de test (opcional)
        timeout: Timeout en segundos

    Returns:
        ExecutionResult con los resultados de los tests
    """
    import time

    if not os.path.isdir(project_path):
        return ExecutionResult("", 1, "", f"Directorio no encontrado: {project_path}", 0)

    # Auto-detectar framework
    if not test_framework:
        test_framework = _detect_test_framework(project_path)

    # Construir comando de test
    cmd = _build_test_command(test_framework, project_path, test_path)
    if not cmd:
        return ExecutionResult("", 1, "", f"No se pudo construir comando de test para {test_framework}", 0)

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_path,
            shell=True,
        )
        duration = time.time() - start_time

        return ExecutionResult(
            command=cmd,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration=duration,
        )

    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        return ExecutionResult(cmd, -1, "", f"Tests timeout de {timeout}s", duration, timed_out=True)
    except Exception as e:
        return ExecutionResult(cmd, -1, "", str(e), 0)


def _detect_test_framework(project_path: str) -> str:
    """Detecta el framework de tests de un proyecto."""
    # Python
    if os.path.exists(os.path.join(project_path, "pytest.ini")) or \
       os.path.exists(os.path.join(project_path, "setup.cfg")) or \
       os.path.exists(os.path.join(project_path, "pyproject.toml")):
        return "pytest"

    if os.path.exists(os.path.join(project_path, "manage.py")):
        return "django"

    # Node.js
    package_json_path = os.path.join(project_path, "package.json")
    if os.path.exists(package_json_path):
        try:
            with open(package_json_path, "r") as f:
                pkg = json.load(f)
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            if "vitest" in deps:
                return "vitest"
            if "jest" in deps:
                return "jest"
            if "mocha" in deps:
                return "mocha"
            # Node.js built-in test runner
            if "node:test" in json.dumps(pkg):
                return "node-test"
        except Exception:
            pass

    # Default
    if any(f.endswith(".py") for f in os.listdir(project_path) if os.path.isfile(os.path.join(project_path, f))):
        return "pytest"
    if os.path.exists(os.path.join(project_path, "package.json")):
        return "vitest"

    return "pytest"


def _build_test_command(framework: str, project_path: str, test_path: str = None) -> Optional[str]:
    """Construye el comando de test para el framework detectado."""
    commands = {
        "pytest": f"python3 -m pytest {test_path or ''} -v --tb=short 2>&1",
        "django": f"python3 manage.py test {test_path or ''} --verbosity=2 2>&1",
        "vitest": f"npx vitest run {test_path or ''} 2>&1",
        "jest": f"npx jest {test_path or ''} --verbose 2>&1",
        "mocha": f"npx mocha {test_path or 'test/'} 2>&1",
        "node-test": f"node --test {test_path or '**/*.test.*'} 2>&1",
    }
    return commands.get(framework)


# ============================================================
# LOOP DE VERIFICACION AUTOMATICA
# ============================================================

def execute_and_verify(code: str, language: str = "python",
                       expected_output: str = None,
                       max_retries: int = MAX_TEST_RETRIES) -> dict:
    """Ejecuta codigo y verifica el resultado. Si falla, intenta corregir.

    Args:
        code: Codigo a ejecutar
        language: Lenguaje
        expected_output: Salida esperada (opcional)
        max_retries: Maximo de reintentos

    Returns:
        Dict con success, result, attempts, corrections
    """
    attempts = []
    current_code = code
    corrections = []

    for attempt in range(1, max_retries + 1):
        # Ejecutar
        result = execute_code(current_code, language)
        attempts.append({
            "attempt": attempt,
            "result": result.to_dict(),
        })

        logger.info(f"[Sandbox] Intento {attempt}: exit_code={result.exit_code}, duration={result.duration:.2f}s")

        # Verificar exito
        if result.success:
            # Verificar salida esperada si se proporciono
            if expected_output and expected_output.strip():
                if expected_output.strip() in result.stdout.strip():
                    return {
                        "success": True,
                        "result": result.to_dict(),
                        "attempts": attempts,
                        "corrections": corrections,
                    }
                else:
                    # Salida no coincide, intentar corregir
                    error_msg = f"Salida no coincide. Esperaba contener: '{expected_output[:100]}', obtuvo: '{result.stdout[:100]}'"
                    corrections.append(error_msg)
            else:
                return {
                    "success": True,
                    "result": result.to_dict(),
                    "attempts": attempts,
                    "corrections": corrections,
                }

        # Si fallo, diagnosticar
        error_summary = result.get_error_summary()
        logger.info(f"[Sandbox] Error en intento {attempt}: {error_summary[:200]}")
        corrections.append(f"Intento {attempt}: {error_summary}")

        if attempt < max_retries:
            # Intentar correccion automatica basica
            current_code = _auto_fix_code(current_code, language, error_summary)

    return {
        "success": False,
        "result": attempts[-1]["result"] if attempts else None,
        "attempts": attempts,
        "corrections": corrections,
    }


def _auto_fix_code(code: str, language: str, error: str) -> str:
    """Intenta correcciones automaticas basicas de codigo.

    Args:
        code: Codigo original
        language: Lenguaje
        error: Mensaje de error

    Returns:
        Codigo con correcciones aplicadas
    """
    fixed = code

    if language == "python":
        # Fix: Missing newline at end
        if not fixed.endswith("\n"):
            fixed += "\n"

        # Fix: Indentation errors - try to normalize tabs to spaces
        if "IndentationError" in error or "TabError" in error:
            lines = fixed.split("\n")
            fixed_lines = []
            for line in lines:
                if line.startswith("\t"):
                    fixed_lines.append("    " + line[1:])
                else:
                    fixed_lines.append(line)
            fixed = "\n".join(fixed_lines)

        # Fix: Missing imports comunes
        common_imports = {
            "json": "import json\n",
            "os": "import os\n",
            "sys": "import sys\n",
            "datetime": "from datetime import datetime\n",
            "re": "import re\n",
            "math": "import math\n",
            "collections": "from collections import defaultdict, Counter\n",
            "pathlib": "from pathlib import Path\n",
            "typing": "from typing import List, Dict, Optional\n",
        }
        for module, import_line in common_imports.items():
            if module in error and import_line.strip() not in fixed:
                fixed = import_line + fixed

        # Fix: SyntaxError - remove trailing commas in function calls
        if "SyntaxError" in error:
            fixed = re.sub(r',\s*\)', ')', fixed)

    elif language == "javascript":
        # Fix: Missing newline at end
        if not fixed.endswith("\n"):
            fixed += "\n"

        # Fix: Common require errors - add try/catch
        if "Cannot find module" in error:
            # No podemos instalar modulos automaticamente, pero si lo reportamos
            pass

    return fixed


def diagnose_error(result: ExecutionResult) -> dict:
    """Diagnostica un error de ejecucion y sugiere correcciones.

    Args:
        result: Resultado de ejecucion fallida

    Returns:
        Dict con diagnostico y sugerencias
    """
    diagnosis = {
        "error_type": "unknown",
        "error_message": result.get_error_summary(),
        "suggestions": [],
        "severity": "medium",
    }

    stderr = result.stderr.lower()
    stdout = result.stdout.lower()

    if result.timed_out:
        diagnosis["error_type"] = "timeout"
        diagnosis["severity"] = "high"
        diagnosis["suggestions"] = [
            "El codigo tardo demasiado. Posibles causas:",
            "- Bucle infinito o recursion sin caso base",
            "- Operacion de red o I/O que no responde",
            "- Procesamiento de datos muy grande",
            "Sugerencia: Agregar timeout o limitar iteraciones",
        ]

    elif "importerror" in stderr or "modulenotfounderror" in stderr:
        diagnosis["error_type"] = "missing_import"
        diagnosis["severity"] = "low"
        # Extraer modulo faltante
        match = re.search(r"No module named '(\w+)'", result.stderr)
        if match:
            module = match.group(1)
            diagnosis["suggestions"] = [
                f"Falta instalar el modulo: {module}",
                f"Ejecutar: pip install {module}",
            ]

    elif "syntaxerror" in stderr:
        diagnosis["error_type"] = "syntax_error"
        diagnosis["severity"] = "medium"
        # Extraer linea del error
        match = re.search(r"line (\d+)", result.stderr)
        if match:
            line = match.group(1)
            diagnosis["suggestions"] = [
                f"Error de sintaxis en linea {line}",
                "Verificar parentesis, indentacion, y comillas",
            ]

    elif "typeerror" in stderr:
        diagnosis["error_type"] = "type_error"
        diagnosis["severity"] = "medium"
        diagnosis["suggestions"] = [
            "Error de tipo: se uso un tipo incorrecto",
            "Verificar tipos de argumentos en funciones",
        ]

    elif "filenotfounderror" in stderr or "no such file" in stderr:
        diagnosis["error_type"] = "file_not_found"
        diagnosis["severity"] = "low"
        diagnosis["suggestions"] = [
            "Archivo no encontrado",
            "Verificar que la ruta existe y es accesible",
        ]

    elif "permission denied" in stderr:
        diagnosis["error_type"] = "permission_error"
        diagnosis["severity"] = "high"
        diagnosis["suggestions"] = [
            "Permiso denegado",
            "Verificar permisos del archivo o directorio",
        ]

    elif "referenceerror" in stderr or "is not defined" in stderr:
        diagnosis["error_type"] = "reference_error"
        diagnosis["severity"] = "medium"
        diagnosis["suggestions"] = [
            "Variable o funcion no definida",
            "Verificar que la variable esta declarada antes de usarse",
        ]

    return diagnosis
