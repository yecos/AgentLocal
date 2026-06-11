"""
security.py — Utilidades de seguridad para ZAI
Cambio: comandos y patrones extendidos para bloquear más vectores de ataque.
Incluye sanitización de entrada, validación de comandos y detección de
inyección de prompts.
"""

from __future__ import annotations

import re
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)


# ====================================================================== #
#  PATRONES DE COMANDOS PELIGROSOS — extendidos                          #
# ====================================================================== #

COMANDOS_BLOQUEADOS: List[str] = [
    # ── Eliminación destructiva ──
    r"rm\s+-rf\s+/",
    r"rm\s+-rf\s+~",
    r"rm\s+-rf\s+\*",
    r"rm\s+-r\s+/",
    r"rm\s+-fr\s+/",
    r"rmdir\s+/s\s+/q",
    r"del\s+/[sfq]",
    r"rd\s+/s\s+/q",
    r"shred\s+",
    r"wipe\s+",
    r"secure-empty-trash",

    # ── Sistema y particiones ──
    r"dd\s+if=",
    r"mkfs\b",
    r"fdisk\b",
    r"parted\b",
    r"gparted\b",
    r"format\s+[A-Za-z]:",

    # ── Permisos y escalación ──
    r"chmod\s+777",
    r"chmod\s+-R\s+777",
    r"chown\s+.*:.*\s+/",
    r"chown\s+-R\s+",

    # ── Red y conexiones ──
    r"nc\s+-[elp]",
    r"netcat\s+",
    r"ncat\s+",
    r"curl\s+.*\|\s*sh",
    r"curl\s+.*\|\s*bash",
    r"wget\s+.*\|\s*sh",
    r"wget\s+.*\|\s*bash",
    r"nmap\s+",
    r"telnet\s+",

    # ── Usuarios y contraseñas ──
    r"passwd\s+",
    r"useradd\s+",
    r"userdel\s+",
    r"usermod\s+",
    r"adduser\s+",
    r"deluser\s+",
    r"chpasswd\b",
    r"chsh\s+",

    # ── Procesos y servicios ──
    r"kill\s+-9\s+1\b",
    r"killall\s+",
    r"pkill\s+-9",
    r"systemctl\s+(stop|disable|mask)\s+(ssh|sshd|firewall|ufw|iptables|systemd)",
    r"service\s+\w+\s+stop",

    # ── Kernel y módulos ──
    r"insmod\b",
    r"rmmod\b",
    r"modprobe\b",
    r"sysctl\s+-w",

    # ── Cron y tareas programadas ──
    r"crontab\s+-r",
    r"at\b.*\d",

    # ── Redirección destructiva ──
    r">\s*/dev/sd",
    r">\s*/dev/hd",
    r">\s*/etc/passwd",
    r">\s*/etc/shadow",
    r">\s*/etc/sudoers",
    r">\s*/etc/hosts",
    r">\s*/boot/",
    r">\s*/etc/fstab",
    r">\s*/etc/ssh/sshd_config",

    # ── Shell y ejecución ──
    r":\(\)\{\s*:\|:\s*&\s*\}",  # fork bomb
    r"fork\s+bomb",

    # ── Docker y contenedores ──
    r"docker\s+rm\s+-f\s+\w+",
    r"docker\s+rmi\s+",
    r"docker\s+system\s+prune",
    r"kubectl\s+delete\s+namespace",

    # ── Python peligroso ──
    r"os\.system\s*\(",
    r"subprocess\.call\s*\(",
    r"exec\s*\(",
    r"eval\s*\(",
    r"__import__\s*\(",
    r"pickle\.loads\s*\(",
    r"marshal\.loads\s*\(",
    r"compile\s*\(",
]

# Compilar todos los patrones como regex
_PATRONES_COMPILADOS = [re.compile(p, re.IGNORECASE) for p in COMANDOS_BLOQUEADOS]


# ====================================================================== #
#  PATRONES DE INYECCIÓN DE PROMPTS                                       #
# ====================================================================== #

