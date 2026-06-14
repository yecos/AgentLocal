"""
=============================================================
AGENTE v16 - Error Recovery Chain
=============================================================
Sistema de recuperacion automatica de errores.
Cuando una herramienta falla, diagnostica la causa raiz,
propone alternativas, y ejecuta la correccion.

Flujo:
1. Error detectado → Diagnosticar
2. Clasificar error (timeout, permisos, dependencia, sintaxis, etc.)
3. Generar correccion automatica si es posible
4. Si no, proponer alternativa al agente
5. Ejecutar correccion y verificar resultado
6. Si sigue fallando, escalar

v16: Auto-curacion del agente.
=============================================================
"""

import os
import re
import json
import logging
from datetime import datetime
from typing import Optional
from enum import Enum

from config import LEARN_DIR, logger

# ============================================================
# CLASIFICACION DE ERRORES
# ============================================================

class ErrorType(str, Enum):
    TIMEOUT = "timeout"
    PERMISSION = "permission"
    NOT_FOUND = "not_found"
    SYNTAX = "syntax"
    DEPENDENCY = "dependency"
    NETWORK = "network"
    RUNTIME = "runtime"
    CONFIGURATION = "configuration"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


class ErrorSeverity(str, Enum):
    LOW = "low"          # Auto-reparable
    MEDIUM = "medium"    # Requiere intento alternativo
    HIGH = "high"        # Requiere intervencion del usuario
    CRITICAL = "critical"  # No recuperable sin ayuda


# ============================================================
# DIAGNOSTICO
# ============================================================

