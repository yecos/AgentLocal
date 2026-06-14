"""
=============================================================
AGENTE v16 - Herramienta Git Estructurada
=============================================================
Operaciones Git como herramienta de primera clase del agente.
No mas ejecutar_comando("git ...") — cada operacion es una
funcion tipada con validacion y parsing de salida.

Operaciones:
- git_status: Estado del repositorio
- git_diff: Cambios pendientes
- git_add: Agregar archivos al staging
- git_commit: Crear commit con mensaje generado o manual
- git_branch: Listar, crear, cambiar branches
- git_log: Historial de commits
- git_push / git_pull: Sincronizar con remoto
- git_stash: Guardar/restaurar cambios temporales

v16: Git como herramienta de primera clase.
=============================================================
"""

import os
import re
import json
import subprocess
import logging
from typing import Optional

from config import REPOS_DIR, logger
from utils.security import validate_path

# ============================================================
# UTILIDAD BASE
# ============================================================

def _run_git(args: list, cwd: str = None, timeout: int = 30) -> dict:
    """Ejecuta un comando git y retorna resultado estructurado.

    Args:
        args: Argumentos del comando git (sin 'git')
        cwd: Directorio de trabajo
        timeout: Timeout en segundos

    Returns:
        Dict con success, stdout, stderr, exit_code
    """
    cmd = ["git"] + args
    cwd = cwd or REPOS_DIR

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Git timeout", "exit_code": -1}
    except FileNotFoundError:
        return {"success": False, "stdout": "", "stderr": "Git no instalado", "exit_code": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "exit_code": -1}


def _is_git_repo(path: str) -> bool:
    """Verifica si un directorio es un repositorio git."""
    result = _run_git(["rev-parse", "--is-inside-work-tree"], cwd=path)
    return result["success"]


# ============================================================
# HERRAMIENTAS GIT
# ============================================================

def git_status(repo_path: str = None) -> dict:
    """Obtiene el estado del repositorio git.

    Args:
        repo_path: Ruta al repositorio (default: REPOS_DIR)

    Returns:
        Dict con branch, staged, unstaged, untracked, conflicted
    """
    path = repo_path or REPOS_DIR
    validated = validate_path(path)
    if not validated:
        return {"success": False, "error": f"Ruta no permitida: {path}"}

    if not _is_git_repo(validated):
        return {"success": False, "error": f"No es un repositorio git: {path}"}

    # Obtener branch actual
    branch_result = _run_git(["branch", "--show-current"], cwd=validated)
    current_branch = branch_result["stdout"] if branch_result["success"] else "unknown"

    # Obtener status porcelana
    status_result = _run_git(["status", "--porcelain=v2", "--branch"], cwd=validated)

    if not status_result["success"]:
        # Fallback a status normal
        status_result = _run_git(["status", "--short", "--branch"], cwd=validated)
        if not status_result["success"]:
            return {"success": False, "error": status_result["stderr"]}

    # Parsear status
    staged = []
    unstaged = []
    untracked = []
    conflicted = []

    for line in status_result["stdout"].split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.startswith("#"):
            continue

        # Formato corto: XY filename
        if len(line) >= 3:
            x = line[0]
            y = line[1] if len(line) > 2 else " "
            filename = line[3:].strip() if len(line) > 3 else line[2:].strip()

            if x == "?" or y == "?":
                untracked.append(filename)
            elif x == "!" or y == "!":
                pass  # ignored
            elif x == "U" or y == "U" or (x == "A" and y == "A") or (x == "D" and y == "D"):
                conflicted.append(filename)
            elif x != " " and x != "?":
                staged.append({"file": filename, "status": _status_code_to_text(x)})
            elif y != " " and y != "?":
                unstaged.append({"file": filename, "status": _status_code_to_text(y)})

    # Verificar si hay cambios sin commit
    has_changes = bool(staged or unstaged or untracked or conflicted)

    return {
        "success": True,
        "branch": current_branch,
        "staged": staged,
        "unstaged": unstaged,
        "untracked": untracked,
        "conflicted": conflicted,
        "has_changes": has_changes,
        "clean": not has_changes,
    }


