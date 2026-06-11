"""
apps.py — Herramientas de gestión de aplicaciones para ZAI
Cambio: integración de `sanitize_input` en todos los inputs de usuario
para prevenir inyección de comandos y caracteres maliciosos.
"""

from __future__ import annotations

import subprocess
import logging
import re
from typing import Optional, Dict, List, Any

from utils.security import sanitize_input, sanitize_shell_arg, is_safe_command

logger = logging.getLogger(__name__)


# ====================================================================== #
#  Gestor de paquetes (detecta apt, dnf, pacman, etc.)                   #
# ====================================================================== #

def _detectar_gestor_paquetes() -> Optional[str]:
    """Detecta el gestor de paquetes del sistema."""
    gestores = [
        ("apt-get", "apt"),
        ("dnf", "dnf"),
        ("yum", "yum"),
        ("pacman", "pacman"),
        ("zypper", "zypper"),
        ("apk", "apk"),
        ("emerge", "emerge"),
    ]
    for cmd, nombre in gestores:
        try:
            result = subprocess.run(
                ["which", cmd], capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return nombre
        except Exception:
            continue
    return None


GESTOR = _detectar_gestor_paquetes()


# ====================================================================== #
#  Funciones de aplicaciones                                              #
# ====================================================================== #

def instalar_app(nombre: str) -> Dict[str, Any]:
    """
    Instala una aplicación usando el gestor de paquetes del sistema.

    Parámetros
    ----------
    nombre : str
        Nombre del paquete a instalar.

    Retorna
    -------
    dict con resultado de la instalación.
    """
    # ── Sanitizar input ──
    nombre = sanitize_input(nombre)
    nombre = sanitize_shell_arg(nombre)

    if not nombre:
        return {"error": "Nombre de paquete vacío"}

    if not is_safe_command(f"install {nombre}"):
        return {"error": f"Paquete bloqueado por seguridad: {nombre}"}

    if GESTOR is None:
        return {"error": "No se detectó gestor de paquetes en el sistema"}

    # ── Construir comando según gestor ──
    comandos = {
        "apt": ["sudo", "apt-get", "install", "-y", nombre],
        "dnf": ["sudo", "dnf", "install", "-y", nombre],
        "yum": ["sudo", "yum", "install", "-y", nombre],
        "pacman": ["sudo", "pacman", "-S", "--noconfirm", nombre],
        "zypper": ["sudo", "zypper", "install", "-y", nombre],
        "apk": ["apk", "add", nombre],
        "emerge": ["sudo", "emerge", nombre],
    }

    cmd = comandos.get(GESTOR)
    if cmd is None:
        return {"error": f"Gestor {GESTOR} no soportado"}

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )

        if result.returncode == 0:
            logger.info("App instalada: %s (gestor: %s)", nombre, GESTOR)
            return {
                "exito": True,
                "mensaje": f"{nombre} instalado correctamente con {GESTOR}",
                "gestor": GESTOR,
            }
        else:
            return {
                "exito": False,
                "error": result.stderr[:500],
                "gestor": GESTOR,
            }

    except subprocess.TimeoutExpired:
        return {"error": f"Timeout instalando {nombre}"}
    except Exception as exc:
        return {"error": str(exc)}


