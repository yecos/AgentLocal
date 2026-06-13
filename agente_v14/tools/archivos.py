"""
=============================================================
AGENTE v14 - Herramientas de Archivos (Mejoradas)
=============================================================
leer_archivo, escribir_archivo, listar_archivos, buscar_en_archivos
v14.5: ripgrep como motor primario (10-100x mas rapido que grep).
       Extensiones ampliadas, exclusiones inteligentes.
=============================================================
"""

import os
import platform

from config import REPOS_DIR, MAX_FILE_READ, MAX_TOOL_OUTPUT, IS_WINDOWS
from utils.security import validate_path, sanitize_input
from tools.sistema import ejecutar_comando

# Extensiones soportadas (ampliadas)
SEARCH_EXTENSIONS = [
    # Código
    "*.py", "*.js", "*.ts", "*.tsx", "*.jsx", "*.html", "*.css", "*.scss",
    "*.less", "*.json", "*.yaml", "*.yml", "*.toml", "*.cfg", "*.ini",
    "*.sh", "*.bat", "*.ps1", "*.sql",
    # Lenguajes adicionales
    "*.rs", "*.go", "*.java", "*.rb", "*.php", "*.swift", "*.kt", "*.c",
    "*.cpp", "*.h", "*.hpp", "*.cs", "*.scala",
    # Frontend
    "*.vue", "*.svelte", "*.astro",
    # Datos y docs
    "*.md", "*.txt", "*.csv", "*.xml", "*.env", "*.log",
    # Config
    "*.dockerfile", "*.makefile", "*.cmake",
]

# Directorios a excluir siempre
EXCLUDE_DIRS = [
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "dist", "build", ".next", ".nuxt", ".cache",
    ".idea", ".vscode", "*.egg-info",
]


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
    """Busca texto dentro de archivos usando ripgrep (primero) o grep (fallback).

    v14.5: ripgrep es 10-100x mas rapido que grep y excluye
    automaticamente .git, node_modules, etc.
    Extensiones de busqueda ampliadas significativamente.
    """
    # Sanitizar patron para prevenir inyeccion
    patron = sanitize_input(patron)

    if IS_WINDOWS:
        # Windows: usar findstr como fallback
        return _search_windows(ruta, patron)

    # Intentar ripgrep primero (mucho mas rapido y completo)
    result = _search_ripgrep(ruta, patron)
    if result is not None:
        return result

    # Fallback a grep mejorado
    return _search_grep(ruta, patron)


def _search_ripgrep(ruta: str, patron: str) -> str:
    """Busqueda usando ripgrep (rg). Retorna None si rg no esta disponible."""
    # Construir lista de exclusiones
    exclude_args = " ".join(f'--glob "!{d}/**"' for d in EXCLUDE_DIRS)

    # Construir lista de extensiones (type list)
    type_args = " ".join(f"-t {ext.lstrip('*.')}" for ext in SEARCH_EXTENSIONS[:20])

    rg_cmd = (
        f'rg --max-count 50 --line-number --color never '
        f'--max-depth 10 --smart-case '
        f'{exclude_args} '
        f'{type_args} '
        f'"{patron}" "{ruta}" 2>/dev/null'
    )

    try:
        result = ejecutar_comando(rg_cmd)
        if result and "command not found" not in result.lower() and "no such file" not in result.lower():
            return result
    except Exception as e:
        logger.debug(f"ripgrep fallo: {e}")

    # Segundo intento: rg sin type filters (mas permisivo)
    rg_cmd_simple = (
        f'rg --max-count 50 --line-number --color never '
        f'--max-depth 10 --smart-case '
        f'{exclude_args} '
        f'"{patron}" "{ruta}" 2>/dev/null'
    )

    try:
        result = ejecutar_comando(rg_cmd_simple)
        if result and "command not found" not in result.lower():
            return result
    except Exception:
        pass

    return None


def _search_grep(ruta: str, patron: str) -> str:
    """Fallback: busqueda usando grep con extensiones ampliadas."""
    include_args = " ".join(f'--include="{ext}"' for ext in SEARCH_EXTENSIONS)

    grep_cmd = (
        f'grep -rn "{patron}" "{ruta}" '
        f'{include_args} '
        f'2>/dev/null | head -50'
    )
    return ejecutar_comando(grep_cmd)


def _search_windows(ruta: str, patron: str) -> str:
    """Busqueda en Windows usando findstr."""
    return ejecutar_comando(f'findstr /s /i /n "{patron}" "{ruta}\\*"')