class ErrorDiagnostic:
    """Diagnostica errores y genera planes de recuperacion."""

    # Patrones de error y sus clasificaciones
    ERROR_PATTERNS = [
        # Timeout
        (r"timeout|timed?\s*out|TimeoutExpired", ErrorType.TIMEOUT, ErrorSeverity.MEDIUM),
        (r"took too long|exceeded.*time", ErrorType.TIMEOUT, ErrorSeverity.MEDIUM),

        # Permisos
        (r"permission denied|access denied|EACCES|EPERM", ErrorType.PERMISSION, ErrorSeverity.HIGH),
        (r"not authorized|forbidden|403", ErrorType.PERMISSION, ErrorSeverity.HIGH),

        # No encontrado
        (r"no such file|not found|FileNotFoundError|ENOENT", ErrorType.NOT_FOUND, ErrorSeverity.LOW),
        (r"module not found|cannot find module|ImportError", ErrorType.DEPENDENCY, ErrorSeverity.LOW),
        (r"command not found|is not recognized", ErrorType.DEPENDENCY, ErrorSeverity.LOW),

        # Sintaxis
        (r"SyntaxError|syntax error|unexpected token", ErrorType.SYNTAX, ErrorSeverity.LOW),
        (r"IndentationError|TabError", ErrorType.SYNTAX, ErrorSeverity.LOW),
        (r"unexpected.*keyword|invalid.*argument", ErrorType.SYNTAX, ErrorSeverity.LOW),

        # Red
        (r"connection refused|ECONNREFUSED|ConnectionError", ErrorType.NETWORK, ErrorSeverity.MEDIUM),
        (r"connection reset|ECONNRESET", ErrorType.NETWORK, ErrorSeverity.MEDIUM),
        (r"name resolution|DNS|ENOTFOUND", ErrorType.NETWORK, ErrorSeverity.MEDIUM),
        (r"CORS|cross-origin", ErrorType.NETWORK, ErrorSeverity.LOW),

        # Runtime
        (r"TypeError|type error|null pointer|NoneType", ErrorType.RUNTIME, ErrorSeverity.MEDIUM),
        (r"ValueError|value error|invalid value", ErrorType.RUNTIME, ErrorSeverity.LOW),
        (r"IndexError|index out of range|KeyError", ErrorType.RUNTIME, ErrorSeverity.LOW),
        (r"ReferenceError|is not defined|UnboundLocalError", ErrorType.RUNTIME, ErrorSeverity.LOW),

        # Configuracion
        (r"config|configuration|env|environment variable", ErrorType.CONFIGURATION, ErrorSeverity.MEDIUM),
        (r"missing.*setting|invalid.*config", ErrorType.CONFIGURATION, ErrorSeverity.MEDIUM),

        # Recursos
        (r"out of memory|OOM|Cannot allocate", ErrorType.RESOURCE, ErrorSeverity.HIGH),
        (r"disk full|no space left|ENOSPC", ErrorType.RESOURCE, ErrorSeverity.HIGH),
    ]

    # Estrategias de recuperacion por tipo de error
    RECOVERY_STRATEGIES = {
        ErrorType.TIMEOUT: [
            "Reintentar con timeout mayor",
            "Dividir la tarea en pasos mas pequenos",
            "Usar un modelo mas rapido",
            "Verificar que no haya un bucle infinito",
        ],
        ErrorType.PERMISSION: [
            "Verificar permisos del archivo/directorio",
            "Intentar con chmod/chown si es seguro",
            "Usar un directorio alternativo",
            "Solicitar permisos al usuario",
        ],
        ErrorType.NOT_FOUND: [
            "Verificar que la ruta existe",
            "Buscar el archivo en otras ubicaciones",
            "Crear el archivo si es seguro",
            "Instalar el componente faltante",
        ],
        ErrorType.SYNTAX: [
            "Verificar sintaxis del codigo/comando",
            "Corregir indentacion",
            "Verificar comillas y parentesis",
            "Usar un linter para detectar errores",
        ],
        ErrorType.DEPENDENCY: [
            "Instalar la dependencia faltante (pip/npm)",
            "Verificar version de la dependencia",
            "Buscar alternativa a la dependencia",
            "Actualizar requirements.txt o package.json",
        ],
        ErrorType.NETWORK: [
            "Verificar conexion a internet",
            "Reintentar en unos segundos",
            "Verificar que el servicio este corriendo",
            "Usar una URL o endpoint alternativo",
        ],
        ErrorType.RUNTIME: [
            "Verificar tipos de datos",
            "Agregar validacion de entrada",
            "Manejar valores nulos/vacios",
            "Agregar try/except",
        ],
        ErrorType.CONFIGURATION: [
            "Verificar archivo de configuracion",
            "Crear .env si no existe",
            "Usar valores por defecto",
            "Documentar variables necesarias",
        ],
        ErrorType.RESOURCE: [
            "Liberar memoria cerrando procesos",
            "Procesar datos en lotes mas pequenos",
            "Limpiar archivos temporales",
            "Reiniciar el servicio",
        ],
    }

    def diagnose(self, error_message: str, tool_name: str = "",
                 context: dict = None) -> dict:
        """Diagnostica un error y genera plan de recuperacion.

        Args:
            error_message: Mensaje de error
            tool_name: Herramienta que fallo
            context: Contexto adicional (comando, parametros, etc.)

        Returns:
            Dict con error_type, severity, root_cause, recovery_steps, auto_fixable
        """
        error_lower = error_message.lower()

        # Clasificar error
        error_type = ErrorType.UNKNOWN
        severity = ErrorSeverity.MEDIUM

        for pattern, etype, eseverity in self.ERROR_PATTERNS:
            if re.search(pattern, error_lower, re.IGNORECASE):
                error_type = etype
                severity = eseverity
                break

        # Extraer causa raiz
        root_cause = self._extract_root_cause(error_message, error_type)

        # Generar pasos de recuperacion
        recovery_steps = self.RECOVERY_STRATEGIES.get(error_type, [
            "Reintentar la operacion",
            "Buscar en internet como resolver este error",
            "Proponer alternativa al usuario",
        ])

        # Determinar si es auto-reparable
        auto_fixable = severity in (ErrorSeverity.LOW, ErrorSeverity.MEDIUM) and \
                       error_type in (
                           ErrorType.TIMEOUT, ErrorType.SYNTAX,
                           ErrorType.NOT_FOUND, ErrorType.DEPENDENCY,
                           ErrorType.RUNTIME,
                       )

        # Generar correccion automatica si es posible
        auto_fix = None
        if auto_fixable:
            auto_fix = self._generate_auto_fix(error_type, error_message, context)

        diagnosis = {
            "error_type": error_type.value,
            "severity": severity.value,
            "root_cause": root_cause,
            "recovery_steps": recovery_steps,
            "auto_fixable": auto_fixable,
            "auto_fix": auto_fix,
            "tool": tool_name,
            "original_error": error_message[:500],
            "timestamp": datetime.now().isoformat(),
        }

        logger.info(
            f"[ErrorRecovery] Diagnostico: {error_type.value} ({severity.value}) "
            f"en {tool_name}: {root_cause[:100]}"
        )

        return diagnosis

    def _extract_root_cause(self, error: str, error_type: ErrorType) -> str:
        """Extrae la causa raiz del mensaje de error."""
        # Para errores comunes, extraer informacion clave
        if error_type == ErrorType.DEPENDENCY:
            match = re.search(r"No module named ['\"]?(\w+)['\"]?", error)
            if match:
                return f"Modulo faltante: {match.group(1)}"
            match = re.search(r"cannot find module ['\"]?(\S+)['\"]?", error, re.IGNORECASE)
            if match:
                return f"Modulo faltante: {match.group(1)}"

        if error_type == ErrorType.NOT_FOUND:
            match = re.search(r"No such file.*?:\s*['\"]?(\S+)['\"]?", error)
            if match:
                return f"Archivo no encontrado: {match.group(1)}"

        if error_type == ErrorType.SYNTAX:
            match = re.search(r"line (\d+)", error)
            if match:
                return f"Error de sintaxis en linea {match.group(1)}"

        # Fallback: primeras 200 chars del error
        return error[:200].strip()

    def _generate_auto_fix(self, error_type: ErrorType, error: str,
                           context: dict = None) -> Optional[dict]:
        """Genera una correccion automatica si es posible.

        Returns:
            Dict con fix_type, action, params o None
        """
        context = context or {}

        if error_type == ErrorType.DEPENDENCY:
            # Detectar modulo faltante y generar comando de instalacion
            match = re.search(r"No module named ['\"]?(\w+)['\"]?", error)
            if match:
                module = match.group(1)
                return {
                    "fix_type": "install_dependency",
                    "action": "ejecutar_comando",
                    "params": {"comando": f"pip install {module}"},
                    "description": f"Instalar modulo {module}",
                }

            match = re.search(r"cannot find module ['\"]?(\S+)['\"]?", error, re.IGNORECASE)
            if match:
                module = match.group(1)
                return {
                    "fix_type": "install_dependency",
                    "action": "ejecutar_comando",
                    "params": {"comando": f"npm install {module}"},
                    "description": f"Instalar modulo {module}",
                }

        elif error_type == ErrorType.NOT_FOUND:
            # Si el contexto incluye el path, intentar crear
            filepath = context.get("filepath", "")
            if filepath:
                return {
                    "fix_type": "create_file",
                    "action": "escribir_archivo",
                    "params": {"ruta": filepath, "contenido": ""},
                    "description": f"Crear archivo {filepath}",
                }

        elif error_type == ErrorType.SYNTAX:
            return {
                "fix_type": "lint_fix",
                "action": "ejecutar_comando",
                "params": {"comando": context.get("lint_command", "")},
                "description": "Ejecutar linter para corregir sintaxis",
            }

        elif error_type == ErrorType.TIMEOUT:
            return {
                "fix_type": "increase_timeout",
                "action": "retry_with_params",
                "params": {"timeout": 180},
                "description": "Reintentar con timeout mayor (180s)",
            }

        return None


