"""
security.py - Seguridad: validacion de paths, sanitizacion, comandos peligrosos
Extraido de app_auto_pro.py lineas 88-194
"""
import re
import logging
from pathlib import Path
from .config import REPOS_DIR, LEARN_DIR, COMANDOS_PELIGROSOS, STRIP_PREFIXES

logger = logging.getLogger("agente.security")


def strip_prefixes(text: str) -> str:
    """Elimina prefijos comunes de comandos de voz/texto."""
    text = text.strip()
    for prefix in STRIP_PREFIXES:
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    return text.strip()


def validate_path(ruta: str) -> str:
    """Valida que una ruta este dentro de directorios permitidos.
    Previene path traversal attacks."""
    allowed_dirs = [REPOS_DIR, LEARN_DIR]
    try:
        resolved = Path(ruta).resolve()
        for allowed in allowed_dirs:
            if str(resolved).startswith(str(Path(allowed).resolve())):
                return ruta  # Ruta segura
        # Tambien permitir rutas relativas dentro de REPOS_DIR
        if not os.path.isabs(ruta):
            resolved_in_repos = Path(os.path.join(REPOS_DIR, ruta)).resolve()
            if str(resolved_in_repos).startswith(str(Path(REPOS_DIR).resolve())):
                return ruta
    except (OSError, ValueError):
        pass
    return (f"ACCESO DENEGADO: La ruta '{ruta}' esta fuera de los "
            f"directorios permitidos. Solo puedes acceder a archivos dentro de {REPOS_DIR}")


def sanitize_input(text: str) -> str:
    """Sanitiza un input para prevenir inyeccion de comandos."""
    if not re.match(r'^[a-zA-Z0-9\s\.\-_:/\\@]+$', text):
        text = re.sub(r'[`$\{\}();|&<>!#~]', '', text)
    return text


def is_dangerous_command(comando: str) -> tuple:
    """Verifica si un comando es peligroso. Retorna (es_peligroso, comando_detectado)."""
    cmd_lower = comando.lower()
    for peligro in COMANDOS_PELIGROSOS:
        if peligro in cmd_lower:
            return True, peligro
    return False, ""


# Import necesario para validate_path
import os
