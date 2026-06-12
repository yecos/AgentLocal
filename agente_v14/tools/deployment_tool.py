"""
=============================================================
AGENTE v14 - Herramienta de Deployment
=============================================================
Permite al agente desplegar proyectos que ha construido.
Soporta multiples targets: Vercel, Docker, Local, SSH.

Funciones:
- detect_project_type: Detecta tipo de proyecto
- deploy_vercel: Deploy a Vercel
- deploy_docker: Deploy con Docker
- deploy_local: Deploy local como proceso background
- deploy_ssh: Deploy via SSH/rsync
- generate_dockerfile: Genera Dockerfile optimizado
- stop_deployment: Detiene un deployment activo
- deployment_status: Estado de deployments activos
- list_deployment_options: Opciones de deploy disponibles
=============================================================
"""

import os
import re
import json
import subprocess
import signal
import time
from pathlib import Path
from typing import Optional

from config import REPOS_DIR, logger
from utils.security import validate_path, is_dangerous_command

# ============================================================
# REGISTRO DE DEPLOYMENTS EN MEMORIA
# ============================================================
_DEPLOYMENTS: dict = {}  # key: project_path -> dict con info del deployment

# Timeouts
BUILD_TIMEOUT = 300  # segundos para build
DEPLOY_TIMEOUT = 120  # segundos para deploy
COMMAND_TIMEOUT = 30  # segundos para comandos cortos


# ============================================================
# UTILIDADES BASE
# ============================================================

def _run_command(
    cmd: list,
    cwd: str = None,
    timeout: int = COMMAND_TIMEOUT,
    capture: bool = True,
    env: dict = None,
) -> dict:
    """Ejecuta un comando y retorna resultado estructurado.

    Args:
        cmd: Comando como lista de strings
        cwd: Directorio de trabajo
        timeout: Timeout en segundos
        capture: Si capturar stdout/stderr
        env: Variables de entorno adicionales

    Returns:
        Dict con success, stdout, stderr, exit_code
    """
    try:
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=run_env,
        )

        return {
            "success": result.returncode == 0,
            "stdout": result.stdout.strip() if capture else "",
            "stderr": result.stderr.strip() if capture else "",
            "exit_code": result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "exit_code": -1,
        }
    except FileNotFoundError:
        cmd_name = cmd[0] if cmd else "unknown"
        return {
            "success": False,
            "stdout": "",
            "stderr": f"{cmd_name} not found. Is it installed?",
            "exit_code": -1,
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "exit_code": -1,
        }


def _tool_installed(tool_name: str) -> bool:
    """Verifica si una herramienta CLI esta instalada."""
    result = _run_command(["which", tool_name], timeout=5)
    return result["success"]


def _register_deployment(project_path: str, info: dict):
    """Registra un deployment en el registro en memoria."""
    _DEPLOYMENTS[project_path] = {
        **info,
        "registered_at": time.time(),
    }
    logger.info(f"Deployment registered: {project_path} -> {info.get('platform', 'unknown')}")


def _unregister_deployment(project_path: str):
    """Elimina un deployment del registro."""
    if project_path in _DEPLOYMENTS:
        del _DEPLOYMENTS[project_path]
        logger.info(f"Deployment unregistered: {project_path}")


# ============================================================
# DETECCION DE PROYECTO
# ============================================================

def detect_project_type(project_path: str) -> dict:
    """Escanea el directorio del proyecto y detecta el tipo.

    Args:
        project_path: Ruta al directorio del proyecto

    Returns:
        Dict con type, framework, has_dockerfile, has_vercel,
        package_manager, y otros campos detectados
    """
    validated = validate_path(project_path)
    if not validated or validated.startswith("ACCESO DENEGADO"):
        return {"success": False, "error": f"Ruta no permitida: {project_path}"}

    project_dir = Path(validated)
    if not project_dir.exists():
        return {"success": False, "error": f"Directorio no existe: {project_path}"}

    # Archivos clave a buscar
    files = set()
    try:
        for f in project_dir.iterdir():
            files.add(f.name.lower())
    except PermissionError:
        return {"success": False, "error": f"Sin permisos para leer: {project_path}"}

    has_dockerfile = "dockerfile" in files
    has_vercel = "vercel.json" in files
    has_package_json = "package.json" in files
    has_requirements_txt = "requirements.txt" in files
    has_pyproject_toml = "pyproject.toml" in files
    has_setup_py = "setup.py" in files
    has_index_html = "index.html" in files

    # Detectar package_manager
    package_manager = "unknown"
    if "package-lock.json" in files:
        package_manager = "npm"
    elif "yarn.lock" in files:
        package_manager = "yarn"
    elif "pnpm-lock.yaml" in files:
        package_manager = "pnpm"
    elif "bun.lockb" in files:
        package_manager = "bun"
    elif has_package_json:
        package_manager = "npm"

    # Detectar tipo y framework
    project_type = "unknown"
    framework = "unknown"

    if has_package_json:
        # Leer package.json para determinar framework
        pkg_path = project_dir / "package.json"
        try:
            with open(pkg_path, "r", encoding="utf-8") as f:
                pkg = json.load(f)

            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            if "next" in deps:
                project_type = "nextjs"
                framework = "next"
            elif "react" in deps and "vite" in deps:
                project_type = "react"
                framework = "vite"
            elif "react" in deps:
                project_type = "react"
                framework = "react"
            elif "express" in deps:
                project_type = "express"
                framework = "express"
            elif "fastify" in deps:
                project_type = "express"
                framework = "fastify"
            elif "vue" in deps:
                project_type = "react"
                framework = "vue"
            elif "svelte" in deps:
                project_type = "react"
                framework = "svelte"
            else:
                # Generic Node.js project
                project_type = "express"
                framework = "node"

            scripts = pkg.get("scripts", {})
            has_build = "build" in scripts
            has_start = "start" in scripts
            has_dev = "dev" in scripts

        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Error reading package.json: {e}")
            project_type = "express"
            framework = "node"
            has_build = False
            has_start = False
            has_dev = False

    elif has_requirements_txt or has_pyproject_toml or has_setup_py:
        # Proyecto Python
        # Intentar determinar si es API o CLI
        python_files = list(project_dir.glob("*.py"))
        main_content = ""
        for py_file in python_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                main_content += content.lower() + "\n"
            except OSError:
                pass

        # Tambien revisar subdirectorios comunes
        app_dir = project_dir / "app"
        if app_dir.exists():
            for py_file in app_dir.glob("*.py"):
                try:
                    content = py_file.read_text(encoding="utf-8", errors="ignore")
                    main_content += content.lower() + "\n"
                except OSError:
                    pass

        if "fastapi" in main_content or "from fastapi" in main_content:
            project_type = "python_api"
            framework = "fastapi"
        elif "flask" in main_content or "from flask" in main_content:
            project_type = "python_api"
            framework = "flask"
        elif "django" in main_content or "from django" in main_content:
            project_type = "python_api"
            framework = "django"
        elif "uvicorn" in main_content:
            project_type = "python_api"
            framework = "uvicorn"
        elif "click" in main_content or "argparse" in main_content or "typer" in main_content:
            project_type = "python_cli"
            framework = "click" if "click" in main_content else "argparse"
        else:
            # Default: CLI tool
            project_type = "python_cli"
            framework = "python"

    elif has_index_html:
        project_type = "static_html"
        framework = "html"
        has_build = False
        has_start = False
        has_dev = False

    elif has_dockerfile:
        project_type = "docker"
        framework = "docker"
        has_build = False
        has_start = False
        has_dev = False

    else:
        has_build = False
        has_start = False
        has_dev = False

    result = {
        "success": True,
        "type": project_type,
        "framework": framework,
        "has_dockerfile": has_dockerfile,
        "has_vercel": has_vercel,
        "has_package_json": has_package_json,
        "has_requirements_txt": has_requirements_txt,
        "has_pyproject_toml": has_pyproject_toml,
        "package_manager": package_manager,
    }

    # Asegurar que has_build/has_start/has_dev estan definidos
    if "has_build" not in result:
        result["has_build"] = has_build if "has_build" in dir() else False
    if "has_start" not in result:
        result["has_start"] = has_start if "has_start" in dir() else False
    if "has_dev" not in result:
        result["has_dev"] = has_dev if "has_dev" in dir() else False

    logger.info(f"Project detected: {project_type}/{framework} at {project_path}")
    return result


