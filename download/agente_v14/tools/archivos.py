"""
=============================================================
AGENTE v14 - Herramientas de Archivos
=============================================================
leer_archivo, escribir_archivo, listar_archivos, buscar_en_archivos
=============================================================
"""

import os
import platform

from config import REPOS_DIR, MAX_FILE_READ, MAX_TOOL_OUTPUT, IS_WINDOWS
from utils.security import validate_path, sanitize_input
from tools.sistema import ejecutar_comando


def leer_archivo(ruta: str) -> str:
    """Lee el contenido de un archivo con validacion de path traversal."""
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    rutas_posibles = [ruta]
    if not os.path.isabs(ruta):
        rutas_posibles.append(os.path.join(REPOS_DIR, ruta))
        try:
            for d in os.listdir(REPOS_DIR):
                rutas_posibles.append(os.path.join(REPOS_DIR, d, ruta))
        except OSError:
            pass

    for r in rutas_posibles:
        if os.path.exists(r) and os.path.isfile(r):
            try:
                with open(r, "r", encoding="utf-8", errors="replace") as f:
                    contenido = f.read()
                if len(contenido) > MAX_FILE_READ:
                    contenido = contenido[:MAX_FILE_READ] + "\n... [truncado]"
                return contenido
            except (OSError, UnicodeDecodeError) as e:
                return f"ERROR leyendo: {e}"
    return f"Archivo no encontrado: {ruta}"


def escribir_archivo(ruta: str, contenido: str) -> str:
    """Crea o modifica un archivo con contenido especifico."""
    validation = validate_path(ruta)
    if validation != ruta:
        return validation

    try:
        dir_name = os.path.dirname(ruta)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(contenido)
        return f"Archivo escrito: {ruta}"
    except OSError as e:
        return f"ERROR: {e}"


def listar_archivos(ruta: str = None) -> str:
    """Lista archivos y carpetas de un directorio."""
    if ruta is None:
        ruta = REPOS_DIR
    if not os.path.exists(ruta):
        alt = os.path.join(REPOS_DIR, ruta) if not os.path.isabs(ruta) else ruta
        if os.path.exists(alt):
            ruta = alt
        else:
            return f"Directorio no existe: {ruta}"
    try:
        items = os.listdir(ruta)
        carpetas = sorted([f for f in items if os.path.isdir(os.path.join(ruta, f))])
        archivos = sorted([f for f in items if os.path.isfile(os.path.join(ruta, f))])
        resultado = f"Contenido de {ruta}:\n"
        for c in carpetas:
            resultado += f"  [CARPETA] {c}\n"
        for a in archivos:
            resultado += f"  [ARCHIVO] {a}\n"
        resultado += f"Total: {len(carpetas)} carpetas, {len(archivos)} archivos"
        return resultado
    except OSError as e:
        return f"ERROR: {e}"


def buscar_en_archivos(ruta: str, patron: str) -> str:
    """Busca texto dentro de archivos (como grep/findstr)."""
    # Sanitizar patron para prevenir inyeccion
    patron = sanitize_input(patron)
    if IS_WINDOWS:
        return ejecutar_comando(f'findstr /s /i /n "{patron}" "{ruta}\\*"')
    else:
        return ejecutar_comando(
            f'grep -rn "{patron}" "{ruta}" '
            f'--include="*.py" --include="*.js" --include="*.html" '
            f'--include="*.ts" --include="*.json" 2>/dev/null | head -50'
        )
