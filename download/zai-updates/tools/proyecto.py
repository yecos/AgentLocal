"""
proyecto.py — Herramientas de gestión de proyectos para ZAI
Cambio: integración de `sanitize_input` en todos los inputs y
`validate_url` para validar URLs de repositorios antes de clonar.
"""

from __future__ import annotations

import subprocess
import os
import logging
import re
from typing import Optional, Dict, List, Any

from utils.security import sanitize_input, sanitize_shell_arg, is_safe_command, validate_url

logger = logging.getLogger(__name__)


# ====================================================================== #
#  Herramientas de proyecto                                               #
# ====================================================================== #

def clonar_repositorio(url: str, destino: str = "./projects") -> Dict[str, Any]:
    """
    Clona un repositorio Git desde una URL.

    Parámetros
    ----------
    url : str
        URL del repositorio (HTTPS o SSH).
    destino : str
        Directorio donde clonar.

    Retorna
    -------
    dict con resultado de la clonación.
    """
    # ── Sanitizar inputs ──
    url = sanitize_input(url)
    destino = sanitize_input(destino)

    if not url:
        return {"error": "URL del repositorio vacía"}

    # ── Validar URL ──
    # Permitir URLs HTTPS y SSH de git
    es_url_valida = False

    # URLs HTTPS
    if url.startswith("https://") or url.startswith("http://"):
        if not validate_url(url):
            return {"error": f"URL no válida o protocolo no permitido: {url[:100]}"}
        es_url_valida = True

    # URLs SSH de Git (git@host:user/repo.git)
    if re.match(r"^git@[a-zA-Z0-9.-]+:[a-zA-Z0-9._/-]+\.git$", url):
        es_url_valida = True

    # URLs de protocolo Git (git://)
    if url.startswith("git://"):
        # Validar formato básico
        if re.match(r"^git://[a-zA-Z0-9.-]+/[a-zA-Z0-9._/-]+\.git$", url):
            es_url_valida = True
        else:
            return {"error": f"URL Git con formato inválido: {url[:100]}"}

    if not es_url_valida:
        return {
            "error": (
                f"URL de repositorio no válida: {url[:100]}. "
                f"Usar HTTPS (https://github.com/user/repo.git), "
                f"SSH (git@github.com:user/repo.git) o "
                f"Git protocol (git://...)."
            )
        }

    # ── Verificar seguridad ──
    if not is_safe_command(f"git clone {url}"):
        return {"error": "Clonación bloqueada por políticas de seguridad"}

    # ── Crear directorio de destino ──
    try:
        os.makedirs(destino, exist_ok=True)
    except OSError as exc:
        return {"error": f"Error creando directorio {destino}: {exc}"}

    # ── Clonar ──
    try:
        cmd = ["git", "clone", url, destino]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )

        if result.returncode == 0:
            logger.info("Repositorio clonado: %s → %s", url, destino)
            return {
                "exito": True,
                "mensaje": f"Repositorio clonado en {destino}",
                "url": url,
                "destino": destino,
            }
        else:
            return {
                "exito": False,
                "error": result.stderr[:500],
            }

    except subprocess.TimeoutExpired:
        return {"error": "Timeout clonando repositorio"}
    except Exception as exc:
        return {"error": str(exc)}


