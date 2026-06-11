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
from utils.security import sanitize_input
from tools.sistema import ejecutar_comando

# Cache para buscar_exe (evita escaneo de disco repetido)
_exe_cache = {}
_exe_cache_time = {}

# Nombres alternativos de ejecutables (lo que el usuario dice -> como se llama el .exe)
_EXE_ALIASES = {
    "autocad": "acad",
    "revit": "revit",
    "photoshop": "photoshop",
    "illustrator": "illustrator",
    "visual studio code": "code",
    "vscode": "code",
    "visual studio": "devenv",
    "google chrome": "chrome",
    "chrome": "chrome",
    "firefox": "firefox",
    "microsoft word": "winword",
    "word": "winword",
    "microsoft excel": "excel",
    "excel": "excel",
    "microsoft powerpoint": "powerpnt",
    "powerpoint": "powerpnt",
    "notepad": "notepad",
    "blender": "blender",
    "sketchup": "sketchup",
    "figma": "figma",
    "telegram": "telegram",
    "whatsapp": "whatsapp",
}


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
    exe_name = _EXE_ALIASES.get(nombre_lower, nombre_lower)

    # Cache con TTL
    cache_key = nombre_lower
    if cache_key in _exe_cache:
        cached_time = _exe_cache_time.get(cache_key, 0)
        if time.time() - cached_time < 300:
            return _exe_cache[cache_key]

    # 0. Buscar en Start Menu primero (rapido)
    shortcut = buscar_en_start_menu(nombre)
    if shortcut:
        _exe_cache[cache_key] = shortcut
        _exe_cache_time[cache_key] = time.time()
        return shortcut

    if not re.match(r'^[a-zA-Z0-9\s\.\-_]+$', nombre_lower):
        logger.warning(f"Nombre de app rechazado: {nombre_lower}")
        return ""

    if IS_WINDOWS:
        # 1. Buscar en registro (InstallLocation) - busca por nombre del producto
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
                    # Buscar exe con nombre real (alias) dentro del directorio de instalacion
                    for root, dirs, files in os.walk(install_path):
                        level = root.replace(install_path, "").count(os.sep)
                        if level > 3:
                            dirs.clear()
                            continue
                        for f in files:
                            f_lower = f.lower()
                            if f_lower.endswith(".exe") and (
                                exe_name in f_lower or nombre_lower in f_lower
                            ):
                                result = os.path.join(root, f)
                                _exe_cache[cache_key] = result
                                _exe_cache_time[cache_key] = time.time()
                                return result
        except Exception:
            pass

        # 2. Buscar exe directo en subcarpetas de Autodesk, Adobe, etc.
        known_vendors = []
        if "autocad" in nombre_lower or "revit" in nombre_lower:
            known_vendors = ["Autodesk"]
        elif "photoshop" in nombre_lower or "illustrator" in nombre_lower:
            known_vendors = ["Adobe"]
        elif "chrome" in nombre_lower:
            known_vendors = ["Google"]

        for vendor in known_vendors:
            search_dirs = [
                os.path.join(os.environ.get("ProgramFiles", "C:\\Program Files"), vendor),
                os.path.join(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"), vendor),
            ]
            for base_dir in search_dirs:
                if not os.path.exists(base_dir):
                    continue
                for root, dirs, files in os.walk(base_dir):
                    level = root.replace(base_dir, "").count(os.sep)
                    if level > 4:
                        dirs.clear()
                        continue
                    for f in files:
                        f_lower = f.lower()
                        if f_lower.endswith(".exe") and (
                            exe_name in f_lower or nombre_lower in f_lower
                        ):
                            result = os.path.join(root, f)
                            _exe_cache[cache_key] = result
                            _exe_cache_time[cache_key] = time.time()
                            return result

        # 3. Buscar en Program Files con where (lento, ultimo recurso)
        search_dirs = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        ]
        for base_dir in search_dirs:
            if not os.path.exists(base_dir):
                continue
            # Buscar por el nombre real del exe (alias)
            where_cmd = f'where /r "{base_dir}" *{exe_name}*.exe'
            where_result = ejecutar_comando(where_cmd)
            if where_result and where_result != "(sin salida)" and "ERROR" not in where_result:
                exes = [line.strip() for line in where_result.split('\n')
                        if line.strip() and line.strip().endswith(".exe")]
                if exes:
                    result = exes[0]
                    _exe_cache[cache_key] = result
                    _exe_cache_time[cache_key] = time.time()
                    return result

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
    app_clean = sanitize_input(app_clean)

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
        return f"No encontre '{app}' en tu computadora.\nSugerencia: Ejecuta 'dir /s /b \"C:\\Program Files\\Autodesk\\acad.exe\"' para buscar la ruta exacta."
    return resultado


def buscar_youtube(consulta: str) -> str:
    """Busca un video en YouTube y lo abre en el navegador."""
    import urllib.parse
    consulta_clean = sanitize_input(strip_prefixes(consulta))
    encoded = urllib.parse.quote(consulta_clean)
    url = f"https://www.youtube.com/results?search_query={encoded}"

    resultado = open_in_browser(url, ejecutar_comando_fn=ejecutar_comando)
    if not resultado or resultado == "(sin salida)" or "error" not in resultado.lower():
        return f"Buscando '{consulta_clean}' en YouTube."
    return f"Abriendo YouTube con la busqueda: {consulta_clean}"
