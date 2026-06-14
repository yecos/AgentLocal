"""
=============================================================
AGENTE v16 - Edicion Incremental de Archivos
=============================================================
Permite editar archivos de forma incremental usando
search-and-replace, edicion por lineas, y diffs.

En vez de reescribir todo el archivo, puede:
- Buscar y reemplazar texto especifico
- Insertar antes/despues de una linea
- Reemplazar un rango de lineas
- Mostrar diff antes de aplicar cambios
- Rollback si la edicion falla

v16: Edicion precisa sin reescribir archivos completos.
=============================================================
"""

import os
import re
import difflib
import shutil
import logging
from datetime import datetime
from typing import Optional

from config import REPOS_DIR, logger
from utils.security import validate_path

# ============================================================
# BACKUP / ROLLBACK
# ============================================================

_BACKUP_DIR = os.path.join(REPOS_DIR, ".backups")


def _ensure_backup_dir():
    """Asegura que el directorio de backups existe."""
    os.makedirs(_BACKUP_DIR, exist_ok=True)


def _backup_file(filepath: str) -> str:
    """Crea un backup de un archivo antes de editarlo.

    Args:
        filepath: Ruta del archivo

    Returns:
        Ruta del backup creado
    """
    _ensure_backup_dir()
    if not os.path.exists(filepath):
        return ""

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    basename = os.path.basename(filepath)
    backup_name = f"{basename}.{timestamp}.bak"
    backup_path = os.path.join(_BACKUP_DIR, backup_name)

    try:
        shutil.copy2(filepath, backup_path)
        logger.info(f"[FileEditor] Backup creado: {backup_path}")
        return backup_path
    except Exception as e:
        logger.error(f"[FileEditor] Error creando backup: {e}")
        return ""


def rollback_file(filepath: str) -> bool:
    """Restaura un archivo desde el backup mas reciente.

    Args:
        filepath: Ruta del archivo a restaurar

    Returns:
        True si se restauro exitosamente
    """
    _ensure_backup_dir()
    basename = os.path.basename(filepath)

    # Buscar el backup mas reciente
    backups = []
    for f in os.listdir(_BACKUP_DIR):
        if f.startswith(basename) and f.endswith(".bak"):
            backups.append(f)

    if not backups:
        logger.warning(f"[FileEditor] No hay backups para: {filepath}")
        return False

    # Ordenar por timestamp (el mas reciente al final)
    backups.sort()
    latest_backup = os.path.join(_BACKUP_DIR, backups[-1])

    try:
        shutil.copy2(latest_backup, filepath)
        logger.info(f"[FileEditor] Rollback exitoso: {filepath} <- {latest_backup}")
        return True
    except Exception as e:
        logger.error(f"[FileEditor] Error en rollback: {e}")
        return False


# ============================================================
# OPERACIONES DE EDICION
# ============================================================

