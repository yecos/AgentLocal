"""
=============================================================
AGENTE v14 - Seguridad
=============================================================
Validacion de comandos peligrosos, path traversal, sanitizacion.
v2: Patrones extendidos, validate_url, sanitize_input mejorado,
    deteccion de inyeccion de prompts.
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
    # Ransomware/exfiltration patterns
    "icacls /grant everyone", "net share c",
    "vssadmin delete", "wbadmin delete",
    "bcdedit /delete", "bootrec /fixmbr",
    # Nuevos: destrucion masiva
    "rm -r /", "rm -fr /", "rm -rf ~", "rm -rf *",
    "shred", "wipe", "secure-empty-trash",
    # Permisos peligrosos
    "chmod 777", "chmod -R 777", "chown root",
    # Red peligrosa
    "nc -e", "ncat", "nmap", "telnet",
    "wget | sh", "wget | bash",
    # Usuarios/contrasenas
    "passwd", "useradd", "userdel", "chpasswd",
    # Kernel/modulos
    "insmod", "rmmod", "modprobe", "sysctl -w",
    # Docker destructivo
    "docker rm -f", "docker rmi", "docker system prune",
    "kubectl delete namespace",
    # Redireccion destructiva
    "> /etc/passwd", "> /etc/shadow", "> /etc/sudoers",
    "> /etc/hosts", "> /boot/", "> /etc/fstab",
    "> /etc/ssh/sshd_config",
    # Python peligroso
    "os.system(", "subprocess.call(", "pickle.loads(",
    "marshal.loads(",
]

# Comandos permitidos sin confirmacion (allowlist)
COMANDOS_SEGUROS = [
    "git", "npm", "pip", "python", "node", "dir", "ls",
    "cat", "echo", "cd", "type", "find", "where", "which",
    "tasklist", "start", "open", "xdg-open",
    "pipenv", "poetry", "bun", "yarn", "cargo",
    "docker ps", "docker images", "docker compose",
    # Herramientas de desarrollo comunes
    "ollama", "code", "nvim", "vim",
    "pytest", "jest", "vitest",
    "uvicorn", "flask", "gunicorn",
    "npx", "pnpm",
]

# Patrones de inyeccion de prompts
PATRONES_INYECCION_PROMPT = [
    r"ignore\s+(all\s+)?previous\s+(instructions|prompts)",
    r"forget\s+(all\s+)?previous\s+(instructions|prompts|context)",
    r"disregard\s+(all\s+)?previous",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?\s*:",
    r"override\s+(safety|security|restrictions)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"jailbreak",
    r"DAN\s+mode",
    r"developer\s+mode",
    r"admin\s+mode",
    r"bypass\s+(safety|security|filter)",
    r"disable\s+(safety|security|filter|guardrails)",
    r"reveal\s+(your|the|system)\s+(prompt|instructions)",
    r"show\s+me\s+(your|the|system)\s+(prompt|instructions)",
    r"what\s+(are|is)\s+your\s+(system|hidden)\s+(prompt|instructions)",
]

_PATRONES_INYECCION_COMPILADOS = [
    re.compile(p, re.IGNORECASE) for p in PATRONES_INYECCION_PROMPT
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
        # Inyeccion avanzada
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
        # Nuevos: fork bomb
        r':\(\)\{\s*:\|:\s*&\s*\}',  # fork bomb
        r'fork\s+bomb',
        # Nuevos: protocolos peligrosos en URL
        r'javascript\s*:',
        r'data\s*:',
        r'file\s*:',
        r'vbscript\s*:',
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
    """Sanitiza un input para prevenir inyeccion de comandos.
    v2: Elimina null bytes, secuencias ANSI, y caracteres de control."""
    if not text:
        return ""
    
    # Eliminar null bytes
    text = text.replace("\x00", "")
    
    # Eliminar secuencias ANSI de escape
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    
    # Eliminar caracteres de control (mantener \n, \t, \r)
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    
    # Si solo tiene caracteres seguros, mantener tal cual
    if re.match(r'^[a-zA-Z0-9\s\.\-_:/\\@]+$', text):
        return text.strip()
    
    # Limpiar caracteres peligrosos
    text = re.sub(r'[`$\{\}();|&<>!#~]', '', text)
    
    # Normalizar espacios multiples
    text = re.sub(r' {2,}', ' ', text)
    
    return text.strip()


def validate_url(url: str) -> bool:
    """Valida que una URL sea segura y use un protocolo permitido.
    Solo permite HTTP y HTTPS. Rechaza file://, javascript:, data:, etc."""
    if not url:
        return False

    url_lower = url.strip().lower()
    protocolos_permitidos = ("http://", "https://")

    if not any(url_lower.startswith(p) for p in protocolos_permitidos):
        logger.warning(f"URL con protocolo no permitido: {url[:100]}")
        return False

    # Verificar que no haya protocolos embebidos
    patrones_peligrosos_url = [
        r"javascript\s*:",
        r"data\s*:",
        r"file\s*:",
        r"vbscript\s*:",
        r"blob\s*:",
    ]
    for patron in patrones_peligrosos_url:
        if re.search(patron, url, re.IGNORECASE):
            logger.warning(f"URL con protocolo peligroso embebido: {url[:100]}")
            return False

    # Verificar formato basico
    url_pattern = re.compile(
        r'^https?://'
        r'[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?'
        r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*'
        r'(:\d{1,5})?(/.*)?$'
    )
    if not url_pattern.match(url.strip()):
        logger.warning(f"URL con formato invalido: {url[:100]}")
        return False

    return True


def detect_prompt_injection(text: str) -> bool:
    """Detecta si el texto contiene patrones de inyeccion de prompts."""
    if not text:
        return False
    for patron in _PATRONES_INYECCION_COMPILADOS:
        if patron.search(text):
            logger.warning(f"Posible inyeccion de prompt detectada: patron={patron.pattern}")
            return True
    return False


def sanitize_shell_arg(arg: str) -> str:
    """Escapa un argumento de shell para prevenir inyeccion de comandos."""
    if not arg:
        return ""
    cleaned = re.sub(r'[`$\\;|&<>(){}[\]!#~]', '', arg)
    cleaned = cleaned.replace('\n', '').replace('\r', '')
    return cleaned.strip()
