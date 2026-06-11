"""
=============================================================
AGENTE v14 - Herramientas de Aplicaciones y URLs
=============================================================
abrir_aplicacion, abrir_url, buscar_youtube
=============================================================
"""

import os
import re
import time
import platform
import logging

from config import (
    REPOS_DIR, SITIOS_CONOCIDOS, APP_ALIASES, IS_WINDOWS, logger
)
from utils.helpers import strip_prefixes, open_in_browser
from tools.sistema import ejecutar_comando

# Cache para buscar_exe (evita escaneo de disco repetido)
_exe_cache = {}
_exe_cache_time = {}


def buscar_en_start_menu(nombre: str) -> str:
    """Busca un acceso directo en el Start Menu de Windows."""
    nombre_lower = strip_prefixes(nombre).lower()

    start_menu_dirs = []
    if IS_WINDOWS:
        start_menu_dirs.append(os.path.join(
            os.environ.get("ProgramData", "C:\\ProgramData"),
            "Microsoft", "Windows", "Start Menu", "Programs"
        ))
        start_menu_dirs.append(os.path.join(
            os.environ.get("AppData", ""),
            "Microsoft", "Windows", "Start Menu", "Programs"
        ))

    matches = []
    for sm_dir in start_menu_dirs:
        if not os.path.exists(sm_dir):
            continue
        for root, dirs, files in os.walk(sm_dir):
            for f in files:
                f_lower = f.lower()
                if f_lower.endswith(".lnk"):
                    name_no_ext = f_lower[:-4]
                    if nombre_lower in name_no_ext or name_no_ext in nombre_lower:
                        matches.append((os.path.join(root, f), name_no_ext))

    if not matches:
        return ""

    for path, name in matches:
        if nombre_lower == name:
            return path
    return matches[0][0]


def buscar_exe(nombre: str) -> str:
    """Busca el ejecutable de una aplicacion con cache TTL de 5 minutos."""
    nombre_lower = strip_prefixes(nombre).lower()

    # Cache con TTL
    cache_key = nombre_lower
    if cache_key in _exe_cache:
        cached_time = _exe_cache_time.get(cache_key, 0)
        if time.time() - cached_time < 300:
            return _exe_cache[cache_key]

    shortcut = buscar_en_start_menu(nombre)
    if shortcut:
        _exe_cache[cache_key] = shortcut
        _exe_cache_time[cache_key] = time.time()
        return shortcut

    if not re.match(r'^[a-zA-Z0-9\s\.\-_]+$', nombre_lower):
        logger.warning(f"Nombre de app rechazado: {nombre_lower}")
        return ""

    if IS_WINDOWS:
        # Buscar en registro
        try:
            reg_cmd = (
                f'powershell -Command "'
                f'Get-ItemProperty \'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*\', '
                f'\'HKLM:\\SOFTWARE\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*\', '
                f'\'HKCU:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*\' '
                f'| Where-Object {{$_.DisplayName -like \'*{nombre}*\'}} '
                f'| Select-Object -ExpandProperty InstallLocation '
                f'| Select-Object -First 1"'
            )
            reg_result = ejecutar_comando(reg_cmd)
            if reg_result and reg_result != "(sin salida)" and "ERROR" not in reg_result:
                install_path = reg_result.strip().split('\n')[0].strip()
                if install_path and os.path.exists(install_path):
                    for root, dirs, files in os.walk(install_path):
                        level = root.replace(install_path, "").count(os.sep)
                        if level > 2:
                            dirs.clear()
                            continue
                        for f in files:
                            if f.lower().endswith(".exe") and nombre_lower in f.lower():
                                return os.path.join(root, f)
        except Exception:
            pass

        # Buscar en Program Files
        search_dirs = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        ]
        for base_dir in search_dirs:
            if not os.path.exists(base_dir):
                continue
            where_cmd = f'where /r "{base_dir}" *{nombre_lower}*.exe'
            where_result = ejecutar_comando(where_cmd)
            if where_result and where_result != "(sin salida)" and "ERROR" not in where_result:
                exes = [line.strip() for line in where_result.split('\n')
                        if line.strip() and line.strip().endswith(".exe")]
                if exes:
                    return exes[0]

    return ""


def abrir_url(url: str) -> str:
    """Abre una URL en el navegador por defecto."""
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url_lower = strip_prefixes(url).lower()
        if url_lower in SITIOS_CONOCIDOS:
            url = SITIOS_CONOCIDOS[url_lower]
        elif "." in url_lower:
            url = "https://" + url_lower
        else:
            return f"No puedo determinar la URL para '{url}'. Intenta con una URL completa."

    # Validar esquema
    import urllib.parse
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https", ""):
        return f"Esquema de URL no permitido: {parsed.scheme}"

    resultado = open_in_browser(url, ejecutar_comando_fn=ejecutar_comando)
    if not resultado or resultado == "(sin salida)" or "error" not in resultado.lower():
        return f"URL abierta en el navegador: {url}"
    return f"Error al abrir URL: {resultado}"


def abrir_aplicacion(app: str) -> str:
    """Abre una aplicacion de escritorio por nombre."""
    app_clean = strip_prefixes(app).lower()

    # Si parece URL, usar abrir_url
    indicadores_url = ["http://", "https://", "www.", ".com", ".org", ".net", ".io"]
    if any(ind in app_clean for ind in indicadores_url):
        return abrir_url(app)

    if app_clean in SITIOS_CONOCIDOS:
        return abrir_url(app_clean)

    search_name = APP_ALIASES.get(app_clean, app_clean)

    # Buscar en Start Menu
    shortcut_path = buscar_en_start_menu(search_name)
    if shortcut_path:
        resultado = ejecutar_comando(f'start "" "{shortcut_path}"')
        if not resultado or resultado == "(sin salida)" or "error" not in resultado.lower():
            return f"Aplicacion {app} abierta (via Start Menu)"

    # Buscar exe
    exe_path = buscar_exe(search_name)
    if exe_path:
        resultado = ejecutar_comando(f'start "" "{exe_path}"')
        if not resultado or resultado == "(sin salida)" or "error" not in resultado.lower():
            return f"Aplicacion {app} abierta (encontrada en: {exe_path})"

    # Intento directo
    resultado = ejecutar_comando(f"start {app_clean}")
    if not resultado or resultado == "(sin salida)":
        return f"Aplicacion {app} abierta"

    if "no se puede" in resultado.lower() or "no encuentra" in resultado.lower():
        return f"No encontre '{app}' en tu computadora."
    return resultado


def buscar_youtube(consulta: str) -> str:
    """Busca un video en YouTube y lo abre en el navegador."""
    import urllib.parse
    consulta_clean = strip_prefixes(consulta)
    encoded = urllib.parse.quote(consulta_clean)
    url = f"https://www.youtube.com/results?search_query={encoded}"

    resultado = open_in_browser(url, ejecutar_comando_fn=ejecutar_comando)
    if not resultado or resultado == "(sin salida)" or "error" not in resultado.lower():
        return f"Buscando '{consulta_clean}' en YouTube."
    return f"Abriendo YouTube con la busqueda: {consulta_clean}"
