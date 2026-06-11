"""
=============================================================
AGENTE v14 - Helpers Compartidos
=============================================================
Funciones utilitarias usadas por multiples modulos.
=============================================================
"""

import platform

from config import IS_WINDOWS, IS_MAC


def strip_prefixes(text: str) -> str:
    """Elimina prefijos comunes de comandos de voz/texto."""
    text = text.strip()
    prefixes = [
        "abre ", "abrir ", "open ", "inicia ", "lanza ", "mi ",
        "ve a ", "ir a ", "navega a ", "busca ", "buscar ",
        "pon ", "ponme ", "reproduce "
    ]
    for prefix in prefixes:
        if text.lower().startswith(prefix):
            text = text[len(prefix):]
            break
    return text.strip()


def open_in_browser(url: str, ejecutar_comando_fn=None) -> str:
    """Abre una URL en el navegador por defecto. Multi-plataforma.
    Requiere la funcion ejecutar_comando como parametro para evitar import circular.
    """
    if ejecutar_comando_fn is None:
        # Fallback: import directo (solo si es necesario)
        from tools.sistema import ejecutar_comando
        ejecutar_comando_fn = ejecutar_comando

    if IS_WINDOWS:
        return ejecutar_comando_fn(f'start "" "{url}"')
    elif IS_MAC:
        return ejecutar_comando_fn(f'open "{url}"')
    else:
        return ejecutar_comando_fn(f'xdg-open "{url}"')


def safe_read_file(filepath, max_chars=2000):
    """Lee un archivo de forma segura, truncando si es necesario."""
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(max_chars)
        return content
    except (OSError, UnicodeDecodeError):
        return ""


def resolve_project_path(ruta, repos_dir):
    """Resuelve una ruta de proyecto, buscando en REPOS_DIR si es relativa."""
    if os.path.exists(ruta):
        return ruta
    if not os.path.isabs(ruta):
        alt = os.path.join(repos_dir, ruta)
        if os.path.exists(alt):
            return alt
    return None


import os
