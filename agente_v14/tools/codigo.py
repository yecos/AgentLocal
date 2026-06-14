"""
=============================================================
AGENTE v14 - Herramienta de Generacion de Codigo
=============================================================
generar_codigo: Usa el LLM para generar codigo y lo guarda en archivo.
v14.8: Seguridad mejorada
       - Validacion de sintaxis antes de escribir (Python: compile(),
         JS/TS: balance de llaves/parentesis)
       - Backup antes de sobreescribir (.bak, .bak.1, .bak.2)
       - Limpieza automatica de backups antiguos (max 3)
=============================================================
"""

import os
import re
import shutil
import logging

from config import REPOS_DIR, CODE_GEN_PROMPTS, CODE_EXT_MAP, IS_WINDOWS, logger
from tools.archivos import escribir_archivo
from tools.sistema import ejecutar_comando
from llm import ollama

# Max backup versions to keep
MAX_BACKUP_VERSIONS = 3


def _validate_python_syntax(content: str) -> tuple[bool, str]:
    """Validate Python code syntax using compile().

    Returns:
        (is_valid, error_message) tuple. If valid, error_message is empty.
    """
    try:
        compile(content, '<string>', 'exec')
        return True, ""
    except SyntaxError as e:
        line_info = f"linea {e.lineno}" if e.lineno else "linea desconocida"
        detail = f"{e.msg} en {line_info}"
        if e.text:
            detail += f"\n  {e.text.strip()}"
            if e.offset:
                detail += f"\n  {' ' * (e.offset - 1)}^"
        return False, f"Error de sintaxis Python: {detail}"


def _validate_js_ts_syntax(content: str) -> tuple[bool, str]:
    """Basic syntax check for JS/TS files: matching braces, parens, brackets.

    Returns:
        (is_valid, error_message) tuple. If valid, error_message is empty.
    """
    stack = []
    pairs = {'(': ')', '[': ']', '{': '}'}
    openers = set(pairs.keys())
    closers = set(pairs.values())

    # Track line numbers for error reporting
    for line_num, line in enumerate(content.split('\n'), 1):
        # Skip string literals and comments (basic heuristic)
        i = 0
        while i < len(line):
            ch = line[i]

            # Skip single-line comments
            if ch == '/' and i + 1 < len(line) and line[i + 1] == '/':
                break

            # Skip string literals
            if ch in ('"', "'", '`'):
                quote = ch
                i += 1
                while i < len(line):
                    if line[i] == '\\':
                        i += 2  # Skip escaped char
                        continue
                    if line[i] == quote:
                        break
                    i += 1
                i += 1
                continue

            if ch in openers:
                stack.append((ch, line_num))
            elif ch in closers:
                if not stack:
                    return False, f"Parentesis/llave/corchete de cierre '{ch}' sin apertura en linea {line_num}"
                last_opener, opener_line = stack.pop()
                if pairs[last_opener] != ch:
                    return False, (f"Desbalance: '{last_opener}' en linea {opener_line} "
                                  f"cerrado con '{ch}' en linea {line_num}")

            i += 1

    if stack:
        opener, line_num = stack[-1]
        return False, f"Parentesis/llave/corchete '{opener}' sin cerrar (abierto en linea {line_num})"

    return True, ""


def _validate_code_syntax(content: str, filepath: str) -> tuple[bool, str]:
    """Validate code syntax based on file extension.

    Returns:
        (is_valid, error_message) tuple. If valid, error_message is empty.
    """
    ext = os.path.splitext(filepath)[1].lower()

    if ext == '.py':
        return _validate_python_syntax(content)
    elif ext in ('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs'):
        return _validate_js_ts_syntax(content)

    # For other file types, no syntax validation
    return True, ""


