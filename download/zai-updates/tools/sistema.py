"""
sistema.py — Herramientas de administración del sistema para ZAI
Cambio: REWRITE COMPLETO. Se añadió PROCESOS_CRITICOS para proteger
procesos esenciales del sistema que NO deben ser terminados, y se
mejoró la validación de seguridad en todos los comandos.
"""

from __future__ import annotations

import subprocess
import logging
import re
from typing import Optional, Dict, List, Any

from utils.security import (
    sanitize_input,
    sanitize_shell_arg,
    is_safe_command,
)

logger = logging.getLogger(__name__)


# ====================================================================== #
#  PROCESOS CRÍTICOS — NUNCA deben ser terminados                        #
# ====================================================================== #

PROCESOS_CRITICOS: List[str] = [
    # ── Init y sistema ──
    "systemd",
    "init",
    "sysvinit",
    "upstart",
    "openrc",
    "runit",
    "s6",

    # ── SSH y acceso remoto ──
    "sshd",
    "ssh-agent",
    "telnetd",

    # ── Kernel y udev ──
    "kthreadd",
    "ksoftirqd",
    "kworker",
    "migration",
    "rcu",
    "udev",

    # ── Logging ──
    "rsyslogd",
    "syslogd",
    "journald",
    "systemd-journal",

    # ── DBus y comunicación ──
    "dbus-daemon",
    "systemd-logind",
    "systemd-udevd",

    # ── Red ──
    "NetworkManager",
    "dhclient",
    "dhcpcd",
    "wpa_supplicant",
    "systemd-networkd",
    "avahi-daemon",

    # ── DNS ──
    "named",
    "dnsmasq",
    "systemd-resolved",

    # ── Cron y programación ──
    "cron",
    "crond",
    "atd",
    "systemd-cron",

    # ── Base de datos ──
    "mysqld",
    "postgres",
    "mongod",
    "redis-server",
    "mariadbd",

    # ── Servidor web ──
    "nginx",
    "apache2",
    "httpd",
    "caddy",

    # ── Supervisión ──
    "fail2ban",
    "monitorix",
    "prometheus",
    "grafana",

    # ── Contenedores ──
    "containerd",
    "dockerd",
    "kubelet",

    # ── ZAI ──
    "zai",
    "zai-core",
    "zai-agent",
    "ollama",
    "chroma",
]


def _es_proceso_critico(nombre_proceso: str) -> bool:
    """
    Verifica si un proceso está en la lista de procesos críticos.
    Hace matching parcial para cubrir variantes como 'sshd' en
    '/usr/sbin/sshd -D' o 'kworker/0:1'.
    """
    nombre_lower = nombre_proceso.lower().strip()
    for critico in PROCESOS_CRITICOS:
        if critico in nombre_lower:
            return True
    return False


# ====================================================================== #
#  Herramientas del sistema                                               #
# ====================================================================== #