def estado_repositorio(ruta: str = ".") -> Dict[str, Any]:
    """
    Muestra el estado de un repositorio Git.

    Parámetros
    ----------
    ruta : str
        Ruta al repositorio.

    Retorna
    -------
    dict con el estado del repositorio.
    """
    ruta = sanitize_input(ruta)
    ruta = sanitize_shell_arg(ruta)

    if not os.path.isdir(ruta):
        return {"error": f"Directorio no encontrado: {ruta}"}

    if not os.path.isdir(os.path.join(ruta, ".git")):
        return {"error": f"No es un repositorio Git: {ruta}"}

    try:
        # git status
        result = subprocess.run(
            ["git", "-C", ruta, "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        status = result.stdout.strip()

        # git branch
        result = subprocess.run(
            ["git", "-C", ruta, "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        branch = result.stdout.strip()

        # git log (último commit)
        result = subprocess.run(
            ["git", "-C", ruta, "log", "-1", "--oneline"],
            capture_output=True, text=True, timeout=5,
        )
        last_commit = result.stdout.strip()

        # git remote
        result = subprocess.run(
            ["git", "-C", ruta, "remote", "-v"],
            capture_output=True, text=True, timeout=5,
        )
        remotes = result.stdout.strip()

        return {
            "ruta": ruta,
            "branch": branch,
            "ultimo_commit": last_commit,
            "remotos": remotes,
            "archivos_modificados": status.split("\n") if status else [],
            "limpio": len(status) == 0,
        }

    except subprocess.TimeoutExpired:
        return {"error": "Timeout obteniendo estado del repositorio"}
    except Exception as exc:
        return {"error": str(exc)}


def crear_proyecto(nombre: str, tipo: str = "python", directorio: str = "./projects") -> Dict[str, Any]:
    """
    Crea la estructura base de un proyecto.

    Parámetros
    ----------
    nombre : str
        Nombre del proyecto.
    tipo : str
        Tipo de proyecto: "python", "node", "web", "rust".
    directorio : str
        Directorio base donde crear el proyecto.

    Retorna
    -------
    dict con resultado de la creación.
    """
    # ── Sanitizar inputs ──
    nombre = sanitize_input(nombre)
    nombre = sanitize_shell_arg(nombre)
    tipo = sanitize_input(tipo).lower()
    directorio = sanitize_input(directorio)

    if not nombre:
        return {"error": "Nombre de proyecto vacío"}

    # Validar nombre de proyecto (solo alfanuméricos, guiones y guiones bajos)
    if not re.match(r"^[a-zA-Z0-9_-]+$", nombre):
        return {
            "error": f"Nombre de proyecto inválido: {nombre!r}. "
                     f"Usar solo letras, números, guiones y guiones bajos."
        }

    tipos_validos = {"python", "node", "web", "rust"}
    if tipo not in tipos_validos:
        return {
            "error": f"Tipo de proyecto no soportado: {tipo!r}. "
                     f"Tipos disponibles: {', '.join(sorted(tipos_validos))}"
        }

    # ── Crear estructura de directorios ──
    proyecto_path = os.path.join(directorio, nombre)

    try:
        os.makedirs(proyecto_path, exist_ok=True)
    except OSError as exc:
        return {"error": f"Error creando directorio {proyecto_path}: {exc}"}

    # ── Estructura según tipo ──
    estructura: Dict[str, Any] = {"directorios": [], "archivos": []}

    if tipo == "python":
        dirs = [
            os.path.join(proyecto_path, "src"),
            os.path.join(proyecto_path, "tests"),
            os.path.join(proyecto_path, "docs"),
        ]
        archivos = {
            os.path.join(proyecto_path, "src", "__init__.py"): "",
            os.path.join(proyecto_path, "src", "main.py"): '"""Punto de entrada."""\n\n\ndef main():\n    pass\n\n\nif __name__ == "__main__":\n    main()\n',
            os.path.join(proyecto_path, "tests", "__init__.py"): "",
            os.path.join(proyecto_path, "tests", "test_main.py"): '"""Tests."""\n\n\ndef test_placeholder():\n    assert True\n',
            os.path.join(proyecto_path, "requirements.txt"): "",
            os.path.join(proyecto_path, "setup.py"): f'from setuptools import setup, find_packages\n\nsetup(\n    name="{nombre}",\n    version="0.1.0",\n    packages=find_packages(),\n)\n',
            os.path.join(proyecto_path, ".gitignore"): "__pycache__/\n*.pyc\n.env\nvenv/\n",
            os.path.join(proyecto_path, "README.md"): f"# {nombre}\n\nProyecto generado por ZAI.\n",
        }

    elif tipo == "node":
        dirs = [
            os.path.join(proyecto_path, "src"),
            os.path.join(proyecto_path, "test"),
        ]
        archivos = {
            os.path.join(proyecto_path, "src", "index.js"): "// Punto de entrada\n",
            os.path.join(proyecto_path, "test", "index.test.js"): "// Tests\n",
            os.path.join(proyecto_path, "package.json"): f'{{\n  "name": "{nombre}",\n  "version": "1.0.0",\n  "main": "src/index.js"\n}}\n',
            os.path.join(proyecto_path, ".gitignore"): "node_modules/\n.env\n",
            os.path.join(proyecto_path, "README.md"): f"# {nombre}\n\nProyecto generado por ZAI.\n",
        }

    elif tipo == "web":
        dirs = [
            os.path.join(proyecto_path, "css"),
            os.path.join(proyecto_path, "js"),
            os.path.join(proyecto_path, "img"),
        ]
        archivos = {
            os.path.join(proyecto_path, "index.html"): f"<!DOCTYPE html>\n<html>\n<head><title>{nombre}</title></head>\n<body><h1>{nombre}</h1></body>\n</html>\n",
            os.path.join(proyecto_path, "css", "style.css"): "/* Estilos */\n",
            os.path.join(proyecto_path, "js", "app.js"): "// App\n",
            os.path.join(proyecto_path, ".gitignore"): ".env\n",
            os.path.join(proyecto_path, "README.md"): f"# {nombre}\n\nProyecto generado por ZAI.\n",
        }

    elif tipo == "rust":
        dirs = [
            os.path.join(proyecto_path, "src"),
        ]
        archivos = {
            os.path.join(proyecto_path, "src", "main.rs"): "fn main() {\n    println!(\"Hello, world!\");\n}\n",
            os.path.join(proyecto_path, "Cargo.toml"): f'[package]\nname = "{nombre}"\nversion = "0.1.0"\nedition = "2021"\n',
            os.path.join(proyecto_path, ".gitignore"): "target/\n",
            os.path.join(proyecto_path, "README.md"): f"# {nombre}\n\nProyecto generado por ZAI.\n",
        }

    # Crear directorios
    for d in dirs:
        try:
            os.makedirs(d, exist_ok=True)
            estructura["directorios"].append(d)
        except OSError as exc:
            logger.warning("Error creando directorio %s: %s", d, exc)

    # Crear archivos
    for ruta_archivo, contenido in archivos.items():
        try:
            with open(ruta_archivo, "w", encoding="utf-8") as f:
                f.write(contenido)
            estructura["archivos"].append(ruta_archivo)
        except OSError as exc:
            logger.warning("Error creando archivo %s: %s", ruta_archivo, exc)

    # ── Inicializar Git ──
    try:
        subprocess.run(
            ["git", "init", proyecto_path],
            capture_output=True, text=True, timeout=10,
        )
    except Exception as exc:
        logger.warning("Error inicializando Git en %s: %s", proyecto_path, exc)

    logger.info("Proyecto %s creado en %s (tipo: %s)", nombre, proyecto_path, tipo)
    return {
        "exito": True,
        "mensaje": f"Proyecto '{nombre}' creado en {proyecto_path}",
        "tipo": tipo,
        "estructura": estructura,
    }


def listar_proyectos(directorio: str = "./projects") -> Dict[str, Any]:
    """
    Lista los proyectos existentes en un directorio.

    Parámetros
    ----------
    directorio : str
        Directorio base donde buscar proyectos.

    Retorna
    -------
    dict con la lista de proyectos.
    """
    directorio = sanitize_input(directorio)

    if not os.path.isdir(directorio):
        return {"proyectos": [], "total": 0, "mensaje": f"Directorio no encontrado: {directorio}"}

    proyectos: List[Dict[str, Any]] = []

    try:
        for entrada in os.listdir(directorio):
            ruta = os.path.join(directorio, entrada)
            if not os.path.isdir(ruta):
                continue

            es_git = os.path.isdir(os.path.join(ruta, ".git"))

            # Intentar detectar tipo
            tipo = "desconocido"
            if os.path.isfile(os.path.join(ruta, "setup.py")) or \
               os.path.isfile(os.path.join(ruta, "pyproject.toml")):
                tipo = "python"
            elif os.path.isfile(os.path.join(ruta, "package.json")):
                tipo = "node"
            elif os.path.isfile(os.path.join(ruta, "Cargo.toml")):
                tipo = "rust"
            elif os.path.isfile(os.path.join(ruta, "index.html")):
                tipo = "web"

            proyectos.append({
                "nombre": entrada,
                "ruta": ruta,
                "tipo": tipo,
                "es_git": es_git,
            })

    except PermissionError:
        return {"error": f"Sin permisos para leer: {directorio}"}
    except Exception as exc:
        return {"error": str(exc)}

    return {"proyectos": proyectos, "total": len(proyectos)}


def ejecutar_comando_proyecto(
    ruta: str, comando: str, timeout: int = 60
) -> Dict[str, Any]:
    """
    Ejecuta un comando dentro del contexto de un proyecto.

    Parámetros
    ----------
    ruta : str
        Ruta al proyecto.
    comando : str
        Comando a ejecutar.
    timeout : int
        Timeout en segundos.

    Retorna
    -------
    dict con resultado de la ejecución.
    """
    # ── Sanitizar inputs ──
    ruta = sanitize_input(ruta)
    comando = sanitize_input(comando)

    if not os.path.isdir(ruta):
        return {"error": f"Directorio no encontrado: {ruta}"}

    if not comando:
        return {"error": "Comando vacío"}

    # ── Verificar seguridad ──
    if not is_safe_command(comando):
        return {"error": f"Comando bloqueado por políticas de seguridad: {comando[:100]}"}

    # ── Ejecutar ──
    try:
        result = subprocess.run(
            comando,
            shell=True,
            cwd=ruta,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "comando": comando,
            "ruta": ruta,
            "exit_code": result.returncode,
            "stdout": result.stdout[:3000],
            "stderr": result.stderr[:1000],
        }

    except subprocess.TimeoutExpired:
        return {"error": f"Timeout ({timeout}s) ejecutando: {comando[:100]}"}
    except Exception as exc:
        return {"error": str(exc)}
