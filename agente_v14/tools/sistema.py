"""
=============================================================
AGENTE v14 - Herramientas del Sistema
=============================================================
ejecutar_comando, procesos_activos, matar_proceso
=============================================================
"""

import subprocess
import platform
import logging

from config import (
    REPOS_DIR, IS_WINDOWS, DEFAULT_TIMEOUT, LONG_TIMEOUT, MAX_TOOL_OUTPUT, logger
)
from utils.security import is_dangerous_command, sanitize_input

# Procesos del sistema que NUNCA se deben matar (pueden causar inestabilidad)
PROCESOS_CRITICOS = {
    # Windows
    "system", "lsass", "csrss", "smss", "wininit", "winlogon",
    "services", "svchost", "dwm", "explorer", "taskhostw",
    "runtimebroker", "searchindexer", "securityhealthservice",
    # Antivirus/seguridad
    "msmpeng", "msascuil", "nissrv",
    # Ollama (nuestro LLM)
    "ollama", "ollama_llama_server",
    # Linux
    "systemd", "init", "kernel", "sshd", "dbus-daemon",
}


def ejecutar_comando(comando: str, cwd: str = None, confirmar_peligroso: bool = False) -> str:
    """Ejecuta un comando en la terminal con VALIDACION de seguridad."""
    # Sanitizar input del usuario
    comando = sanitize_input(comando)
    cmd_lower = comando.lower()

    # Validar comandos peligrosos
    if is_dangerous_command(comando) and not confirmar_peligroso:
        logger.warning(f"Comando peligroso bloqueado: {comando}")
        return (f"COMANDO PELIGROSO detectado.\n"
                f"Si estas seguro, dime: 'ejecuta confirmado: {comando}'")

    # Timeout adaptativo
    timeout = DEFAULT_TIMEOUT
    if any(w in cmd_lower for w in ["install", "build", "compile", "docker", "pull"]):
        timeout = LONG_TIMEOUT

    try:
        # Detectar si es un comando simple (sin pipes/redirecciones)
        is_simple = not any(c in comando for c in '|&><`')

        if is_simple:
            parts = comando.split()
            result = subprocess.run(
                parts, capture_output=True, text=True,
                timeout=timeout, cwd=cwd or REPOS_DIR
            )
        else:
            result = subprocess.run(
                comando, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=cwd or REPOS_DIR
            )

        output = ""
        if result.stdout:
            output += result.stdout.strip()
        if result.stderr:
            stderr = result.stderr.strip()
            if stderr and "npm notice" not in stderr.lower():
                output += ("\n[STDERR] " + stderr) if output else stderr
        if not output:
            output = "(sin salida)"

        # Truncar si es muy largo
        if len(output) > MAX_TOOL_OUTPUT:
            output = output[:MAX_TOOL_OUTPUT] + "\n... [truncado]"
        return output

    except subprocess.TimeoutExpired:
        return f"ERROR_TIMEOUT: Comando cancelado (>{timeout}s)"
    except Exception as e:
        return f"ERROR: {e}"


def procesos_activos(filtro: str = "") -> str:
    """Lista procesos corriendo. Opcionalmente filtra por nombre."""
    if IS_WINDOWS:
        cmd = 'tasklist /fo csv'
        if filtro:
            cmd += f' | findstr /i "{filtro}"'
    else:
        cmd = 'ps aux'
        if filtro:
            cmd += f' | grep -i "{filtro}"'
    result = ejecutar_comando(cmd)
    if len(result) > MAX_TOOL_OUTPUT:
        result = result[:MAX_TOOL_OUTPUT] + "\n... [truncado]"
    return result


def matar_proceso(pid_o_nombre: str) -> str:
    """Termina un proceso por PID o nombre. Protege procesos criticos del sistema."""
    nombre_lower = pid_o_nombre.lower().strip()

    # Proteger procesos criticos (por nombre)
    for critico in PROCESOS_CRITICOS:
        if critico in nombre_lower or nombre_lower in critico:
            logger.warning(f"Intento de matar proceso critico bloqueado: {pid_o_nombre}")
            return (f"PROCESO CRITICO: No puedo terminar '{pid_o_nombre}' "
                    f"porque es un proceso del sistema esencial. "
                    f"Matarlo podria causar inestabilidad o perdida de datos.")

    # Sanitizar entrada
    pid_o_nombre = sanitize_input(pid_o_nombre)

    if IS_WINDOWS:
        if pid_o_nombre.isdigit():
            return ejecutar_comando(f"taskkill /pid {pid_o_nombre} /f")
        else:
            return ejecutar_comando(f'taskkill /f /im "{pid_o_nombre}"')
    else:
        if pid_o_nombre.isdigit():
            return ejecutar_comando(f"kill -9 {pid_o_nombre}")
        else:
            return ejecutar_comando(f"pkill -f {pid_o_nombre}")