def _rotate_backups(filepath: str) -> None:
    """Rotate backup files, keeping at most MAX_BACKUP_VERSIONS.

    Rotation order: .bak.2 -> deleted, .bak.1 -> .bak.2, .bak -> .bak.1
    """
    # Delete the oldest backup if it exists
    oldest = f"{filepath}.bak.{MAX_BACKUP_VERSIONS - 1}"
    if os.path.exists(oldest):
        try:
            os.remove(oldest)
        except OSError:
            pass

    # Shift existing backups up
    for i in range(MAX_BACKUP_VERSIONS - 2, 0, -1):
        src = f"{filepath}.bak.{i}" if i > 0 else f"{filepath}.bak"
        dst = f"{filepath}.bak.{i + 1}"
        if os.path.exists(src):
            try:
                shutil.move(src, dst)
            except OSError:
                pass

    # Move .bak to .bak.1
    bak_path = f"{filepath}.bak"
    bak1_path = f"{filepath}.bak.1"
    if os.path.exists(bak_path):
        try:
            shutil.move(bak_path, bak1_path)
        except OSError:
            pass


def _create_backup(filepath: str) -> bool:
    """Create a backup of the file before overwriting.

    Uses .bak, .bak.1, .bak.2 rotation. Keeps max 3 backup versions.

    Returns:
        True if backup was created, False otherwise.
    """
    if not os.path.exists(filepath):
        return False  # No existing file to backup

    # Rotate existing backups first
    _rotate_backups(filepath)

    # Create the .bak backup
    bak_path = f"{filepath}.bak"
    try:
        shutil.copy2(filepath, bak_path)
        logger.debug(f"Backup creado: {bak_path}")
        return True
    except OSError as e:
        logger.warning(f"No se pudo crear backup de {filepath}: {e}")
        return False


def generar_codigo(descripcion: str, tipo: str, ruta: str = "") -> str:
    """Genera codigo/texto completo usando el LLM y lo guarda en un archivo."""
    if not ruta:
        ext = CODE_EXT_MAP.get(tipo, ".txt")
        safe_name = re.sub(r'[^a-z0-9]', '_', descripcion[:30].lower()).strip('_')
        ruta = os.path.join(REPOS_DIR, f"{safe_name}{ext}")
    else:
        ruta = ruta.replace("REPOS_DIR", REPOS_DIR)

    system_prompt = CODE_GEN_PROMPTS.get(tipo, "Genera contenido completo y funcional. Responde SOLO con el contenido.")

    # Usar modelo de codigo (potente)
    contenido = ollama.generate_code([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Crea: {descripcion}"}
    ])

    if not contenido:
        return "ERROR: No se pudo generar contenido (Ollama no responde)"

    # Limpiar markdown code blocks
    contenido = contenido.strip()
    if contenido.startswith("```"):
        contenido = re.sub(r'^```[a-z]*\n?', '', contenido)
        contenido = re.sub(r'\n?```$', '', contenido)
        contenido = contenido.strip()

    # Validate syntax before writing
    is_valid, error_msg = _validate_code_syntax(contenido, ruta)
    if not is_valid:
        return (f"ERROR: El codigo generado tiene errores de sintaxis y NO fue guardado.\n"
                f"{error_msg}\n\n"
                f"Intenta de nuevo o revisa la descripcion del codigo.")

    # Create backup if overwriting an existing file
    if os.path.exists(ruta):
        backup_created = _create_backup(ruta)
        if backup_created:
            logger.info(f"Backup creado antes de sobreescribir: {ruta}")

    resultado = escribir_archivo(ruta, contenido)
    if "ERROR" in resultado:
        return resultado

    # Si es HTML, abrir en navegador
    if tipo == "html" and IS_WINDOWS:
        ejecutar_comando(f'start "" "{ruta}"')
        return f"Contenido generado y guardado en: {ruta}\nAbierto en el navegador automaticamente!"

    size_kb = len(contenido) / 1024
    return f"Contenido generado ({size_kb:.1f}KB) y guardado en: {ruta}"