def desinstalar_app(nombre: str) -> Dict[str, Any]:
    """
    Desinstala una aplicación usando el gestor de paquetes.

    Parámetros
    ----------
    nombre : str
        Nombre del paquete a desinstalar.

    Retorna
    -------
    dict con resultado de la desinstalación.
    """
    # ── Sanitizar input ──
    nombre = sanitize_input(nombre)
    nombre = sanitize_shell_arg(nombre)

    if not nombre:
        return {"error": "Nombre de paquete vacío"}

    if not is_safe_command(f"remove {nombre}"):
        return {"error": f"Operación bloqueada por seguridad: remove {nombre}"}

    if GESTOR is None:
        return {"error": "No se detectó gestor de paquetes en el sistema"}

    # ── Construir comando de desinstalación ──
    comandos = {
        "apt": ["sudo", "apt-get", "remove", "-y", nombre],
        "dnf": ["sudo", "dnf", "remove", "-y", nombre],
        "yum": ["sudo", "yum", "remove", "-y", nombre],
        "pacman": ["sudo", "pacman", "-R", "--noconfirm", nombre],
        "zypper": ["sudo", "zypper", "remove", "-y", nombre],
        "apk": ["apk", "del", nombre],
        "emerge": ["sudo", "emerge", "--depclean", nombre],
    }

    cmd = comandos.get(GESTOR)
    if cmd is None:
        return {"error": f"Gestor {GESTOR} no soportado"}

    # ── Verificar que no sea un paquete crítico ──
    paquetes_criticos = [
        "systemd", "sudo", "openssh-server", "openssl", "gnupg",
        "iptables", "ufw", "fail2ban", "curl", "wget",
    ]
    if nombre.lower() in paquetes_criticos:
        return {
            "error": f"⛔ Paquete crítico: '{nombre}' está protegido y no se "
                     f"puede desinstalar para mantener la seguridad del sistema.",
            "paquete": nombre,
            "critico": True,
        }

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )

        if result.returncode == 0:
            logger.info("App desinstalada: %s (gestor: %s)", nombre, GESTOR)
            return {
                "exito": True,
                "mensaje": f"{nombre} desinstalado correctamente con {GESTOR}",
                "gestor": GESTOR,
            }
        else:
            return {
                "exito": False,
                "error": result.stderr[:500],
                "gestor": GESTOR,
            }

    except subprocess.TimeoutExpired:
        return {"error": f"Timeout desinstalando {nombre}"}
    except Exception as exc:
        return {"error": str(exc)}


def buscar_app(termino: str) -> Dict[str, Any]:
    """
    Busca paquetes disponibles en los repositorios.

    Parámetros
    ----------
    termino : str
        Término de búsqueda.

    Retorna
    -------
    dict con los resultados de la búsqueda.
    """
    # ── Sanitizar input ──
    termino = sanitize_input(termino)
    termino = sanitize_shell_arg(termino)

    if not termino:
        return {"error": "Término de búsqueda vacío"}

    if GESTOR is None:
        return {"error": "No se detectó gestor de paquetes en el sistema"}

    comandos = {
        "apt": ["apt-cache", "search", termino],
        "dnf": ["dnf", "search", termino],
        "yum": ["yum", "search", termino],
        "pacman": ["pacman", "-Ss", termino],
        "zypper": ["zypper", "search", termino],
        "apk": ["apk", "search", termino],
        "emerge": ["emerge", "--search", termino],
    }

    cmd = comandos.get(GESTOR)
    if cmd is None:
        return {"error": f"Gestor {GESTOR} no soportado"}

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )

        if result.returncode == 0:
            # Limitar output a 50 líneas
            lineas = result.stdout.strip().split("\n")[:50]
            return {
                "resultados": lineas,
                "total": len(lineas),
                "gestor": GESTOR,
            }
        else:
            return {
                "error": result.stderr[:300],
                "gestor": GESTOR,
            }

    except subprocess.TimeoutExpired:
        return {"error": f"Timeout buscando {termino}"}
    except Exception as exc:
        return {"error": str(exc)}