# ============================================================
# DEPLOY VERCEL
# ============================================================

def deploy_vercel(project_path: str, production: bool = False) -> dict:
    """Despliega un proyecto a Vercel.

    Args:
        project_path: Ruta al proyecto
        production: Si es deploy a produccion (--prod)

    Returns:
        Dict con success, url, platform
    """
    validated = validate_path(project_path)
    if not validated or validated.startswith("ACCESO DENEGADO"):
        return {"success": False, "error": f"Ruta no permitida: {project_path}"}

    if not Path(validated).exists():
        return {"success": False, "error": f"Directorio no existe: {project_path}"}

    logger.info(f"Starting Vercel deploy for {project_path} (production={production})")

    # Verificar si Vercel CLI esta instalado
    vercel_check = _run_command(["vercel", "--version"], timeout=10)
    if not vercel_check["success"]:
        logger.info("Vercel CLI not found. Attempting to install...")
        install_result = _run_command(
            ["npm", "install", "-g", "vercel"],
            timeout=BUILD_TIMEOUT,
        )
        if not install_result["success"]:
            return {
                "success": False,
                "error": "Vercel CLI not installed. Install with: npm install -g vercel",
                "install_command": "npm install -g vercel",
                "platform": "vercel",
            }

    # Detectar tipo de proyecto
    project_info = detect_project_type(validated)

    # Construir comando de deploy
    cmd = ["vercel", "--yes"]  # --yes para no interactive
    if production:
        cmd.append("--prod")

    # Ejecutar deploy
    deploy_result = _run_command(
        cmd,
        cwd=validated,
        timeout=DEPLOY_TIMEOUT,
    )

    if not deploy_result["success"]:
        return {
            "success": False,
            "error": deploy_result["stderr"] or deploy_result["stdout"],
            "platform": "vercel",
        }

    # Extraer URL del output
    output = deploy_result["stdout"]
    url = _extract_vercel_url(output)

    result = {
        "success": True,
        "url": url,
        "platform": "vercel",
        "production": production,
        "output": output[:2000],
    }

    # Registrar deployment
    _register_deployment(validated, {
        "platform": "vercel",
        "url": url,
        "production": production,
        "project_type": project_info.get("type", "unknown"),
    })

    logger.info(f"Vercel deploy successful: {url}")
    return result


def _extract_vercel_url(output: str) -> str:
    """Extrae la URL de deploy del output de Vercel."""
    # Patrones comunes en output de vercel
    patterns = [
        r'https://[a-zA-Z0-9][-a-zA-Z0-9]*\.vercel\.app',
        r'Production:\s+(https://[^\s]+)',
        r'Deployment URL:\s+(https://[^\s]+)',
        r'Inspect:\s+(https://[^\s]+)',
    ]

    for pattern in patterns:
        match = re.search(pattern, output)
        if match:
            url = match.group(1) if match.lastindex else match.group(0)
            return url.strip()

    # Fallback: buscar cualquier URL de vercel
    url_match = re.search(r'https://[^\s]+\.vercel\.app', output)
    if url_match:
        return url_match.group(0)

    return ""


# ============================================================
# DEPLOY DOCKER
# ============================================================