def search_and_replace(filepath: str, search: str, replace: str,
                       use_regex: bool = False, case_sensitive: bool = True,
                       create_backup: bool = True, max_replacements: int = 0) -> dict:
    """Busca y reemplaza texto en un archivo.

    Args:
        filepath: Ruta del archivo
        search: Texto o patron a buscar
        replace: Texto de reemplazo
        use_regex: Usar expresiones regulares
        case_sensitive: Busqueda sensible a mayusculas
        create_backup: Crear backup antes de editar
        max_replacements: Maximo de reemplazos (0 = todos)

    Returns:
        Dict con success, replacements, diff, error
    """
    # Validar ruta
    validated_path = validate_path(filepath)
    if not validated_path:
        return {"success": False, "error": f"Ruta no permitida: {filepath}"}

    if not os.path.exists(validated_path):
        return {"success": False, "error": f"Archivo no encontrado: {filepath}"}

    try:
        # Leer contenido original
        with open(validated_path, "r", encoding="utf-8") as f:
            original = f.read()

        # Backup
        backup_path = ""
        if create_backup:
            backup_path = _backup_file(validated_path)

        # Buscar y reemplazar
        if use_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            if max_replacements > 0:
                modified = re.sub(search, replace, original, count=max_replacements, flags=flags)
            else:
                modified = re.sub(search, replace, original, flags=flags)
        else:
            # Busqueda literal
            if not case_sensitive:
                # Para busqueda insensible, usar regex escapado
                escaped = re.escape(search)
                if max_replacements > 0:
                    modified = re.sub(escaped, replace, original, count=max_replacements, flags=re.IGNORECASE)
                else:
                    modified = re.sub(escaped, replace, original, flags=re.IGNORECASE)
            else:
                if max_replacements > 0:
                    modified = original.replace(search, replace, max_replacements)
                else:
                    modified = original.replace(search, replace)

        # Verificar si hubo cambios
        if modified == original:
            return {
                "success": True,
                "replacements": 0,
                "diff": "",
                "message": "No se encontraron coincidencias para reemplazar",
            }

        # Contar reemplazos
        if use_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            count = len(re.findall(search, original, flags=flags))
        else:
            count = original.count(search)

        # Generar diff
        diff = _generate_diff(original, modified, filepath)

        # Escribir archivo modificado
        with open(validated_path, "w", encoding="utf-8") as f:
            f.write(modified)

        logger.info(f"[FileEditor] search_and_replace: {count} reemplazos en {filepath}")

        return {
            "success": True,
            "replacements": count,
            "diff": diff,
            "backup": backup_path,
            "message": f"{count} reemplazo(s) aplicado(s) en {filepath}",
        }

    except Exception as e:
        logger.error(f"[FileEditor] Error en search_and_replace: {e}")
        # Intentar rollback si se creo backup
        if create_backup and backup_path:
            rollback_file(validated_path)
        return {"success": False, "error": str(e)}


