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
import shlex
import subprocess
import tempfile
import logging
import shutil
from datetime import datetime
from typing import Optional

from config import REPOS_DIR, logger
from utils.security import is_dangerous_command, is_dangerous_python

# ============================================================
# CONFIGURACION
# ============================================================

SANDBOX_DIR = os.path.join(REPOS_DIR, ".sandbox")
MAX_EXECUTION_TIME = 60  # segundos
MAX_OUTPUT_LENGTH = 5000  # caracteres
MAX_TEST_RETRIES = 3

# SECURITY: Limites del sandbox para ejecucion de codigo
SANDBOX_MAX_MEMORY_MB = 256  # Memoria maxima en MB (rlimit)
SANDBOX_MAX_CPU_SECONDS = 30  # CPU time maximo en segundos
SANDBOX_MAX_PROCESSES = 5     # Maximo de subprocesos
SANDBOX_MAX_FILE_SIZE_MB = 10 # Tamano maximo de archivo que puede crear

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

    # SECURITY: Verificar codigo peligroso antes de ejecutar
    if language == "python":
        is_danger, reason = is_dangerous_python(code)
        if is_danger:
            return ExecutionResult(
                command="", exit_code=-1, stdout="",
                stderr=f"Codigo bloqueado por seguridad: {reason}",
                duration=0
            )

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
        # SECURITY: Restringir acceso a red y filesystem en Python
        if language == "python":
            exec_env["PYTHONPATH"] = tmp_dir  # Solo importar desde sandbox
        if env_vars:
            exec_env.update(env_vars)

        # SECURITY: Para Python, agregar wrapper de sandbox con rlimits
        if language == "python":
            sandbox_wrapper = _build_sandbox_wrapper(tmp_file, tmp_dir)
            cmd = ["python3", sandbox_wrapper]
        else:
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
            shlex.split(cmd),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_path,
            stderr=subprocess.STDOUT,
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
        "pytest": f"python3 -m pytest {test_path or ''} -v --tb=short",
        "django": f"python3 manage.py test {test_path or ''} --verbosity=2",
        "vitest": f"npx vitest run {test_path or ''}",
        "jest": f"npx jest {test_path or ''} --verbose",
        "mocha": f"npx mocha {test_path or 'test/'}",
        "node-test": f"node --test {test_path or '**/*.test.*'}",
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


# ============================================================
# SANDBOX: Wrapper con rlimits para ejecucion segura
# ============================================================