def deploy_docker(
    project_path: str,
    image_name: str = None,
    ports: str = None,
) -> dict:
    """Despliega un proyecto usando Docker.

    Args:
        project_path: Ruta al proyecto
        image_name: Nombre de la imagen Docker
        ports: Mapeo de puertos (e.g., "3000:3000")

    Returns:
        Dict con success, image, container_id, url
    """
    validated = validate_path(project_path)
    if not validated or validated.startswith("ACCESO DENEGADO"):
        return {"success": False, "error": f"Ruta no permitida: {project_path}"}

    if not Path(validated).exists():
        return {"success": False, "error": f"Directorio no existe: {project_path}"}

    logger.info(f"Starting Docker deploy for {project_path}")

    # Verificar Docker
    docker_check = _run_command(["docker", "--version"], timeout=10)
    if not docker_check["success"]:
        return {
            "success": False,
            "error": "Docker not installed. Please install Docker first.",
            "platform": "docker",
        }

    # Detectar tipo de proyecto
    project_info = detect_project_type(validated)

    # Generar nombre de imagen si no se proporciona
    if not image_name:
        dir_name = Path(validated).name.lower().replace(" ", "-")
        image_name = re.sub(r'[^a-z0-9._-]', '', dir_name) or "my-app"

    # Generar Dockerfile si no existe
    if not project_info.get("has_dockerfile"):
        gen_result = generate_dockerfile(validated)
        if not gen_result["success"]:
            return {
                "success": False,
                "error": f"Failed to generate Dockerfile: {gen_result.get('error', 'unknown')}",
                "platform": "docker",
            }

    # Determinar puerto por defecto
    if not ports:
        ports = _default_port_for_project(project_info)

    # Build Docker image
    logger.info(f"Building Docker image: {image_name}")
    build_result = _run_command(
        ["docker", "build", "-t", image_name, "."],
        cwd=validated,
        timeout=BUILD_TIMEOUT,
    )

    if not build_result["success"]:
        return {
            "success": False,
            "error": f"Docker build failed: {build_result['stderr'][:1000]}",
            "platform": "docker",
            "image": image_name,
        }

    # Run container
    container_name = f"{image_name}-{int(time.time())}"
    run_cmd = ["docker", "run", "-d", "--name", container_name]

    # Agregar mapeo de puertos
    port_mappings = _parse_port_mappings(ports)
    for port_map in port_mappings:
        run_cmd.extend(["-p", port_map])

    run_cmd.append(image_name)

    logger.info(f"Running Docker container: {container_name}")
    run_result = _run_command(
        run_cmd,
        timeout=DEPLOY_TIMEOUT,
    )

    if not run_result["success"]:
        return {
            "success": False,
            "error": f"Docker run failed: {run_result['stderr'][:1000]}",
            "platform": "docker",
            "image": image_name,
        }

    container_id = run_result["stdout"].strip()[:12]

    # Determinar URL
    host_port = port_mappings[0].split(":")[0] if port_mappings else "3000"
    url = f"http://localhost:{host_port}"

    result = {
        "success": True,
        "image": image_name,
        "container_id": container_id,
        "container_name": container_name,
        "url": url,
        "platform": "docker",
        "ports": ports,
    }

    # Registrar deployment
    _register_deployment(validated, {
        "platform": "docker",
        "image": image_name,
        "container_id": container_id,
        "container_name": container_name,
        "url": url,
        "ports": ports,
        "project_type": project_info.get("type", "unknown"),
    })

    logger.info(f"Docker deploy successful: container={container_id}, url={url}")
    return result


def _parse_port_mappings(ports: str) -> list:
    """Parsea el string de puertos a lista de mapeos.

    Acepta formatos: "3000:3000", "3000:3000 8080:8080", "3000:3000,8080:8080"
    """
    if not ports:
        return ["3000:3000"]

    # Separar por coma o espacio
    mappings = re.split(r'[,\s]+', ports.strip())
    return [m.strip() for m in mappings if m.strip()]


def _default_port_for_project(project_info: dict) -> str:
    """Retorna el mapeo de puertos por defecto segun tipo de proyecto."""
    ptype = project_info.get("type", "unknown")
    framework = project_info.get("framework", "unknown")

    port_map = {
        "nextjs": "3000:3000",
        "react": "5173:5173",
        "express": "3000:3000",
        "python_api": "8000:8000",
        "python_cli": None,
        "static_html": "8080:80",
        "docker": "3000:3000",
    }

    # Refinar por framework
    framework_ports = {
        "vite": "5173:5173",
        "fastapi": "8000:8000",
        "flask": "5000:5000",
        "django": "8000:8000",
        "next": "3000:3000",
    }

    if framework in framework_ports:
        return framework_ports[framework]

    return port_map.get(ptype, "3000:3000")


# ============================================================
# DEPLOY LOCAL
# ============================================================

def deploy_local(project_path: str, port: int = None) -> dict:
    """Inicia el proyecto localmente como proceso background.

    Args:
        project_path: Ruta al proyecto
        port: Puerto especifico (opcional)

    Returns:
        Dict con success, pid, url, command
    """
    validated = validate_path(project_path)
    if not validated or validated.startswith("ACCESO DENEGADO"):
        return {"success": False, "error": f"Ruta no permitida: {project_path}"}

    if not Path(validated).exists():
        return {"success": False, "error": f"Directorio no existe: {project_path}"}

    logger.info(f"Starting local deploy for {project_path}")

    # Detectar tipo de proyecto
    project_info = detect_project_type(validated)
    ptype = project_info.get("type", "unknown")
    framework = project_info.get("framework", "unknown")

    # Determinar comando y puerto
    cmd, default_port = _get_local_command(validated, project_info, port)

    if cmd is None:
        return {
            "success": True,
            "message": "CLI tool, no server needed",
            "platform": "local",
            "project_type": ptype,
        }

    effective_port = port or default_port

    # Verificar si ya hay un deployment activo para este proyecto
    if validated in _DEPLOYMENTS:
        existing = _DEPLOYMENTS[validated]
        if existing.get("platform") == "local" and existing.get("pid"):
            # Verificar si el proceso sigue vivo
            if _is_process_running(existing["pid"]):
                return {
                    "success": False,
                    "error": f"Project already deployed locally (PID: {existing['pid']}). Stop it first.",
                    "platform": "local",
                    "existing_pid": existing["pid"],
                    "existing_url": existing.get("url", ""),
                }

    # Iniciar proceso en background
    try:
        process = subprocess.Popen(
            cmd,
            cwd=validated,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # Desatachar del proceso padre pero mantener handles
            start_new_session=True,
        )
    except FileNotFoundError as e:
        return {
            "success": False,
            "error": f"Command not found: {e}",
            "platform": "local",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to start process: {e}",
            "platform": "local",
        }

    # Dar un momento para verificar que no murio inmediatamente
    time.sleep(2)
    if process.poll() is not None:
        # El proceso ya termino - error
        stdout, stderr = process.communicate()
        return {
            "success": False,
            "error": f"Process exited immediately with code {process.returncode}",
            "stderr": (stderr or "")[:1000],
            "stdout": (stdout or "")[:1000],
            "platform": "local",
        }

    url = f"http://localhost:{effective_port}"
    command_str = " ".join(cmd)

    result = {
        "success": True,
        "pid": process.pid,
        "url": url,
        "command": command_str,
        "platform": "local",
        "port": effective_port,
    }

    # Registrar deployment
    _register_deployment(validated, {
        "platform": "local",
        "pid": process.pid,
        "process": process,
        "url": url,
        "command": command_str,
        "port": effective_port,
        "project_type": ptype,
    })

    logger.info(f"Local deploy successful: pid={process.pid}, url={url}, cmd={command_str}")
    return result