def git_diff(repo_path: str = None, staged: bool = False,
             file_path: str = None) -> dict:
    """Obtiene el diff del repositorio.

    Args:
        repo_path: Ruta al repositorio
        staged: Mostrar solo cambios en staging
        file_path: Archivo especifico (opcional)

    Returns:
        Dict con diff, stats, files_changed
    """
    path = repo_path or REPOS_DIR
    validated = validate_path(path)
    if not validated:
        return {"success": False, "error": f"Ruta no permitida: {path}"}

    args = ["diff"]
    if staged:
        args.append("--staged")
    if file_path:
        args.append("--")
        args.append(file_path)

    result = _run_git(args, cwd=validated)
    if not result["success"]:
        return {"success": False, "error": result["stderr"]}

    # Obtener stats
    stat_args = ["diff", "--stat"]
    if staged:
        stat_args.append("--staged")
    if file_path:
        stat_args += ["--", file_path]

    stat_result = _run_git(stat_args, cwd=validated)
    stats = stat_result["stdout"] if stat_result["success"] else ""

    # Contar archivos cambiados
    files_changed = []
    for line in result["stdout"].split("\n"):
        if line.startswith("diff --git"):
            match = re.search(r'b/(.+)$', line)
            if match:
                files_changed.append(match.group(1))

    return {
        "success": True,
        "diff": result["stdout"][:5000],  # Truncar si muy largo
        "stats": stats,
        "files_changed": files_changed,
        "has_changes": bool(result["stdout"]),
    }


def git_add(repo_path: str = None, files: list = None, all_changes: bool = False) -> dict:
    """Agrega archivos al staging area.

    Args:
        repo_path: Ruta al repositorio
        files: Lista de archivos a agregar
        all_changes: Agregar todos los cambios

    Returns:
        Dict con success, files_added, message
    """
    path = repo_path or REPOS_DIR
    validated = validate_path(path)
    if not validated:
        return {"success": False, "error": f"Ruta no permitida: {path}"}

    args = ["add"]
    if all_changes:
        args.append("-A")
    elif files:
        args.extend(files)
    else:
        args.append("-A")  # Default: agregar todo

    result = _run_git(args, cwd=validated)

    if result["success"]:
        # Verificar que se agrego
        status = git_status(validated)
        return {
            "success": True,
            "message": "Archivos agregados al staging area",
            "staged_files": status.get("staged", []),
        }
    else:
        return {"success": False, "error": result["stderr"]}


def git_commit(repo_path: str = None, message: str = None,
               auto_message: bool = False, add_all: bool = False) -> dict:
    """Crea un commit.

    Args:
        repo_path: Ruta al repositorio
        message: Mensaje del commit
        auto_message: Generar mensaje automaticamente
        add_all: Agregar todos los cambios antes de commit

    Returns:
        Dict con success, commit_hash, message, files_changed
    """
    path = repo_path or REPOS_DIR
    validated = validate_path(path)
    if not validated:
        return {"success": False, "error": f"Ruta no permitida: {path}"}

    # Agregar cambios si se solicita
    if add_all:
        add_result = git_add(validated, all_changes=True)
        if not add_result["success"]:
            return add_result

    # Generar mensaje automatico si se solicita
    if auto_message or not message:
        diff_result = git_diff(validated, staged=True)
        if diff_result["success"] and diff_result["has_changes"]:
            files = diff_result.get("files_changed", [])
            if len(files) == 1:
                message = f"Update {files[0]}"
            elif len(files) <= 3:
                message = f"Update {', '.join(files)}"
            else:
                message = f"Update {len(files)} files"
        else:
            message = "Auto commit"

    # Crear commit
    result = _run_git(["commit", "-m", message], cwd=validated)

    if result["success"]:
        # Obtener hash del commit
        hash_result = _run_git(["rev-parse", "HEAD"], cwd=validated)
        commit_hash = hash_result["stdout"][:8] if hash_result["success"] else "unknown"

        return {
            "success": True,
            "commit_hash": commit_hash,
            "message": message,
            "output": result["stdout"],
        }
    else:
        # Puede ser que no haya nada para commitear
        if "nothing to commit" in result["stdout"]:
            return {
                "success": True,
                "message": "No hay cambios para commitear",
                "commit_hash": None,
            }
        return {"success": False, "error": result["stderr"]}