def _build_sandbox_wrapper(target_script: str, sandbox_dir: str) -> str:
    """Crea un script wrapper que aplica rlimits antes de ejecutar el codigo del usuario.
    
    SECURITY: El wrapper se ejecuta como proceso separado con:
    - resource.RLIMIT_AS: Limita memoria virtual
    - resource.RLIMIT_CPU: Limita tiempo de CPU
    - resource.RLIMIT_NPROC: Limita numero de subprocesos
    - resource.RLIMIT_FSIZE: Limita tamano de archivos creados
    - sys.path restringido al sandbox
    """
    wrapper_code = '''#!/usr/bin/env python3
"""Sandbox wrapper - aplica rlimits antes de ejecutar codigo de usuario."""
import sys
import os
import resource

# Aplicar rlimits
try:
    # Memoria virtual maxima
    resource.setrlimit(resource.RLIMIT_AS, (
        {max_memory} * 1024 * 1024,  # soft limit
        {max_memory} * 1024 * 1024   # hard limit
    ))
except (ValueError, resource.error):
    pass

try:
    # Tiempo de CPU maximo
    resource.setrlimit(resource.RLIMIT_CPU, (
        {max_cpu},  # soft limit (segundos)
        {max_cpu} + 5  # hard limit
    ))
except (ValueError, resource.error):
    pass

try:
    # Maximo de subprocesos
    resource.setrlimit(resource.RLIMIT_NPROC, (
        {max_procs},  # soft limit
        {max_procs}   # hard limit
    ))
except (ValueError, resource.error):
    pass

try:
    # Tamano maximo de archivo creado
    resource.setrlimit(resource.RLIMIT_FSIZE, (
        {max_file_size} * 1024 * 1024,  # soft limit
        {max_file_size} * 1024 * 1024   # hard limit
    ))
except (ValueError, resource.error):
    pass

# Restringir sys.path al sandbox
sandbox_dir = {sandbox_dir!r}
sys.path = [sandbox_dir, os.path.dirname(os.path.abspath(__file__))]

# Ejecutar el script objetivo
target = {target!r}
if os.path.exists(target):
    # Leer y compilar el codigo para evitar importaciones posteriores
    with open(target, 'r', encoding='utf-8') as f:
        code = f.read()
    
    # Restringir builtins peligrosos
    import builtins
    _original_import = builtins.__import__
    
    _BLOCKED_MODULES = {{'os', 'subprocess', 'shutil', 'ctypes', 'socket',
                         'http', 'pickle', 'marshal', 'code', 'codeop',
                         'multiprocessing', 'signal', 'resource'}}
    
    def _restricted_import(name, *args, **kwargs):
        top_level = name.split('.')[0]
        if top_level in _BLOCKED_MODULES:
            raise ImportError(f"Modulo '{{name}}' bloqueado por sandbox de seguridad")
        return _original_import(name, *args, **kwargs)
    
    builtins.__import__ = _restricted_import
    
    try:
        exec(compile(code, target, 'exec'), {{"__name__": "__main__", "__file__": target}})
    except ImportError as e:
        print(f"SANDBOX: {{e}}", file=sys.stderr)
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"ERROR: {{type(e).__name__}}: {{e}}", file=sys.stderr)
        sys.exit(1)
else:
    print(f"ERROR: Script no encontrado: {{target}}", file=sys.stderr)
    sys.exit(1)
'''.format(
        max_memory=SANDBOX_MAX_MEMORY_MB,
        max_cpu=SANDBOX_MAX_CPU_SECONDS,
        max_procs=SANDBOX_MAX_PROCESSES,
        max_file_size=SANDBOX_MAX_FILE_SIZE_MB,
        sandbox_dir=sandbox_dir,
        target=target_script,
    )
    
    wrapper_path = os.path.join(sandbox_dir, "_sandbox_wrapper.py")
    with open(wrapper_path, "w", encoding="utf-8") as f:
        f.write(wrapper_code)
    
    return wrapper_path


# ============================================================
# CODE REVIEW
# ============================================================

def review_code(ruta: str, lenguaje: str = "python", profundidad: str = "normal") -> str:
    """Revisa codigo y sugiere mejoras. Ejecuta linters si estan disponibles y usa LLM para analisis semantico.

    Args:
        ruta: Ruta al archivo de codigo a revisar
        lenguaje: Lenguaje de programacion (python, javascript, typescript)
        profundidad: Nivel de detalle: rapido, normal, profundo
    """
    if not os.path.exists(ruta):
        return f"ERROR: Archivo no encontrado: {ruta}"

    # Read file content
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            code_content = f.read()
    except Exception as e:
        return f"ERROR leyendo archivo: {e}"

    if not code_content.strip():
        return "El archivo esta vacio. No hay nada que revisar."

    lines_count = code_content.count("\n") + 1

    results = {
        "file": ruta,
        "language": lenguaje,
        "lines": lines_count,
        "depth": profundidad,
        "linter_results": None,
        "llm_results": None,
        "issues": [],
    }

    # 1. Run linter
    linter_output = _run_linter(ruta, lenguaje)
    if linter_output:
        results["linter_results"] = linter_output
        linter_issues = _parse_linter_output(linter_output, lenguaje)
        results["issues"].extend(linter_issues)

    # 2. LLM analysis for semantic issues
    llm_review = _llm_code_review(code_content, lenguaje, profundidad)
    if llm_review:
        results["llm_results"] = llm_review

    # 3. Format output
    return _format_review_output(results)


def _run_linter(ruta: str, lenguaje: str) -> str:
    """Ejecuta el linter apropiado para el lenguaje."""
    try:
        if lenguaje in ("python", "py"):
            # Try flake8 first (faster), then pylint
            for linter_cmd in [
                ["python3", "-m", "flake8", "--max-line-length=120", "--disable=noqa", ruta],
                ["python3", "-m", "pylint", "--output-format=text", "--score=n", ruta],
            ]:
                try:
                    result = subprocess.run(
                        linter_cmd,
                        capture_output=True, text=True, timeout=30,
                    )
                    if result.stdout.strip():
                        return result.stdout.strip()
                except (FileNotFoundError, subprocess.TimeoutExpired):
                    continue
            return ""

        elif lenguaje in ("javascript", "js", "typescript", "ts"):
            try:
                result = subprocess.run(
                    ["npx", "eslint", "--format", "compact", ruta],
                    capture_output=True, text=True, timeout=30,
                )
                return result.stdout.strip() or result.stderr.strip()
            except (FileNotFoundError, subprocess.TimeoutExpired):
                return ""

        return ""
    except Exception as e:
        logger.debug(f"Error ejecutando linter: {e}")
        return ""