def _get_local_command(project_path: str, project_info: dict, port: int = None) -> tuple:
    """Determina el comando para iniciar el proyecto localmente.

    Returns:
        Tuple de (cmd_list, default_port). cmd_list es None para CLI tools.
    """
    ptype = project_info.get("type", "unknown")
    framework = project_info.get("framework", "unknown")
    pkg_manager = project_info.get("package_manager", "npm")

    if ptype == "nextjs":
        port_val = port or 3000
        return ["npm", "run", "dev", "--", "-p", str(port_val)], 3000

    elif ptype == "react":
        if framework == "vite":
            return ["npm", "run", "dev"], 5173
        return ["npm", "start"], 3000

    elif ptype == "express":
        # Verificar si tiene dev script
        pkg_path = Path(project_path) / "package.json"
        if pkg_path.exists():
            try:
                with open(pkg_path, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                scripts = pkg.get("scripts", {})
                if "dev" in scripts:
                    return ["npm", "run", "dev"], 3000
                elif "start" in scripts:
                    return ["npm", "start"], 3000
            except (json.JSONDecodeError, OSError):
                pass
        return ["npm", "start"], 3000

    elif ptype == "python_api":
        port_val = port or 8000
        if framework == "fastapi":
            # Buscar el archivo principal
            main_file = _find_python_main(project_path, ["main.py", "app.py", "server.py"])
            module_name = Path(main_file).stem if main_file else "main"
            return [
                "uvicorn", f"{module_name}:app",
                "--host", "0.0.0.0",
                "--port", str(port_val),
            ], 8000
        elif framework == "flask":
            env = {"FLASK_APP": "app.py", "FLASK_ENV": "development"}
            port_val = port or 5000
            return ["flask", "run", "--host", "0.0.0.0", "--port", str(port_val)], 5000
        elif framework == "django":
            return ["python", "manage.py", "runserver", f"0.0.0.0:{port or 8000}"], 8000
        else:
            port_val = port or 8000
            return ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", str(port_val)], 8000

    elif ptype == "python_cli":
        return None, None  # CLI tool, no server needed

    elif ptype == "static_html":
        port_val = port or 8080
        return ["python", "-m", "http.server", str(port_val)], 8080

    elif ptype == "docker":
        return None, None

    else:
        # Intentar con npm start como fallback
        pkg_path = Path(project_path) / "package.json"
        if pkg_path.exists():
            return ["npm", "start"], 3000
        return None, None


def _find_python_main(project_path: str, candidates: list) -> Optional[str]:
    """Busca el archivo principal de Python en el proyecto."""
    for name in candidates:
        if (Path(project_path) / name).exists():
            return name
    return None


def _is_process_running(pid: int) -> bool:
    """Verifica si un proceso sigue corriendo."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


# ============================================================
# DEPLOY SSH
# ============================================================

def deploy_ssh(
    project_path: str,
    host: str,
    user: str,
    key_path: str = None,
    remote_path: str = None,
    port: int = 22,
) -> dict:
    """Despliega un proyecto via SSH usando rsync/scp.

    Args:
        project_path: Ruta al proyecto local
        host: Host remoto
        user: Usuario SSH
        key_path: Ruta a la clave SSH (opcional)
        remote_path: Ruta remota (opcional)
        port: Puerto SSH

    Returns:
        Dict con success, url, remote_path
    """
    validated = validate_path(project_path)
    if not validated or validated.startswith("ACCESO DENEGADO"):
        return {"success": False, "error": f"Ruta no permitida: {project_path}"}

    if not Path(validated).exists():
        return {"success": False, "error": f"Directorio no existe: {project_path}"}

    logger.info(f"Starting SSH deploy for {project_path} -> {user}@{host}")

    # Verificar conectividad SSH
    ssh_cmd = ["ssh", "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=no"]
    if key_path:
        ssh_cmd.extend(["-i", key_path])
    ssh_cmd.extend(["-p", str(port), f"{user}@{host}", "echo", "OK"])

    ssh_check = _run_command(ssh_cmd, timeout=15)
    if not ssh_check["success"]:
        return {
            "success": False,
            "error": f"SSH connection failed: {ssh_check['stderr'][:500]}",
            "platform": "ssh",
        }

    # Determinar ruta remota
    if not remote_path:
        dir_name = Path(validated).name
        remote_path = f"/home/{user}/apps/{dir_name}"

    # Detectar tipo de proyecto
    project_info = detect_project_type(validated)

    # Copiar archivos via rsync
    rsync_available = _tool_installed("rsync")

    if rsync_available:
        # Usar rsync (mas eficiente)
        rsync_cmd = [
            "rsync", "-avz", "--delete",
            "-e", f"ssh -p {port}" + (f" -i {key_path}" if key_path else ""),
            f"{validated}/",
            f"{user}@{host}:{remote_path}/",
        ]
        copy_result = _run_command(rsync_cmd, timeout=DEPLOY_TIMEOUT)
    else:
        # Fallback a scp
        scp_cmd = ["scp", "-r", "-P", str(port)]
        if key_path:
            scp_cmd.extend(["-i", key_path])
        scp_cmd.extend([validated, f"{user}@{host}:{remote_path}"])
        copy_result = _run_command(scp_cmd, timeout=DEPLOY_TIMEOUT)

    if not copy_result["success"]:
        return {
            "success": False,
            "error": f"File copy failed: {copy_result['stderr'][:500]}",
            "platform": "ssh",
        }

    # Ejecutar comandos remotos de instalacion y arranque
    remote_commands = _get_remote_install_commands(project_info, remote_path)

    ssh_base = ["ssh", "-o", "StrictHostKeyChecking=no"]
    if key_path:
        ssh_base.extend(["-i", key_path])
    ssh_base.extend(["-p", str(port), f"{user}@{host}"])

    for cmd_desc, cmd in remote_commands:
        logger.info(f"Remote: {cmd_desc}")
        remote_cmd = ssh_base + [cmd]
        remote_result = _run_command(remote_cmd, timeout=BUILD_TIMEOUT)
        if not remote_result["success"]:
            logger.warning(f"Remote command failed ({cmd_desc}): {remote_result['stderr'][:300]}")
            # No abortar por fallos no criticos

    # Determinar URL
    ptype = project_info.get("type", "unknown")
    default_port = _default_port_for_project(project_info).split(":")[1] if _default_port_for_project(project_info) else "3000"
    url = f"http://{host}:{default_port}"

    result = {
        "success": True,
        "url": url,
        "remote_path": remote_path,
        "host": host,
        "user": user,
        "platform": "ssh",
    }

    # Registrar deployment
    _register_deployment(validated, {
        "platform": "ssh",
        "url": url,
        "remote_path": remote_path,
        "host": host,
        "user": user,
        "port": port,
        "project_type": project_info.get("type", "unknown"),
    })

    logger.info(f"SSH deploy successful: {url}")
    return result


def _get_remote_install_commands(project_info: dict, remote_path: str) -> list:
    """Genera comandos remotos de instalacion y arranque segun tipo de proyecto."""
    ptype = project_info.get("type", "unknown")
    commands = []

    if ptype in ("nextjs", "react", "express"):
        commands.append(("Install dependencies", f"cd {remote_path} && npm install"))
        if project_info.get("has_build"):
            commands.append(("Build project", f"cd {remote_path} && npm run build"))
        commands.append(("Start application", f"cd {remote_path} && nohup npm start > /dev/null 2>&1 &"))

    elif ptype == "python_api":
        commands.append(("Install dependencies", f"cd {remote_path} && pip install -r requirements.txt"))
        framework = project_info.get("framework", "fastapi")
        if framework == "fastapi":
            commands.append(("Start FastAPI", f"cd {remote_path} && nohup uvicorn main:app --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &"))
        elif framework == "flask":
            commands.append(("Start Flask", f"cd {remote_path} && nohup flask run --host 0.0.0.0 > /dev/null 2>&1 &"))
        elif framework == "django":
            commands.append(("Start Django", f"cd {remote_path} && nohup python manage.py runserver 0.0.0.0:8000 > /dev/null 2>&1 &"))

    elif ptype == "static_html":
        commands.append(("Start HTTP server", f"cd {remote_path} && nohup python3 -m http.server 8080 > /dev/null 2>&1 &"))

    elif ptype == "docker":
        commands.append(("Docker build & run", f"cd {remote_path} && docker build -t app . && docker run -d -p 3000:3000 app"))

    return commands


# ============================================================
# GENERACION DE DOCKERFILE
# ============================================================

def generate_dockerfile(
    project_path: str,
    base_image: str = None,
    port: int = None,
) -> dict:
    """Genera un Dockerfile optimizado basado en el tipo de proyecto.

    Args:
        project_path: Ruta al proyecto
        base_image: Imagen base personalizada (opcional)
        port: Puerto a exponer (opcional)

    Returns:
        Dict con success, dockerfile_path, content
    """
    validated = validate_path(project_path)
    if not validated or validated.startswith("ACCESO DENEGADO"):
        return {"success": False, "error": f"Ruta no permitida: {project_path}"}

    if not Path(validated).exists():
        return {"success": False, "error": f"Directorio no existe: {project_path}"}

    logger.info(f"Generating Dockerfile for {project_path}")

    # Detectar tipo de proyecto
    project_info = detect_project_type(validated)
    ptype = project_info.get("type", "unknown")

    # Generar contenido del Dockerfile
    if ptype in ("nextjs", "react", "express"):
        content = _dockerfile_nodejs(project_info, base_image, port)
    elif ptype in ("python_api", "python_cli"):
        content = _dockerfile_python(project_info, base_image, port)
    elif ptype == "static_html":
        content = _dockerfile_static(base_image, port)
    else:
        # Dockerfile generico
        content = _dockerfile_generic(base_image, port)

    # Escribir Dockerfile
    dockerfile_path = Path(validated) / "Dockerfile"
    try:
        with open(dockerfile_path, "w", encoding="utf-8") as f:
            f.write(content)
    except OSError as e:
        return {
            "success": False,
            "error": f"Failed to write Dockerfile: {e}",
        }

    # Agregar .dockerignore si no existe
    dockerignore_path = Path(validated) / ".dockerignore"
    if not dockerignore_path.exists():
        _generate_dockerignore(validated, ptype)

    result = {
        "success": True,
        "dockerfile_path": str(dockerfile_path),
        "content": content,
    }

    logger.info(f"Dockerfile generated at {dockerfile_path}")
    return result


def _dockerfile_nodejs(project_info: dict, base_image: str = None, port: int = None) -> str:
    """Genera Dockerfile para proyectos Node.js (Next.js, React, Express)."""
    framework = project_info.get("framework", "node")
    effective_port = port or 3000
    node_image = base_image or "node:18-alpine"

    if framework == "next":
        # Multi-stage build optimizado para Next.js con standalone output
        return f"""# ---- Build Stage ----
FROM {node_image} AS builder
WORKDIR /app

# Cache de dependencias
COPY package*.json ./
RUN npm ci

# Copiar codigo fuente
COPY . .

# Build con standalone output
RUN npm run build

# ---- Production Stage ----
FROM {node_image} AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1

# Crear usuario no-root
RUN addgroup --system --gid 1001 nodejs && \\
    adduser --system --uid 1001 nextjs

# Copiar archivos de build
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER nextjs

EXPOSE {effective_port}
ENV PORT={effective_port}
ENV HOSTNAME="0.0.0.0"

CMD ["node", "server.js"]
"""

    elif framework in ("vite", "react"):
        # Build estatico servido con nginx
        return f"""# ---- Build Stage ----
FROM {node_image} AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- Production Stage ----
FROM nginx:alpine AS runner

# Copiar build estatico
COPY --from=builder /app/dist /usr/share/nginx/html

# Configuracion nginx para SPA
RUN echo 'server {{\\n\\
    listen {effective_port};\\n\\
    root /usr/share/nginx/html;\\n\\
    index index.html;\\n\\
    location / {{\\n\\
        try_files $uri $uri/ /index.html;\\n\\
    }}\\n\\
}}' > /etc/nginx/conf.d/default.conf