def git_branch(repo_path: str = None, action: str = "list",
               branch_name: str = None) -> dict:
    """Gestiona branches del repositorio.

    Args:
        repo_path: Ruta al repositorio
        action: "list", "create", "switch", "delete"
        branch_name: Nombre del branch (para create/switch/delete)

    Returns:
        Dict con success, branches, current_branch, message
    """
    path = repo_path or REPOS_DIR
    validated = validate_path(path)
    if not validated:
        return {"success": False, "error": f"Ruta no permitida: {path}"}

    if action == "list":
        result = _run_git(["branch", "-a", "--no-color"], cwd=validated)
        if not result["success"]:
            return {"success": False, "error": result["stderr"]}

        branches = []
        current = ""
        for line in result["stdout"].split("\n"):
            line = line.strip()
            if not line:
                continue
            is_current = line.startswith("*")
            name = line.lstrip("* ").strip()
            branches.append({"name": name, "is_current": is_current, "is_remote": "remotes/" in name})
            if is_current:
                current = name

        return {"success": True, "branches": branches, "current_branch": current}

    elif action == "create":
        if not branch_name:
            return {"success": False, "error": "Nombre de branch requerido"}
        result = _run_git(["checkout", "-b", branch_name], cwd=validated)
        return {
            "success": result["success"],
            "message": f"Branch '{branch_name}' creada y activada" if result["success"] else result["stderr"],
        }

    elif action == "switch":
        if not branch_name:
            return {"success": False, "error": "Nombre de branch requerido"}
        result = _run_git(["checkout", branch_name], cwd=validated)
        return {
            "success": result["success"],
            "message": f"Cambiado a branch '{branch_name}'" if result["success"] else result["stderr"],
        }

    elif action == "delete":
        if not branch_name:
            return {"success": False, "error": "Nombre de branch requerido"}
        result = _run_git(["branch", "-d", branch_name], cwd=validated)
        return {
            "success": result["success"],
            "message": f"Branch '{branch_name}' eliminada" if result["success"] else result["stderr"],
        }

    else:
        return {"success": False, "error": f"Accion no soportada: {action}"}


def git_log(repo_path: str = None, count: int = 10,
            file_path: str = None, oneline: bool = True) -> dict:
    """Obtiene el historial de commits.

    Args:
        repo_path: Ruta al repositorio
        count: Numero de commits a mostrar
        file_path: Filtrar por archivo
        oneline: Formato compacto

    Returns:
        Dict con success, commits, total
    """
    path = repo_path or REPOS_DIR
    validated = validate_path(path)
    if not validated:
        return {"success": False, "error": f"Ruta no permitida: {path}"}

    args = ["log", f"-{count}", "--no-color"]
    if oneline:
        args.append("--oneline")
    else:
        args.extend(["--format=%H|%an|%ae|%ai|%s"])

    if file_path:
        args.extend(["--", file_path])

    result = _run_git(args, cwd=validated)
    if not result["success"]:
        return {"success": False, "error": result["stderr"]}

    # Parsear commits
    commits = []
    for line in result["stdout"].split("\n"):
        line = line.strip()
        if not line:
            continue
        if oneline:
            # Formato: hash message
            parts = line.split(" ", 1)
            commits.append({
                "hash": parts[0] if parts else "",
                "message": parts[1] if len(parts) > 1 else "",
            })
        else:
            # Formato: hash|author|email|date|subject
            parts = line.split("|", 4)
            if len(parts) >= 5:
                commits.append({
                    "hash": parts[0][:8],
                    "author": parts[1],
                    "email": parts[2],
                    "date": parts[3],
                    "message": parts[4],
                })

    return {"success": True, "commits": commits, "total": len(commits)}