# ============================================================
# ERROR HISTORY
# ============================================================

class ErrorHistory:
    """Mantiene historial de errores para aprendizaje."""

    def __init__(self):
        self._history_file = os.path.join(LEARN_DIR, "error_history.json")
        self._history: list[dict] = []
        self._load()

    def record(self, diagnosis: dict, fix_applied: str = None,
               fix_success: bool = None):
        """Registra un error y su correccion."""
        entry = {
            **diagnosis,
            "fix_applied": fix_applied,
            "fix_success": fix_success,
        }
        self._history.append(entry)

        # Mantener solo los ultimos 100 errores
        if len(self._history) > 100:
            self._history = self._history[-100:]

        self._save()

    def get_similar_errors(self, error_type: str, tool_name: str = "") -> list[dict]:
        """Busca errores similares en el historial."""
        similar = []
        for entry in self._history[-50:]:
            if entry.get("error_type") == error_type:
                if not tool_name or entry.get("tool") == tool_name:
                    similar.append(entry)
        return similar

    def get_successful_fixes(self, error_type: str) -> list[dict]:
        """Busca correcciones exitosas para un tipo de error."""
        return [
            e for e in self._history[-50:]
            if e.get("error_type") == error_type and e.get("fix_success") is True
        ]

    def _load(self):
        """Carga historial desde disco."""
        try:
            if os.path.exists(self._history_file):
                with open(self._history_file, "r", encoding="utf-8") as f:
                    self._history = json.load(f)
        except Exception:
            self._history = []

    def _save(self):
        """Guarda historial a disco."""
        try:
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump(self._history[-100:], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[ErrorHistory] Error guardando: {e}")


# ============================================================
# INSTANCIAS SINGLETON
# ============================================================

_diagnostic = ErrorDiagnostic()
_error_history = ErrorHistory()


def diagnose_error(error_message: str, tool_name: str = "",
                   context: dict = None) -> dict:
    """Diagnostica un error y sugiere correcciones.

    Args:
        error_message: Mensaje de error
        tool_name: Herramienta que fallo
        context: Contexto adicional

    Returns:
        Dict con diagnostico completo
    """
    return _diagnostic.diagnose(error_message, tool_name, context)


def record_error_fix(diagnosis: dict, fix_applied: str, fix_success: bool):
    """Registra una correccion de error para aprendizaje futuro."""
    _error_history.record(diagnosis, fix_applied, fix_success)


def get_error_history() -> ErrorHistory:
    """Retorna la instancia del historial de errores."""
    return _error_history