EXPOSE {effective_port}
CMD ["nginx", "-g", "daemon off;"]
"""

    else:
        # Express o generico Node.js
        return f"""# ---- Build Stage ----
FROM {node_image} AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci --only=production

COPY . .

# ---- Production Stage ----
FROM {node_image} AS runner
WORKDIR /app

ENV NODE_ENV=production

# Crear usuario no-root
RUN addgroup --system --gid 1001 nodejs && \\
    adduser --system --uid 1001 appuser

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package*.json ./
COPY --from=builder /app .

USER appuser

EXPOSE {effective_port}
CMD ["npm", "start"]
"""


def _dockerfile_python(project_info: dict, base_image: str = None, port: int = None) -> str:
    """Genera Dockerfile para proyectos Python."""
    framework = project_info.get("framework", "python")
    effective_port = port or 8000
    python_image = base_image or "python:3.11-slim"

    main_module = "main"
    # Intentar detectar el modulo principal
    if framework == "fastapi":
        main_module = "main"
        cmd = f'["uvicorn", "{main_module}:app", "--host", "0.0.0.0", "--port", "{effective_port}"]'
    elif framework == "flask":
        main_module = "app"
        cmd = f'["flask", "run", "--host", "0.0.0.0", "--port", "{effective_port}"]'
    elif framework == "django":
        cmd = f'["python", "manage.py", "runserver", "0.0.0.0:{effective_port}"]'
    else:
        # CLI o generico
        cmd = '["python", "main.py"]'

    requirements_file = "requirements.txt"
    if not project_info.get("has_requirements_txt") and project_info.get("has_pyproject_toml"):
        requirements_file = None

    pip_install = f"RUN pip install --no-cache-dir -r requirements.txt"
    if requirements_file is None:
        pip_install = "RUN pip install --no-cache-dir ."

    return f"""FROM {python_image}