def git_push(repo_path: str = None, remote: str = "origin",
             branch: str = None, force: bool = False) -> dict:
    """Push al repositorio remoto.

    Args:
        repo_path: Ruta al repositorio
        remote: Nombre del remoto
        branch: Branch a push (default: actual)
        force: Force push

    Returns:
        Dict con success, message
    """
    path = repo_path or REPOS_DIR
    validated = validate_path(path)
    if not validated:
        return {"success": False, "error": f"Ruta no permitida: {path}"}

    args = ["push", remote]
    if branch:
        args.append(branch)
    if force:
        args.append("--force-with-lease")

    result = _run_git(args, cwd=validated, timeout=60)

    if result["success"]:
        return {"success": True, "message": f"Push exitoso a {remote}" + (f"/{branch}" if branch else "")}
    else:
        return {"success": False, "error": result["stderr"] or result["stdout"]}


def git_pull(repo_path: str = None, remote: str = "origin",
             branch: str = None) -> dict:
    """Pull del repositorio remoto.

    Args:
        repo_path: Ruta al repositorio
        remote: Nombre del remoto
        branch: Branch a pull

    Returns:
        Dict con success, message
    """
    path = repo_path or REPOS_DIR
    validated = validate_path(path)
    if not validated:
        return {"success": False, "error": f"Ruta no permitida: {path}"}

    args = ["pull", remote]
    if branch:
        args.append(branch)

    result = _run_git(args, cwd=validated, timeout=60)

    if result["success"]:
        return {"success": True, "message": result["stdout"] or "Pull exitoso"}
    else:
        return {"success": False, "error": result["stderr"] or result["stdout"]}


def git_stash(repo_path: str = None, action: str = "save",
              message: str = "") -> dict:
    """Gestiona el stash del repositorio.

    Args:
        repo_path: Ruta al repositorio
        action: "save", "list", "pop", "drop"
        message: Mensaje del stash (para save)

    Returns:
        Dict con success, message, stashes
    """
    path = repo_path or REPOS_DIR
    validated = validate_path(path)
    if not validated:
        return {"success": False, "error": f"Ruta no permitida: {path}"}

    if action == "save":
        args = ["stash", "save"]
        if message:
            args.append(message)
        result = _run_git(args, cwd=validated)
        return {
            "success": result["success"],
            "message": "Cambios guardados en stash" if result["success"] else result["stderr"],
        }

    elif action == "list":
        result = _run_git(["stash", "list"], cwd=validated)
        stashes = []
        for line in result["stdout"].split("\n"):
            if line.strip():
                stashes.append(line.strip())
        return {"success": True, "stashes": stashes}

    elif action == "pop":
        result = _run_git(["stash", "pop"], cwd=validated)
        return {
            "success": result["success"],
            "message": "Stash restaurado" if result["success"] else result["stderr"],
        }

    elif action == "drop":
        result = _run_git(["stash", "drop"], cwd=validated)
        return {
            "success": result["success"],
            "message": "Stash eliminado" if result["success"] else result["stderr"],
        }

    else:
        return {"success": False, "error": f"Accion no soportada: {action}"}


def git_init(repo_path: str = None) -> dict:
    """Inicializa un repositorio git.

    Args:
        repo_path: Ruta donde inicializar

    Returns:
        Dict con success, message
    """
    path = repo_path or REPOS_DIR
    validated = validate_path(path)
    if not validated:
        return {"success": False, "error": f"Ruta no permitida: {path}"}

    result = _run_git(["init"], cwd=validated)
    if result["success"]:
        return {"success": True, "message": f"Repositorio inicializado en {path}"}
    return {"success": False, "error": result["stderr"]}


# ============================================================
# UTILIDADES
# ============================================================

def _status_code_to_text(code: str) -> str:
    """Convierte codigo de status git a texto legible."""
    status_map = {
        "M": "modified",
        "A": "added",
        "D": "deleted",
        "R": "renamed",
        "C": "copied",
        "U": "unmerged",
        "?": "untracked",
        "!": "ignored",
    }
    return status_map.get(code, f"unknown({code})")
