"""
tools/system.py - Herramientas del sistema: ejecutar_comando, procesos, etc.
"""
import os
import subprocess
import platform
import logging
from . import tool
from ..config import REPOS_DIR, COMANDOS_PELIGROSOS

logger = logging.getLogger("agente.tools.system")


@tool(
    name="ejecutar_comando",
    description="Ejecuta un comando en la terminal. Peligrosos requieren confirmacion.",
    params={
        "comando": {"type": "string", "description": "Comando a ejecutar"},
        "confirmar_peligroso": {"type": "boolean", "description": "True si el usuario confirmo un comando peligroso"}
    },
    required=["comando"]
)
def ejecutar_comando(comando: str, cwd: str = None, confirmar_peligroso: bool = False) -> str:
    """Ejecuta un comando en la terminal con VALIDACION de seguridad."""
    cmd_lower = comando.lower()
    
    # Validar comandos peligrosos (blocklist)
    for peligro in COMANDOS_PELIGROSOS:
        if peligro in cmd_lower:
            if not confirmar_peligroso:
                logger.warning(f"Comando peligroso bloqueado: {comando}")
                return (f"COMANDO PELIGROSO detectado: '{peligro}'\n"
                        f"Si estas seguro, dime: 'ejecuta confirmado: {comando}'")
    
    # Timeout adaptativo
    timeout = 120
    if any(w in cmd_lower for w in ["install", "build", "compile", "docker", "pull"]):
        timeout = 300
    
    try:
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
        return output
    except subprocess.TimeoutExpired:
        return f"ERROR_TIMEOUT: Comando cancelado (>{timeout}s)"
    except Exception as e:
        return f"ERROR: {e}"


@tool(
    name="procesos_activos",
    description="Lista procesos corriendo. Opcionalmente filtra por nombre.",
    params={"filtro": {"type": "string", "description": "Filtro por nombre de proceso (opcional)"}},
    required=[]
)
def procesos_activos(filtro: str = "") -> str:
    """Lista procesos corriendo."""
    if platform.system() == "Windows":
        cmd = 'tasklist /fo csv'
        if filtro:
            cmd += f' | findstr /i "{filtro}"'
    else:
        cmd = 'ps aux'
        if filtro:
            cmd += f' | grep -i "{filtro}"'
    result = ejecutar_comando(cmd)
    if len(result) > 3000:
        result = result[:3000] + "\n... [truncado]"
    return result


@tool(
    name="matar_proceso",
    description="Termina un proceso por PID o nombre.",
    params={"pid_o_nombre": {"type": "string", "description": "PID numerico o nombre del proceso"}},
    required=["pid_o_nombre"]
)
def matar_proceso(pid_o_nombre: str) -> str:
    """Termina un proceso por PID o nombre."""
    if platform.system() == "Windows":
        if pid_o_nombre.isdigit():
            return ejecutar_comando(f"taskkill /pid {pid_o_nombre} /f")
        else:
            return ejecutar_comando(f'taskkill /f /im "{pid_o_nombre}"')
    else:
        if pid_o_nombre.isdigit():
            return ejecutar_comando(f"kill -9 {pid_o_nombre}")
        else:
            return ejecutar_comando(f"pkill -f {pid_o_nombre}")