def edit_lines(filepath: str, start_line: int, end_line: int,
               new_content: str, create_backup: bool = True) -> dict:
    """Reemplaza un rango de lineas en un archivo.

    Args:
        filepath: Ruta del archivo
        start_line: Linea de inicio (1-indexed, inclusiva)
        end_line: Linea de fin (1-indexed, inclusiva)
        new_content: Nuevo contenido para el rango
        create_backup: Crear backup antes de editar

    Returns:
        Dict con success, diff, error
    """
    validated_path = validate_path(filepath)
    if not validated_path:
        return {"success": False, "error": f"Ruta no permitida: {filepath}"}

    if not os.path.exists(validated_path):
        return {"success": False, "error": f"Archivo no encontrado: {filepath}"}

    if start_line < 1 or end_line < start_line:
        return {"success": False, "error": f"Rango de lineas invalido: {start_line}-{end_line}"}

    try:
        with open(validated_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if start_line > len(lines):
            return {"success": False, "error": f"Linea {start_line} fuera de rango (archivo tiene {len(lines)} lineas)"}

        # Ajustar end_line si excede
        actual_end = min(end_line, len(lines))

        # Backup
        backup_path = ""
        if create_backup:
            backup_path = _backup_file(validated_path)

        # Generar diff antes de modificar
        original = "".join(lines)
        new_lines = new_content.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        modified_lines = lines[:start_line - 1] + new_lines + lines[actual_end:]
        modified = "".join(modified_lines)

        diff = _generate_diff(original, modified, filepath)

        # Escribir
        with open(validated_path, "w", encoding="utf-8") as f:
            f.write(modified)

        logger.info(f"[FileEditor] edit_lines: {filepath} lineas {start_line}-{actual_end}")

        return {
            "success": True,
            "diff": diff,
            "backup": backup_path,
            "lines_replaced": actual_end - start_line + 1,
            "message": f"Lineas {start_line}-{actual_end} reemplazadas en {filepath}",
        }

    except Exception as e:
        logger.error(f"[FileEditor] Error en edit_lines: {e}")
        return {"success": False, "error": str(e)}


def insert_at_line(filepath: str, line_number: int, content: str,
                   position: str = "after", create_backup: bool = True) -> dict:
    """Inserta contenido en una posicion especifica del archivo.

    Args:
        filepath: Ruta del archivo
        line_number: Numero de linea de referencia (1-indexed)
        content: Contenido a insertar
        position: "before" o "after" de la linea
        create_backup: Crear backup antes de editar

    Returns:
        Dict con success, diff, error
    """
    validated_path = validate_path(filepath)
    if not validated_path:
        return {"success": False, "error": f"Ruta no permitida: {filepath}"}

    if not os.path.exists(validated_path):
        return {"success": False, "error": f"Archivo no encontrado: {filepath}"}

    try:
        with open(validated_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if line_number < 1 or line_number > len(lines):
            return {"success": False, "error": f"Linea {line_number} fuera de rango"}

        backup_path = ""
        if create_backup:
            backup_path = _backup_file(validated_path)

        original = "".join(lines)
        new_lines = content.splitlines(keepends=True)
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"

        insert_index = line_number if position == "after" else line_number - 1
        modified_lines = lines[:insert_index] + new_lines + lines[insert_index:]
        modified = "".join(modified_lines)

        diff = _generate_diff(original, modified, filepath)

        with open(validated_path, "w", encoding="utf-8") as f:
            f.write(modified)

        logger.info(f"[FileEditor] insert_at_line: {filepath} en linea {line_number} ({position})")

        return {
            "success": True,
            "diff": diff,
            "backup": backup_path,
            "message": f"Contenido insertado {position} de linea {line_number} en {filepath}",
        }

    except Exception as e:
        logger.error(f"[FileEditor] Error en insert_at_line: {e}")
        return {"success": False, "error": str(e)}


def preview_diff(filepath: str, search: str = None, replace: str = None,
                 start_line: int = None, end_line: int = None,
                 new_content: str = None, use_regex: bool = False) -> dict:
    """Previsualiza el diff de una edicion sin aplicarla.

    Args:
        filepath: Ruta del archivo
        search: Texto a buscar (para search_and_replace)
        replace: Texto de reemplazo
        start_line: Linea inicio (para edit_lines)
        end_line: Linea fin
        new_content: Nuevo contenido
        use_regex: Usar regex

    Returns:
        Dict con diff, changes_count, error
    """
    validated_path = validate_path(filepath)
    if not validated_path or not os.path.exists(validated_path):
        return {"error": f"Archivo no encontrado: {filepath}"}

    try:
        with open(validated_path, "r", encoding="utf-8") as f:
            original = f.read()

        # Calcular contenido modificado segun tipo de edicion
        if search is not None and replace is not None:
            if use_regex:
                modified = re.sub(search, replace, original)
            else:
                modified = original.replace(search, replace)
        elif start_line is not None and end_line is not None and new_content is not None:
            lines = original.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            actual_end = min(end_line, len(lines))
            modified_lines = lines[:start_line - 1] + new_lines + lines[actual_end:]
            modified = "".join(modified_lines)
        else:
            return {"error": "Debe proporcionar search/replace o start_line/end_line/new_content"}

        diff = _generate_diff(original, modified, filepath)
        changes = sum(1 for line in diff.split("\n") if line.startswith("+") and not line.startswith("+++"))

        return {
            "diff": diff,
            "changes_count": changes,
            "has_changes": modified != original,
        }

    except Exception as e:
        return {"error": str(e)}


def show_file_info(filepath: str) -> dict:
    """Retorna informacion sobre un archivo util para editar.

    Args:
        filepath: Ruta del archivo

    Returns:
        Dict con line_count, size, last_lines, first_lines
    """
    validated_path = validate_path(filepath)
    if not validated_path or not os.path.exists(validated_path):
        return {"error": f"Archivo no encontrado: {filepath}"}

    try:
        stat = os.stat(validated_path)
        with open(validated_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        return {
            "path": validated_path,
            "size_bytes": stat.st_size,
            "line_count": len(lines),
            "first_10_lines": "".join(lines[:10]),
            "last_10_lines": "".join(lines[-10:]) if len(lines) > 10 else "",
            "encoding": "utf-8",
        }

    except Exception as e:
        return {"error": str(e)}


# ============================================================
# UTILIDADES
# ============================================================

def _generate_diff(original: str, modified: str, filepath: str = "") -> str:
    """Genera un diff unificado entre dos textos.

    Args:
        original: Texto original
        modified: Texto modificado
        filepath: Nombre del archivo para el header

    Returns:
        Diff en formato unificado
    """
    original_lines = original.splitlines(keepends=True)
    modified_lines = modified.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=f"a/{os.path.basename(filepath)}",
        tofile=f"b/{os.path.basename(filepath)}",
        lineterm="",
    )

    result = "\n".join(diff)

    # Truncar si es muy largo
    if len(result) > 3000:
        result = result[:3000] + "\n... [diff truncado]"

    return result