PATRONES_INYECCION: List[str] = [
    r"ignore\s+(all\s+)?previous\s+(instructions|prompts)",
    r"forget\s+(all\s+)?previous\s+(instructions|prompts|context)",
    r"disregard\s+(all\s+)?previous",
    r"you\s+are\s+now\s+",
    r"new\s+instructions?\s*:",
    r"system\s*:\s*",
    r"override\s+(safety|security|restrictions)",
    r"pretend\s+(you\s+are|to\s+be)",
    r"act\s+as\s+if\s+you\s+(are|were)",
    r"jailbreak",
    r"DAN\s+mode",
    r"developer\s+mode",
    r"admin\s+mode",
    r"root\s+mode",
    r"sudo\s+mode",
    r"bypass\s+(safety|security|filter|restrictions)",
    r"disable\s+(safety|security|filter|restrictions|guardrails)",
    r"reveal\s+(your|the|system)\s+(prompt|instructions)",
    r"show\s+me\s+(your|the|system)\s+(prompt|instructions)",
    r"what\s+(are|is)\s+your\s+(system|hidden)\s+(prompt|instructions)",
    r"print\s+your\s+(system|hidden)\s+(prompt|instructions)",
    r"output\s+your\s+(system|hidden)\s+(prompt|instructions)",
]

_PATRONES_INYECCION_COMPILADOS = [
    re.compile(p, re.IGNORECASE) for p in PATRONES_INYECCION
]


# ====================================================================== #
#  FUNCIONES PÚBLICAS                                                     #
# ====================================================================== #

def sanitize_input(text: str) -> str:
    """
    Sanitiza texto de entrada eliminando caracteres potencialmente
    peligrosos y normalizando espacios.

    - Elimina caracteres de control (excepto salto de línea y tab).
    - Elimina secuencias de escape ANSI.
    - Recorta espacios múltiples.
    - Elimina null bytes.
    """
    if not text:
        return ""

    # Eliminar null bytes
    text = text.replace("\x00", "")

    # Eliminar secuencias ANSI de escape
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)

    # Eliminar caracteres de control (mantener \n, \t, \r)
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Normalizar espacios múltiples
    text = re.sub(r" {2,}", " ", text)

    return text.strip()


def is_safe_command(command: str) -> bool:
    """
    Verifica si un comando es seguro para ejecutar.

    Retorna False si el comando coincide con algún patrón bloqueado.
    """
    if not command:
        return True

    for patron in _PATRONES_COMPILADOS:
        if patron.search(command):
            logger.warning("Comando bloqueado por seguridad: patrón=%s  cmd=%s",
                           patron.pattern, command[:100])
            return False
    return True


def detect_prompt_injection(text: str) -> bool:
    """
    Detecta si el texto contiene patrones de inyección de prompts.

    Retorna True si se detecta un posible intento de inyección.
    """
    if not text:
        return False

    for patron in _PATRONES_INYECCION_COMPILADOS:
        if patron.search(text):
            logger.warning("Posible inyección de prompt detectada: patrón=%s",
                           patron.pattern)
            return True
    return False


def validate_url(url: str) -> bool:
    """
    Valida que una URL sea segura y use un protocolo permitido.

    Solo permite HTTP y HTTPS. Rechaza protocolos peligrosos como
    file://, javascript:, data:, etc.
    """
    if not url:
        return False

    # Verificar protocolo
    url_lower = url.strip().lower()
    protocolos_permitidos = ("http://", "https://")

    if not any(url_lower.startswith(p) for p in protocolos_permitidos):
        logger.warning("URL con protocolo no permitido: %s", url[:100])
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
            logger.warning("URL con protocolo peligroso embebido: %s", url[:100])
            return False

    # Verificar formato básico de URL
    url_pattern = re.compile(
        r'^https?://'
        r'[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?'
        r'(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*'
        r'(:\d{1,5})?(/.*)?$'
    )
    if not url_pattern.match(url.strip()):
        logger.warning("URL con formato inválido: %s", url[:100])
        return False

    return True


def sanitize_shell_arg(arg: str) -> str:
    """
    Escapa un argumento de shell para prevenir inyección de comandos.

    NOTA: Se recomienda usar subprocess con listas de argumentos en
    lugar de shell=True. Esta función es un refuerzo adicional.
    """
    if not arg:
        return ""

    # Eliminar caracteres de shell peligrosos
    cleaned = re.sub(r'[`$\\;|&<>(){}[\]!#~]', '', arg)

    # Eliminar nuevas líneas
    cleaned = cleaned.replace('\n', '').replace('\r', '')

    return cleaned.strip()