def listar_procesos(filtro: Optional[str] = None) -> Dict[str, Any]:
    """
    Lista los procesos del sistema.

    Parámetros
    ----------
    filtro : str, opcional
        Filtrar procesos por nombre (substring).

    Retorna
    -------
    dict con:
        - procesos: lista de dicts con pid, nombre, cpu%, mem%
        - total: número de procesos listados
    """
    try:
        cmd = ["ps", "aux", "--sort=-%mem"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return {"error": f"Error ejecutando ps: {result.stderr}"}

        lineas = result.stdout.strip().split("\n")
        if len(lineas) < 2:
            return {"procesos": [], "total": 0}

        procesos = []
        for linea in lineas[1:]:  # Saltar header
            partes = linea.split(None, 10)
            if len(partes) < 11:
                continue

            nombre = partes[10]
            # Aplicar filtro si se especifica
            if filtro and filtro.lower() not in nombre.lower():
                continue

            es_critico = _es_proceso_critico(nombre)

            procesos.append({
                "usuario": partes[0],
                "pid": partes[1],
                "cpu": partes[2],
                "mem": partes[3],
                "vsz": partes[4],
                "rss": partes[5],
                "estado": partes[7],
                "nombre": nombre,
                "critico": es_critico,
            })

        return {"procesos": procesos, "total": len(procesos)}

    except subprocess.TimeoutExpired:
        return {"error": "Timeout listando procesos"}
    except Exception as exc:
        logger.error("Error en listar_procesos: %s", exc)
        return {"error": str(exc)}


def matar_proceso(pid: str, signal: str = "TERM") -> Dict[str, Any]:
    """
    Envía una señal a un proceso.

    **VALIDACIONES DE SEGURIDAD:**
    1. Verifica que el PID es numérico.
    2. Verifica que el proceso NO está en PROCESOS_CRITICOS.
    3. Verifica que la señal es permitida.
    4. Verifica que el comando es seguro.

    Parámetros
    ----------
    pid : str
        PID del proceso.
    signal : str
        Señal a enviar (TERM, HUP, USR1, USR2, INT). No se permite KILL -9
        para procesos críticos.

    Retorna
    -------
    dict con resultado de la operación.
    """
    # ── Validar PID ──
    pid = sanitize_input(pid)
    if not pid.isdigit():
        return {"error": f"PID inválido: {pid!r}. Debe ser numérico."}

    # ── Validar señal ──
    senales_permitidas = {"TERM", "HUP", "USR1", "USR2", "INT", "SIGTERM",
                          "SIGHUP", "SIGUSR1", "SIGUSR2", "SIGINT"}
    signal_upper = signal.upper().strip()
    if signal_upper not in senales_permitidas:
        return {
            "error": f"Señal no permitida: {signal!r}. "
                     f"Permitidas: {', '.join(sorted(senales_permitidas))}"
        }

    # ── Verificar proceso crítico ──
    try:
        # Obtener nombre del proceso
        proc_cmd = ["ps", "-p", pid, "-o", "comm="]
        proc_result = subprocess.run(
            proc_cmd, capture_output=True, text=True, timeout=5
        )
        if proc_result.returncode != 0:
            return {"error": f"Proceso con PID {pid} no encontrado."}

        nombre_proceso = proc_result.stdout.strip()

        if _es_proceso_critico(nombre_proceso):
            return {
                "error": (
                    f"⛔ PROCESO CRÍTICO: '{nombre_proceso}' (PID {pid}) "
                    f"está protegido y NO puede ser terminado. "
                    f"Los procesos críticos mantienen el sistema operativo."
                ),
                "proceso": nombre_proceso,
                "pid": pid,
                "critico": True,
            }

    except subprocess.TimeoutExpired:
        return {"error": "Timeout verificando proceso"}
    except Exception as exc:
        return {"error": f"Error verificando proceso: {exc}"}

    # ── Ejecutar kill ──
    try:
        kill_cmd = f"kill -{signal_upper} {pid}"
        if not is_safe_command(kill_cmd):
            return {"error": f"Comando bloqueado por seguridad: {kill_cmd}"}

        result = subprocess.run(
            ["kill", f"-{signal_upper}", pid],
            capture_output=True, text=True, timeout=5,
        )

        if result.returncode == 0:
            logger.info("Proceso %s (PID %s) terminado con señal %s",
                        nombre_proceso, pid, signal_upper)
            return {
                "exito": True,
                "mensaje": f"Señal {signal_upper} enviada a {nombre_proceso} (PID {pid})",
                "pid": pid,
                "proceso": nombre_proceso,
            }
        else:
            return {"error": f"Error enviando señal: {result.stderr}"}

    except subprocess.TimeoutExpired:
        return {"error": "Timeout enviando señal al proceso"}
    except Exception as exc:
        return {"error": f"Error: {exc}"}


def info_sistema() -> Dict[str, Any]:
    """
    Recopila información del sistema: hostname, uptime, memoria,
    disco, CPU y load average.

    Retorna
    -------
    dict con la información del sistema.
    """
    info: Dict[str, Any] = {}

    try:
        # Hostname
        result = subprocess.run(
            ["hostname"], capture_output=True, text=True, timeout=5
        )
        info["hostname"] = result.stdout.strip() if result.returncode == 0 else "N/A"

        # Uptime
        result = subprocess.run(
            ["uptime", "-p"], capture_output=True, text=True, timeout=5
        )
        info["uptime"] = result.stdout.strip() if result.returncode == 0 else "N/A"

        # Memoria
        result = subprocess.run(
            ["free", "-h"], capture_output=True, text=True, timeout=5
        )
        info["memoria"] = result.stdout.strip() if result.returncode == 0 else "N/A"

        # Disco
        result = subprocess.run(
            ["df", "-h", "/"], capture_output=True, text=True, timeout=5
        )
        info["disco"] = result.stdout.strip() if result.returncode == 0 else "N/A"

        # CPU info
        result = subprocess.run(
            ["nproc"], capture_output=True, text=True, timeout=5
        )
        info["cpu_nucleos"] = result.stdout.strip() if result.returncode == 0 else "N/A"

        # Load average
        try:
            with open("/proc/loadavg", "r") as f:
                info["load_avg"] = f.read().strip()
        except (FileNotFoundError, PermissionError):
            info["load_avg"] = "N/A"

        # OS
        try:
            with open("/etc/os-release", "r") as f:
                info["os"] = f.read().strip()
        except (FileNotFoundError, PermissionError):
            info["os"] = "N/A"

    except Exception as exc:
        info["error"] = str(exc)

    return info


def estado_servicio(servicio: str) -> Dict[str, Any]:
    """
    Consulta el estado de un servicio del sistema.

    Parámetros
    ----------
    servicio : str
        Nombre del servicio.

    Retorna
    -------
    dict con el estado del servicio.
    """
    servicio = sanitize_shell_arg(sanitize_input(servicio))

    if not servicio:
        return {"error": "Nombre de servicio vacío"}

    # Verificar que no sea un servicio crítico que podría exponer info sensible
    if not is_safe_command(f"systemctl status {servicio}"):
        return {"error": f"Servicio bloqueado por políticas de seguridad: {servicio}"}

    try:
        result = subprocess.run(
            ["systemctl", "status", servicio, "--no-pager"],
            capture_output=True, text=True, timeout=10,
        )
        return {
            "servicio": servicio,
            "activo": "active" in result.stdout.lower(),
            "salida": result.stdout[:500],  # Limitar output
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Timeout consultando estado de {servicio}"}
    except Exception as exc:
        return {"error": str(exc)}


def listar_archivos(directorio: str, patron: Optional[str] = None) -> Dict[str, Any]:
    """
    Lista archivos de un directorio.

    Parámetros
    ----------
    directorio : str
        Ruta del directorio.
    patron : str, opcional
        Patrón de filtrado (glob).

    Retorna
    -------
    dict con la lista de archivos.
    """
    directorio = sanitize_shell_arg(sanitize_input(directorio))

    # Verificar rutas prohibidas
    rutas_prohibidas = ["/etc/shadow", "/etc/passwd", "/root/.ssh",
                        "/etc/ssh", "/etc/sudoers"]
    for ruta in rutas_prohibidas:
        if directorio.startswith(ruta):
            return {"error": f"Acceso denegado a ruta protegida: {directorio}"}

    if not is_safe_command(f"ls {directorio}"):
        return {"error": "Directorio bloqueado por políticas de seguridad"}

    try:
        cmd = ["ls", "-la", directorio]
        if patron:
            patron = sanitize_shell_arg(patron)
            cmd = ["find", directorio, "-maxdepth", "1", "-name", patron]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )

        if result.returncode != 0:
            return {"error": result.stderr.strip()}

        return {
            "directorio": directorio,
            "archivos": result.stdout.strip(),
        }
    except subprocess.TimeoutExpired:
        return {"error": "Timeout listando archivos"}
    except Exception as exc:
        return {"error": str(exc)}


def uso_recursos() -> Dict[str, Any]:
    """
    Devuelve un resumen del uso de recursos del sistema.

    Retorna
    -------
    dict con métricas de CPU, memoria y disco.
    """
    info: Dict[str, Any] = {}

    try:
        # CPU usage (top batch mode, 1 iteration)
        result = subprocess.run(
            ["top", "-bn1"], capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            for linea in result.stdout.split("\n"):
                if "Cpu(s)" in linea:
                    info["cpu_linea"] = linea.strip()
                    break

        # Memoria resumida
        result = subprocess.run(
            ["free", "-m"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            lineas = result.stdout.strip().split("\n")
            if len(lineas) >= 2:
                partes = lineas[1].split()
                if len(partes) >= 7:
                    info["memoria_total_mb"] = partes[1]
                    info["memoria_usada_mb"] = partes[2]
                    info["memoria_libre_mb"] = partes[3]
                    info["memoria_disponible_mb"] = partes[6]

        # Disco resumido
        result = subprocess.run(
            ["df", "-h", "/"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            lineas = result.stdout.strip().split("\n")
            if len(lineas) >= 2:
                info["disco_linea"] = lineas[1].strip()

    except Exception as exc:
        info["error"] = str(exc)

    return info
