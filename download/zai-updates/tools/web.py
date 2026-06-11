"""
web.py — Herramientas web para ZAI
Cambio: integración de `sanitize_input` en todos los inputs de usuario
y `validate_url` para verificar que las URLs son seguras antes de
realizar peticiones.
"""

from __future__ import annotations

import subprocess
import json
import logging
import re
from typing import Optional, Dict, List, Any
from urllib.parse import urlparse

from utils.security import sanitize_input, validate_url, is_safe_command

logger = logging.getLogger(__name__)


# ====================================================================== #
#  Herramientas web                                                       #
# ====================================================================== #

def descargar_archivo(url: str, destino: str = "./downloads") -> Dict[str, Any]:
    """
    Descarga un archivo desde una URL usando wget o curl.

    Parámetros
    ----------
    url : str
        URL del archivo a descargar.
    destino : str
        Directorio de destino.

    Retorna
    -------
    dict con resultado de la descarga.
    """
    # ── Sanitizar y validar URL ──
    url = sanitize_input(url)
    destino = sanitize_input(destino)

    if not validate_url(url):
        return {"error": f"URL no válida o protocolo no permitido: {url[:100]}"}

    if not is_safe_command(f"wget {url}"):
        return {"error": "Descarga bloqueada por políticas de seguridad"}

    # Intentar con wget primero, luego curl
    for herramienta in ["wget", "curl"]:
        try:
            result = subprocess.run(
                ["which", herramienta],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0:
                continue

            if herramienta == "wget":
                cmd = ["wget", "-q", "--show-progress", "-P", destino, url]
            else:
                cmd = ["curl", "-sL", "-o", f"{destino}/download", url]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60,
            )

            if result.returncode == 0:
                logger.info("Archivo descargado: %s → %s", url, destino)
                return {
                    "exito": True,
                    "mensaje": f"Archivo descargado en {destino}",
                    "url": url,
                    "herramienta": herramienta,
                }
            else:
                return {"error": f"Error descargando: {result.stderr[:300]}"}

        except subprocess.TimeoutExpired:
            return {"error": "Timeout descargando archivo"}
        except Exception as exc:
            continue

    return {"error": "No se encontró wget ni curl en el sistema"}


def consultar_api(
    url: str,
    metodo: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    datos: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Realiza una petición HTTP a una API usando curl.

    Parámetros
    ----------
    url : str
        URL de la API.
    metodo : str
        Método HTTP (GET, POST, PUT, DELETE, PATCH).
    headers : dict, opcional
        Headers HTTP.
    datos : str, opcional
        Body de la petición (JSON).

    Retorna
    -------
    dict con la respuesta de la API.
    """
    # ── Sanitizar y validar URL ──
    url = sanitize_input(url)

    if not validate_url(url):
        return {"error": f"URL no válida o protocolo no permitido: {url[:100]}"}

    # ── Validar método ──
    metodos_permitidos = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
    metodo = sanitize_input(metodo).upper()
    if metodo not in metodos_permitidos:
        return {"error": f"Método HTTP no permitido: {metodo}"}

    # ── Construir comando curl ──
    cmd = ["curl", "-s", "-X", metodo, "-w", "\n%{http_code}"]

    # Headers
    if headers:
        for key, value in headers.items():
            key = sanitize_input(key)
            value = sanitize_input(value)
            cmd.extend(["-H", f"{key}: {value}"])

    # Datos
    if datos:
        datos = sanitize_input(datos)
        cmd.extend(["-d", datos])
        # Añadir Content-Type si no se especificó
        if not headers or "Content-Type" not in (headers or {}):
            cmd.extend(["-H", "Content-Type: application/json"])

    cmd.append(url)

    # ── Verificar seguridad ──
    cmd_str = " ".join(cmd)
    if not is_safe_command(cmd_str):
        return {"error": "Petición bloqueada por políticas de seguridad"}

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
        )

        # Separar respuesta del código de estado
        output = result.stdout
        lines = output.rsplit("\n", 1)
        http_code = lines[-1].strip() if len(lines) > 1 else "N/A"
        body = lines[0] if len(lines) > 1 else output

        # Intentar parsear como JSON
        try:
            json_body = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            json_body = None

        return {
            "status_code": http_code,
            "body": json_body if json_body else body[:2000],
            "url": url,
            "metodo": metodo,
            "es_json": json_body is not None,
        }

    except subprocess.TimeoutExpired:
        return {"error": "Timeout en petición HTTP"}
    except Exception as exc:
        return {"error": str(exc)}


def verificar_url(url: str) -> Dict[str, Any]:
    """
    Verifica si una URL es accesible y obtiene su código de estado.

    Parámetros
    ----------
    url : str
        URL a verificar.

    Retorna
    -------
    dict con el resultado de la verificación.
    """
    url = sanitize_input(url)

    if not validate_url(url):
        return {
            "accesible": False,
            "error": "URL no válida o protocolo no permitido",
            "url": url[:100],
        }

    try:
        cmd = ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", url]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=15,
        )

        status_code = result.stdout.strip()
        is_success = status_code.startswith("2") or status_code.startswith("3")

        return {
            "accesible": is_success,
            "status_code": status_code,
            "url": url,
        }

    except subprocess.TimeoutExpired:
        return {"accesible": False, "error": "Timeout verificando URL"}
    except Exception as exc:
        return {"accesible": False, "error": str(exc)}


def buscar_web(consulta: str, num_resultados: int = 5) -> Dict[str, Any]:
    """
    Realiza una búsqueda web usando un motor de búsqueda.

    NOTA: Esta función es un placeholder. En producción se conectaría
    con la API de búsqueda configurada (z-ai-web-dev-sdk, SerpAPI, etc.)

    Parámetros
    ----------
    consulta : str
        Término de búsqueda.
    num_resultados : int
        Número de resultados a devolver.

    Retorna
    -------
    dict con los resultados de la búsqueda.
    """
    consulta = sanitize_input(consulta)

    if not consulta:
        return {"error": "Consulta de búsqueda vacía"}

    if num_resultados < 1 or num_resultados > 20:
        return {"error": "num_resultados debe estar entre 1 y 20"}

    # Placeholder — en producción conectar con API real
    return {
        "consulta": consulta,
        "resultados": [],
        "mensaje": "Búsqueda web no configurada. Conectar con API de búsqueda.",
    }


def obtener_ip_publica() -> Dict[str, Any]:
    """
    Obtiene la dirección IP pública del sistema.

    Retorna
    -------
    dict con la IP pública.
    """
    servicios = [
        "https://api.ipify.org",
        "https://ifconfig.me",
        "https://icanhazip.com",
        "https://checkip.amazonaws.com",
    ]

    for servicio in servicios:
        try:
            result = subprocess.run(
                ["curl", "-s", servicio],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                ip = result.stdout.strip()
                # Validar que parece una IP
                if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
                    return {"ip_publica": ip, "servicio": servicio}
        except Exception:
            continue

    return {"error": "No se pudo obtener la IP pública"}
