"""
=============================================================
AGENTE v14 - Seguridad
=============================================================
Validacion de comandos peligrosos, path traversal, sanitizacion.
=============================================================
"""

import re
import os
import logging
from pathlib import Path

from config import REPOS_DIR, LEARN_DIR, logger

# Comandos que NUNCA se ejecutan sin confirmacion
COMANDOS_PELIGROSOS = [
    "rm -rf", "del /f /s /q", "format", "fdisk",
    "reg delete", "net user", "shutdown", "rmdir /s /q",
    "mkfs", "dd if=", "> /dev/sd", "curl | bash", "curl | sh",
    "rd /s /q", "taskkill /f /pid system",
    "powershell -enc", "certutil", "bitsadmin", "mshta",
    "cipher /w", "diskpart", "reg add",
    # Nuevos: ransomware/exfiltration patterns
    "icacls /grant everyone", "net share c",
    "vssadmin delete", "wbadmin delete",
    "bcdedit /delete", "bootrec /fixmbr",
]

# Comandos permitidos sin confirmacion (allowlist)
COMANDOS_SEGUROS = [
    "git", "npm", "pip", "python", "node", "dir", "ls",
    "cat", "echo", "cd", "type", "find", "where", "which",
    "tasklist", "start", "open", "xdg-open",
    "pipenv", "poetry", "bun", "yarn", "cargo",
    "docker ps", "docker images", "docker compose",
    # Nuevos: herramientas de desarrollo comunes
    "ollama", "code", "nvim", "vim",
    "pytest", "jest", "vitest",
    "uvicorn", "flask", "gunicorn",
    "npx", "pnpm",
]


def is_dangerous_command(comando: str) -> bool:
    """Verifica si un comando es peligroso. 
    Comandos en la allowlist (COMANDOS_SEGUROS) nunca son peligrosos."""
    cmd_lower = comando.lower().strip()
    
    # 1. Si empieza con un comando seguro, NO es peligroso
    for seguro in COMANDOS_SEGUROS:
        if cmd_lower.startswith(seguro):
            return False
    
    # 2. Verificar contra lista de peligrosos
    for peligro in COMANDOS_PELIGROSOS:
        if peligro in cmd_lower:
            return True
    
    # 3. Detectar patrones sospechosos por regex
    sospechosos = [
        r';\s*rm\b',           # ; rm (encadenado)
        r'&&\s*rm\b',          # && rm
        r'\|\s*sh\b',          # | sh
        r'\|\s*bash\b',        # | bash
        r'>\s*/etc/',          # > /etc/
        r'>\s*/dev/',          # > /dev/ (excepto null)
        r'chmod\s+777',        # chmod 777
        r'chown\s+root',       # chown root
        r'sudo\s+rm\b',        # sudo rm
        r'sudo\s+dd\b',        # sudo dd
        # Nuevos: patrones de inyeccion avanzados
        r'\$\(',               # $(command substitution)
        r'`[^`]+`',             # `command` backtick injection
        r'\b\w+\s*=\s*\$\(',   # VAR=$(cmd) assignment injection
        r'\bwget\b.*\|\s*\w',  # wget ... | something
        r'\bcurl\b.*-o\s+/etc', # curl -o /etc/ (overwrite system files)
        r'nc\s+-[el]',          # netcat listener (reverse shell)
        r'/dev/tcp/',           # bash /dev/tcp (reverse shell)
        r'base64\s+-d\s*\|',   # base64 -d | (encoded payload)
        r'\beval\b',           # eval (code injection)
        r'\bexec\b',           # exec (code injection)
    ]
    for pattern in sospechosos:
        if re.search(pattern, cmd_lower):
            return True
    
    return False


def validate_path(ruta: str) -> str:
    """Valida que una ruta este dentro de directorios permitidos. Previene path traversal."""
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
    return f"ACCESO DENEGADO: La ruta '{ruta}' esta fuera de los directorios permitidos. Solo puedes acceder a archivos dentro de {REPOS_DIR}"


def sanitize_input(text: str) -> str:
    """Sanitiza un input para prevenir inyeccion de comandos."""
    if not re.match(r'^[a-zA-Z0-9\s\.\-_:/\\@]+$', text):
        text = re.sub(r'[`$\{\}();|&<>!#~]', '', text)
    return text