def actualizar_sistema() -> Dict[str, Any]:
    """
    Actualiza todos los paquetes del sistema.

    Retorna
    -------
    dict con el resultado de la actualización.
    """
    if GESTOR is None:
        return {"error": "No se detectó gestor de paquetes en el sistema"}

    comandos = {
        "apt": ["sudo", "apt-get", "update", "&&", "sudo", "apt-get", "upgrade", "-y"],
        "dnf": ["sudo", "dnf", "upgrade", "-y"],
        "yum": ["sudo", "yum", "update", "-y"],
        "pacman": ["sudo", "pacman", "-Syu", "--noconfirm"],
        "zypper": ["sudo", "zypper", "update", "-y"],
        "apk": ["apk", "upgrade"],
        "emerge": ["sudo", "emerge", "--update", "@world"],
    }

    cmd = comandos.get(GESTOR)
    if cmd is None:
        return {"error": f"Gestor {GESTOR} no soportado"}

    try:
        # Para apt, ejecutar update y upgrade por separado
        if GESTOR == "apt":
            subprocess.run(
                ["sudo", "apt-get", "update"],
                capture_output=True, text=True, timeout=60,
            )
            result = subprocess.run(
                ["sudo", "apt-get", "upgrade", "-y"],
                capture_output=True, text=True, timeout=300,
            )
        else:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )

        if result.returncode == 0:
            return {
                "exito": True,
                "mensaje": f"Sistema actualizado con {GESTOR}",
                "output": result.stdout[:500],
            }
        else:
            return {
                "exito": False,
                "error": result.stderr[:500],
            }

    except subprocess.TimeoutExpired:
        return {"error": "Timeout actualizando sistema"}
    except Exception as exc:
        return {"error": str(exc)}


def info_app(nombre: str) -> Dict[str, Any]:
    """
    Muestra información detallada de un paquete instalado.

    Parámetros
    ----------
    nombre : str
        Nombre del paquete.

    Retorna
    -------
    dict con la información del paquete.
    """
    # ── Sanitizar input ──
    nombre = sanitize_input(nombre)
    nombre = sanitize_shell_arg(nombre)

    if not nombre:
        return {"error": "Nombre de paquete vacío"}

    if GESTOR is None:
        return {"error": "No se detectó gestor de paquetes en el sistema"}

    comandos = {
        "apt": ["apt-cache", "show", nombre],
        "dnf": ["dnf", "info", nombre],
        "yum": ["yum", "info", nombre],
        "pacman": ["pacman", "-Si", nombre],
        "zypper": ["zypper", "info", nombre],
        "apk": ["apk", "info", "-a", nombre],
        "emerge": ["emerge", "--info", nombre],
    }

    cmd = comandos.get(GESTOR)
    if cmd is None:
        return {"error": f"Gestor {GESTOR} no soportado"}

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
        )

        if result.returncode == 0:
            return {
                "paquete": nombre,
                "info": result.stdout[:1000],
                "gestor": GESTOR,
            }
        else:
            return {
                "error": f"Paquete '{nombre}' no encontrado",
                "gestor": GESTOR,
            }

    except subprocess.TimeoutExpired:
        return {"error": f"Timeout obteniendo info de {nombre}"}
    except Exception as exc:
        return {"error": str(exc)}


def listar_apps_instaladas(filtro: Optional[str] = None) -> Dict[str, Any]:
    """
    Lista las aplicaciones instaladas en el sistema.

    Parámetros
    ----------
    filtro : str, opcional
        Filtrar por nombre (substring).

    Retorna
    -------
    dict con la lista de aplicaciones instaladas.
    """
    if GESTOR is None:
        return {"error": "No se detectó gestor de paquetes en el sistema"}

    if filtro:
        filtro = sanitize_input(filtro)
        filtro = sanitize_shell_arg(filtro)

    comandos = {
        "apt": ["dpkg", "--get-selections"],
        "dnf": ["dnf", "list", "installed"],
        "yum": ["yum", "list", "installed"],
        "pacman": ["pacman", "-Q"],
        "zypper": ["zypper", "search", "--installed-only"],
        "apk": ["apk", "info"],
        "emerge": ["qlist", "-I"],
    }

    cmd = comandos.get(GESTOR)
    if cmd is None:
        return {"error": f"Gestor {GESTOR} no soportado"}

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )

        if result.returncode == 0:
            lineas = result.stdout.strip().split("\n")

            # Aplicar filtro si se especifica
            if filtro:
                lineas = [l for l in lineas if filtro.lower() in l.lower()]

            # Limitar a 100 resultados
            lineas = lineas[:100]

            return {
                "aplicaciones": lineas,
                "total": len(lineas),
                "gestor": GESTOR,
            }
        else:
            return {"error": result.stderr[:300]}

    except subprocess.TimeoutExpired:
        return {"error": "Timeout listando aplicaciones"}
    except Exception as exc:
        return {"error": str(exc)}