def _parse_linter_output(output: str, lenguaje: str) -> list:
    """Parsea la salida del linter en una lista de issues estructurados."""
    issues = []
    for line in output.split("\n")[:30]:  # Limitar a 30 issues
        line = line.strip()
        if not line:
            continue

        # Detect severity
        severity = "info"
        line_lower = line.lower()
        if any(kw in line_lower for kw in ["error", "fatal", "critical"]):
            severity = "high"
        elif any(kw in line_lower for kw in ["warning", "warn"]):
            severity = "medium"
        elif any(kw in line_lower for kw in ["convention", "refactor", "info", "style"]):
            severity = "low"

        issues.append({
            "source": "linter",
            "severity": severity,
            "message": line[:200],
        })

    return issues


def _llm_code_review(code: str, lenguaje: str, profundidad: str) -> str:
    """Usa el LLM para analizar codigo semanticamente."""
    try:
        from llm import ollama

        depth_prompts = {
            "rapido": "Haz una revision rapida. Identifica solo bugs criticos y problemas de seguridad obvios.",
            "normal": "Revisa el codigo buscando bugs, problemas de seguridad, problemas de estilo y oportunidades de optimizacion.",
            "profundo": "Haz una revision exhaustiva. Analiza bugs, seguridad, rendimiento, mantenibilidad, patrones de diseno, manejo de errores, y mejores practicas.",
        }

        review_prompt = depth_prompts.get(profundidad, depth_prompts["normal"])

        # Truncate very long files
        if len(code) > 6000:
            code = code[:3000] + "\n... (truncado) ...\n" + code[-3000:]

        prompt = (
            f"Eres un revisor de codigo experto. {review_prompt}\n\n"
            f"Lenguaje: {lenguaje}\n\n"
            f"Codigo a revisar:\n```\n{code}\n```\n\n"
            "Formato de respuesta:\n"
            "Para cada issue encontrado, usa este formato:\n"
            "[SEVERIDAD] tipo: descripcion\n"
            "Severidades: CRITICAL, HIGH, MEDIUM, LOW, INFO\n"
            "Tipos: bug, security, style, performance, maintainability, best-practice\n\n"
            "Al final, agrega un resumen con el numero total de issues por severidad "
            "y una puntuacion general del 1 al 10."
        )

        messages = [{"role": "user", "content": prompt}]
        response = ollama.generate_chat(messages)

        return str(response).strip() if response else ""

    except Exception as e:
        logger.debug(f"Error en LLM code review: {e}")
        return ""


def _format_review_output(results: dict) -> str:
    """Formatea los resultados de la revision como texto legible."""
    output_parts = [
        f"REVISION DE CODIGO: {results['file']}",
        f"Lenguaje: {results['language']} | Lineas: {results['lines']} | Profundidad: {results['depth']}",
        "=" * 60,
    ]

    # Linter results
    if results["linter_results"]:
        output_parts.append("")
        output_parts.append("LINTER:")
        for line in results["linter_results"].split("\n")[:20]:
            output_parts.append(f"  {line}")
    else:
        output_parts.append("")
        output_parts.append("LINTER: No disponible o sin hallazgos")

    # LLM results
    if results["llm_results"]:
        output_parts.append("")
        output_parts.append("ANALISIS SEMANTICO (LLM):")
        for line in results["llm_results"].split("\n"):
            output_parts.append(f"  {line}")

    # Summary of issues from linter
    if results["issues"]:
        output_parts.append("")
        output_parts.append("RESUMEN DE ISSUES DEL LINTER:")
        by_severity = {"high": 0, "medium": 0, "low": 0, "info": 0}
        for issue in results["issues"]:
            sev = issue.get("severity", "info")
            by_severity[sev] = by_severity.get(sev, 0) + 1
        output_parts.append(f"  HIGH: {by_severity.get('high', 0)} | MEDIUM: {by_severity.get('medium', 0)} | LOW: {by_severity.get('low', 0)} | INFO: {by_severity.get('info', 0)}")

    return "\n".join(output_parts)