WORKDIR /app

# Cache de dependencias
{f"COPY {requirements_file} ." if requirements_file else "COPY pyproject.toml ."}
{pip_install}

# Copiar codigo fuente
COPY . .

# Crear usuario no-root
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser

EXPOSE {effective_port}

CMD {cmd}
"""


def _dockerfile_static(base_image: str = None, port: int = None) -> str:
    """Genera Dockerfile para HTML estatico."""
    effective_port = port or 8080

    return f"""FROM nginx:alpine

COPY . /usr/share/nginx/html

EXPOSE {effective_port}

CMD ["nginx", "-g", "daemon off;"]
"""


def _dockerfile_generic(base_image: str = None, port: int = None) -> str:
    """Genera Dockerfile generico."""
    effective_port = port or 3000
    effective_base = base_image or "alpine:latest"

    return f"""FROM {effective_base}

WORKDIR /app

COPY . .

EXPOSE {effective_port}

# Comando por defecto - ajustar segun necesidad
CMD ["/bin/sh"]
"""


def _generate_dockerignore(project_path: str, ptype: str):
    """Genera .dockerignore basado en tipo de proyecto."""
    lines = [
        "node_modules",
        ".git",
        ".gitignore",
        ".env",
        ".env.local",
        "*.log",
        "__pycache__",
        ".pytest_cache",
        ".venv",
        "venv",
        "dist",
        ".next",
        ".DS_Store",
        "README.md",
        ".dockerignore",
        "Dockerfile",
        "docker-compose.yml",
    ]

    if ptype in ("python_api", "python_cli"):
        lines.extend([
            "*.pyc",
            "*.pyo",
            ".mypy_cache",
            ".tox",
        ])
    elif ptype in ("nextjs", "react", "express"):
        lines.extend([
            ".cache",
            "coverage",
        ])

    try:
        dockerignore_path = Path(project_path) / ".dockerignore"
        with open(dockerignore_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


# ============================================================
# STOP DEPLOYMENT
# ============================================================

def stop_deployment(
    deployment_id: str = None,
    project_path: str = None,
) -> dict:
    """Detiene un deployment activo.

    Args:
        deployment_id: ID del deployment (container_id, pid, etc.)
        project_path: Ruta del proyecto (alternativa a deployment_id)

    Returns:
        Dict con success, message
    """
    if not deployment_id and not project_path:
        return {"success": False, "error": "Must provide deployment_id or project_path"}

    # Buscar deployment por project_path
    if project_path:
        validated = validate_path(project_path)
        if not validated or validated.startswith("ACCESO DENEGADO"):
            return {"success": False, "error": f"Ruta no permitida: {project_path}"}

        if validated not in _DEPLOYMENTS:
            return {"success": False, "error": f"No active deployment found for: {project_path}"}

        deployment = _DEPLOYMENTS[validated]
    else:
        # Buscar por deployment_id en los deployments registrados
        deployment = None
        search_path = None
        for path, info in _DEPLOYMENTS.items():
            if (info.get("container_id") == deployment_id or
                info.get("container_name") == deployment_id or
                str(info.get("pid")) == str(deployment_id)):
                deployment = info
                search_path = path
                break

        if not deployment:
            return {"success": False, "error": f"No deployment found with id: {deployment_id}"}

        validated = search_path

    platform = deployment.get("platform", "unknown")

    # Detener segun plataforma
    if platform == "local":
        return _stop_local_deployment(validated, deployment)
    elif platform == "docker":
        return _stop_docker_deployment(validated, deployment)
    elif platform == "vercel":
        return _stop_vercel_deployment(validated, deployment)
    elif platform == "ssh":
        return _stop_ssh_deployment(validated, deployment)
    else:
        return {"success": False, "error": f"Unknown platform: {platform}"}


def _stop_local_deployment(project_path: str, deployment: dict) -> dict:
    """Detiene un deployment local."""
    pid = deployment.get("pid")
    if not pid:
        return {"success": False, "error": "No PID found for local deployment"}

    if not _is_process_running(pid):
        _unregister_deployment(project_path)
        return {"success": True, "message": f"Process {pid} already stopped"}

    try:
        # Intentar terminacion graceful
        os.kill(pid, signal.SIGTERM)
        time.sleep(2)

        # Si sigue vivo, forzar kill
        if _is_process_running(pid):
            os.kill(pid, signal.SIGKILL)
            time.sleep(1)

        if _is_process_running(pid):
            return {
                "success": False,
                "error": f"Failed to kill process {pid}",
                "platform": "local",
            }

    except ProcessLookupError:
        pass  # Ya murio
    except PermissionError:
        return {
            "success": False,
            "error": f"Permission denied to kill process {pid}",
            "platform": "local",
        }

    _unregister_deployment(project_path)
    logger.info(f"Local deployment stopped: pid={pid}")
    return {
        "success": True,
        "message": f"Deployment stopped (PID: {pid})",
        "platform": "local",
    }


def _stop_docker_deployment(project_path: str, deployment: dict) -> dict:
    """Detiene un deployment Docker."""
    container_id = deployment.get("container_id")
    container_name = deployment.get("container_name")

    if not container_id and not container_name:
        return {"success": False, "error": "No container ID found for Docker deployment"}

    identifier = container_name or container_id

    # Detener contenedor
    stop_result = _run_command(
        ["docker", "stop", identifier],
        timeout=30,
    )

    if not stop_result["success"]:
        logger.warning(f"Failed to stop container {identifier}: {stop_result['stderr']}")

    # Remover contenedor
    rm_result = _run_command(
        ["docker", "rm", identifier],
        timeout=15,
    )

    _unregister_deployment(project_path)
    logger.info(f"Docker deployment stopped: container={identifier}")
    return {
        "success": True,
        "message": f"Docker container stopped and removed: {identifier}",
        "platform": "docker",
    }


def _stop_vercel_deployment(project_path: str, deployment: dict) -> dict:
    """Detiene/remueve un deployment de Vercel."""
    # Vercel no tiene un "stop" directo, pero podemos remover el proyecto
    _unregister_deployment(project_path)
    logger.info(f"Vercel deployment removed from registry: {project_path}")
    return {
        "success": True,
        "message": "Vercel deployment removed from registry. Use 'vercel remove' to fully delete.",
        "platform": "vercel",
        "hint": "vercel remove --yes",
    }


def _stop_ssh_deployment(project_path: str, deployment: dict) -> dict:
    """Detiene un deployment SSH remoto."""
    host = deployment.get("host", "")
    user = deployment.get("user", "")
    remote_path = deployment.get("remote_path", "")
    port = deployment.get("port", 22)
    ptype = deployment.get("project_type", "unknown")

    # Intentar detener el proceso remoto
    ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-p", str(port), f"{user}@{host}"]

    if ptype in ("nextjs", "react", "express"):
        remote_cmd = ssh_cmd + [f"pkill -f 'node.*{remote_path}' || true"]
    elif ptype == "python_api":
        remote_cmd = ssh_cmd + [f"pkill -f 'uvicorn.*{remote_path}' || pkill -f 'flask.*{remote_path}' || true"]
    else:
        remote_cmd = ssh_cmd + ["echo 'Cannot auto-stop remote deployment'"]

    _run_command(remote_cmd, timeout=15)

    _unregister_deployment(project_path)
    logger.info(f"SSH deployment stopped: {user}@{host}:{remote_path}")
    return {
        "success": True,
        "message": f"SSH deployment stopped: {user}@{host}:{remote_path}",
        "platform": "ssh",
    }


# ============================================================
# DEPLOYMENT STATUS
# ============================================================

def deployment_status(project_path: str = None) -> dict:
    """Verifica el estado de los deployments activos.

    Args:
        project_path: Ruta especifica (opcional, si no se proporciona lista todos)

    Returns:
        Dict con success, deployments (lista de deployments activos)
    """
    if project_path:
        validated = validate_path(project_path)
        if not validated or validated.startswith("ACCESO DENEGADO"):
            return {"success": False, "error": f"Ruta no permitida: {project_path}"}

        if validated not in _DEPLOYMENTS:
            return {
                "success": True,
                "deployments": [],
                "message": "No active deployments for this project",
            }

        deployment = _DEPLOYMENTS[validated]
        status = _check_deployment_health(deployment)

        return {
            "success": True,
            "deployments": [
                {
                    "project_path": validated,
                    "platform": deployment.get("platform"),
                    "status": status,
                    "url": deployment.get("url", ""),
                    **_get_deployment_summary(deployment),
                }
            ],
        }

    # Listar todos los deployments activos
    active_deployments = []
    dead_deployments = []

    for path, info in _DEPLOYMENTS.items():
        status = _check_deployment_health(info)
        entry = {
            "project_path": path,
            "platform": info.get("platform"),
            "status": status,
            "url": info.get("url", ""),
            **_get_deployment_summary(info),
        }

        if status == "running":
            active_deployments.append(entry)
        else:
            dead_deployments.append(entry)

    # Limpiar deployments muertos
    for entry in dead_deployments:
        _unregister_deployment(entry["project_path"])

    return {
        "success": True,
        "total": len(active_deployments),
        "deployments": active_deployments,
    }


def _check_deployment_health(deployment: dict) -> str:
    """Verifica si un deployment sigue activo."""
    platform = deployment.get("platform", "unknown")

    if platform == "local":
        pid = deployment.get("pid")
        if pid and _is_process_running(pid):
            return "running"
        return "stopped"

    elif platform == "docker":
        container_id = deployment.get("container_id")
        container_name = deployment.get("container_name")
        identifier = container_name or container_id
        if identifier:
            result = _run_command(
                ["docker", "inspect", "-f", "{{.State.Running}}", identifier],
                timeout=5,
            )
            if result["success"] and "true" in result["stdout"].lower():
                return "running"
        return "stopped"

    elif platform == "vercel":
        # Vercel deployments siempre estan "running" si se registraron
        return "deployed"

    elif platform == "ssh":
        # Dificil verificar sin conectar de nuevo
        return "unknown"

    return "unknown"


def _get_deployment_summary(deployment: dict) -> dict:
    """Retorna resumen de un deployment para status."""
    summary = {}
    if deployment.get("pid"):
        summary["pid"] = deployment["pid"]
    if deployment.get("container_id"):
        summary["container_id"] = deployment["container_id"]
    if deployment.get("container_name"):
        summary["container_name"] = deployment["container_name"]
    if deployment.get("image"):
        summary["image"] = deployment["image"]
    if deployment.get("port"):
        summary["port"] = deployment["port"]
    if deployment.get("project_type"):
        summary["project_type"] = deployment["project_type"]
    if deployment.get("command"):
        summary["command"] = deployment["command"]
    return summary


# ============================================================
# LIST DEPLOYMENT OPTIONS
# ============================================================

def list_deployment_options(project_path: str) -> dict:
    """Analiza el proyecto y retorna opciones de deploy disponibles.

    Args:
        project_path: Ruta al proyecto

    Returns:
        Dict con available, recommended, reasons
    """
    validated = validate_path(project_path)
    if not validated or validated.startswith("ACCESO DENEGADO"):
        return {"success": False, "error": f"Ruta no permitida: {project_path}"}

    if not Path(validated).exists():
        return {"success": False, "error": f"Directorio no existe: {project_path}"}

    logger.info(f"Listing deployment options for {project_path}")

    # Detectar tipo de proyecto
    project_info = detect_project_type(validated)
    ptype = project_info.get("type", "unknown")
    framework = project_info.get("framework", "unknown")

    # Verificar herramientas disponibles
    has_docker = _tool_installed("docker")
    has_vercel = _tool_installed("vercel")
    has_ssh = _tool_installed("ssh")
    has_npm = _tool_installed("npm") or _tool_installed("bun")
    has_python = _tool_installed("python3") or _tool_installed("python")

    # Construir lista de opciones disponibles
    available = []
    reasons = {}

    # Local siempre disponible
    if ptype != "python_cli":
        available.append("local")
        reasons["local"] = "Run the project locally as a development server"
    else:
        reasons["local"] = "CLI tool - no server needed, run directly with python"

    # Docker
    if has_docker:
        available.append("docker")
        reasons["docker"] = "Containerized deployment with Docker"
    else:
        reasons["docker"] = "Docker not installed. Install: https://docs.docker.com/get-docker/"

    # Vercel
    if has_vercel:
        available.append("vercel")
        reasons["vercel"] = "Deploy to Vercel's edge network"
    else:
        reasons["vercel"] = "Vercel CLI not installed. Install: npm install -g vercel"

    # SSH
    if has_ssh:
        available.append("ssh")
        reasons["ssh"] = "Deploy to a remote server via SSH"
    else:
        reasons["ssh"] = "SSH client not available"

    # Determinar recomendacion
    recommended = _recommend_deployment(ptype, framework, available, project_info)
    if recommended not in available and available:
        recommended = available[0]

    # Agregar razones especificas por tipo de proyecto
    if ptype == "nextjs":
        reasons["recommended_reason"] = "Next.js is natively supported by Vercel with zero-config"
    elif ptype == "react" and framework == "vite":
        reasons["recommended_reason"] = "Vite projects work well with Docker or Vercel for SPA hosting"
    elif ptype == "python_api":
        reasons["recommended_reason"] = "Python APIs are best deployed with Docker for reproducibility"
    elif ptype == "static_html":
        reasons["recommended_reason"] = "Static HTML can be deployed anywhere; Vercel is simplest"
    elif ptype == "python_cli":
        reasons["recommended_reason"] = "CLI tools don't need server deployment; use Docker for distribution"
    else:
        reasons["recommended_reason"] = f"Generic {ptype} project - Docker provides the most flexibility"

    result = {
        "success": True,
        "available": available,
        "recommended": recommended,
        "reasons": reasons,
        "project_type": ptype,
        "framework": framework,
        "tools_available": {
            "docker": has_docker,
            "vercel": has_vercel,
            "ssh": has_ssh,
            "npm": has_npm,
            "python": has_python,
        },
    }

    logger.info(f"Deployment options: available={available}, recommended={recommended}")
    return result


def _recommend_deployment(
    ptype: str,
    framework: str,
    available: list,
    project_info: dict,
) -> str:
    """Determina la plataforma recomendada segun tipo de proyecto y herramientas."""
    # Next.js -> Vercel es la mejor opcion
    if ptype == "nextjs":
        if "vercel" in available:
            return "vercel"
        if "docker" in available:
            return "docker"
        return "local"

    # React SPA -> Vercel o Docker
    if ptype == "react":
        if "vercel" in available:
            return "vercel"
        if "docker" in available:
            return "docker"
        return "local"

    # Express -> Docker o Local
    if ptype == "express":
        if "docker" in available:
            return "docker"
        return "local"

    # Python API -> Docker es la mejor opcion
    if ptype == "python_api":
        if "docker" in available:
            return "docker"
        if "ssh" in available:
            return "ssh"
        return "local"

    # Python CLI -> Docker para distribucion
    if ptype == "python_cli":
        if "docker" in available:
            return "docker"
        return "local"

    # Static HTML -> Vercel o local
    if ptype == "static_html":
        if "vercel" in available:
            return "vercel"
        return "local"

    # Docker -> ya tiene Dockerfile
    if ptype == "docker":
        if "docker" in available:
            return "docker"
        return "local"

    # Fallback
    if "docker" in available:
        return "docker"
    if "local" in available:
        return "local"
    return available[0] if available else "unknown"


# ============================================================
# FUNCIONES AUXILIARES PUBLICAS
# ============================================================

def get_deployment(project_path: str) -> Optional[dict]:
    """Retorna la informacion de un deployment registrado.

    Args:
        project_path: Ruta del proyecto

    Returns:
        Dict con info del deployment o None
    """
    validated = validate_path(project_path)
    if not validated or validated.startswith("ACCESO DENEGADO"):
        return None

    return _DEPLOYMENTS.get(validated)


def get_all_deployments() -> dict:
    """Retorna todos los deployments registrados.

    Returns:
        Dict completo de _DEPLOYMENTS
    """
    return dict(_DEPLOYMENTS)
