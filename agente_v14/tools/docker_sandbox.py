"""
=============================================================
AGENTE v17 - Docker Sandbox para Ejecucion Segura
=============================================================
Ejecuta codigo dentro de contenedores Docker aislados.
Si Docker no esta disponible, hace fallback al sandbox local.

Caracteristicas:
- Aislamiento completo del sistema host
- Limites de memoria y CPU configurables
- Timeout con kill automatico
- Sin acceso a red por defecto (configurable)
- Directorio de trabajo montado como volumen
- Auto-limpieza de contenedores

v17: Ejecucion segura en contenedores Docker.
=============================================================
"""

import os
import re
import json
import subprocess
import tempfile
import time
import logging
from datetime import datetime
from typing import Optional

from config import REPOS_DIR, logger
from utils.security import validate_path


# ============================================================
# CLASE PRINCIPAL: DOCKER SANDBOX
# ============================================================

class DockerSandbox:
    """Ejecuta codigo dentro de contenedores Docker aislados.
    Si Docker no esta disponible, hace fallback al sandbox local.
    """

    def __init__(self):
        """Inicializa el sandbox. Verifica si Docker esta disponible."""
        self._docker_available: bool = self._check_docker()
        self._image: str = "python:3.11-slim"
        self._memory_limit: str = "256m"
        self._cpu_period: int = 100000
        self._cpu_quota: int = 50000      # 50% de 1 core
        self._timeout: int = 60
        self._network_disabled: bool = True
        self._max_output: int = 5000
        # Prefijo para identificar contenedores de este sandbox
        self._container_prefix: str = "agent-sandbox"
        # Directorio temporal para archivos de codigo
        self._sandbox_dir = os.path.join(REPOS_DIR, ".docker_sandbox")
        os.makedirs(self._sandbox_dir, exist_ok=True)

        if self._docker_available:
            logger.info("[DockerSandbox] Docker disponible - ejecucion en contenedores aislados")
        else:
            logger.warning("[DockerSandbox] Docker NO disponible - fallback a ejecucion local")

    # ----------------------------------------------------------
    # VERIFICACION DE DOCKER
    # ----------------------------------------------------------
    def _check_docker(self) -> bool:
        """Verifica si Docker esta instalado y el daemon esta corriendo."""
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return False

    def is_available(self) -> bool:
        """Verifica si Docker daemon esta corriendo (check en vivo)."""
        return self._check_docker()

    # ----------------------------------------------------------
    # EJECUCION DE CODIGO EN DOCKER
    # ----------------------------------------------------------
    def execute_in_docker(
        self,
        code: str,
        language: str = "python",
        timeout: int = 60,
        working_dir: str = None,
        env_vars: dict = None,
        allow_network: bool = False,
    ) -> dict:
        """Ejecuta codigo dentro de un contenedor Docker aislado.

        Si Docker no esta disponible, hace fallback al sandbox local.

        Args:
            code: Codigo fuente a ejecutar
            language: Lenguaje (python, javascript, bash)
            timeout: Timeout en segundos
            working_dir: Directorio de trabajo (se monta como /workspace)
            env_vars: Variables de entorno adicionales
            allow_network: Si True, permite acceso a red

        Returns:
            Dict con: {success, stdout, stderr, exit_code, duration, container_id}
        """
        # Fallback a ejecucion local si Docker no esta disponible
        if not self._docker_available:
            logger.info("[DockerSandbox] Docker no disponible, usando fallback local")
            return self._fallback_local(code, language, timeout, working_dir, env_vars)

        # Validar directorio de trabajo si se proporciona
        mount_dir = working_dir or self._sandbox_dir
        if working_dir:
            path_validation = validate_path(working_dir)
            if "ACCESO DENEGADO" in str(path_validation):
                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Acceso denegado al directorio: {working_dir}",
                    "exit_code": -1,
                    "duration": 0,
                    "container_id": None,
                }

        # Asegurar que el directorio existe
        os.makedirs(mount_dir, exist_ok=True)

        # Determinar extension y comando segun lenguaje
        lang_config = self._get_language_config(language)
        if not lang_config:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Lenguaje no soportado en Docker: {language}",
                "exit_code": -1,
                "duration": 0,
                "container_id": None,
            }

        # Escribir codigo a archivo temporal en el directorio montado
        timestamp = datetime.now().strftime("%H%M%S%f")
        filename = f"exec_{timestamp}{lang_config['ext']}"
        filepath = os.path.join(mount_dir, filename)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(code)

            # Construir comando Docker
            network_mode = "none" if not allow_network else "bridge"
            cmd = [
                "docker", "run", "--rm",
                "--memory", self._memory_limit,
                "--cpus", "0.5",
                "--network", network_mode,
                "-v", f"{os.path.abspath(mount_dir)}:/workspace",
                "--read-only",
                "--tmpfs", "/tmp:size=50m",
            ]

            # Agregar variables de entorno si se proporcionan
            if env_vars:
                for key, value in env_vars.items():
                    # Sanitizar clave y valor
                    safe_key = re.sub(r'[^A-Za-z0-9_]', '', str(key))
                    safe_value = str(value)[:500]
                    cmd.extend(["-e", f"{safe_key}={safe_value}"])

            # Agregar imagen y comando de ejecucion
            cmd.extend([
                self._image,
                lang_config["runner"],
                f"/workspace/{filename}",
            ])

            # Ejecutar contenedor
            logger.info(f"[DockerSandbox] Ejecutando en Docker: {filename} (lang={language}, timeout={timeout}s)")
            start_time = time.time()

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=timeout + 5,  # Margen extra para Docker overhead
                )
                duration = time.time() - start_time

                # Truncar salida si es muy larga
                stdout = result.stdout[:self._max_output]
                stderr = result.stderr[:self._max_output]

                success = result.returncode == 0

                logger.info(
                    f"[DockerSandbox] Ejecucion completada: exit_code={result.returncode}, "
                    f"duration={duration:.2f}s"
                )

                return {
                    "success": success,
                    "stdout": stdout,
                    "stderr": stderr,
                    "exit_code": result.returncode,
                    "duration": round(duration, 2),
                    "container_id": None,  # --rm elimina el contenedor
                }

            except subprocess.TimeoutExpired:
                duration = time.time() - start_time
                # Intentar matar el contenedor si sigue corriendo
                self._kill_orphaned_containers(filename)
                logger.warning(f"[DockerSandbox] Timeout despues de {timeout}s para {filename}")

                return {
                    "success": False,
                    "stdout": "",
                    "stderr": f"Ejecucion cancelada: timeout de {timeout}s excedido en contenedor Docker",
                    "exit_code": -1,
                    "duration": round(duration, 2),
                    "container_id": None,
                }

        except Exception as e:
            duration = time.time() - start_time if 'start_time' in dir() else 0
            logger.error(f"[DockerSandbox] Error ejecutando en Docker: {e}")

            return {
                "success": False,
                "stdout": "",
                "stderr": f"Error en ejecucion Docker: {str(e)}",
                "exit_code": -1,
                "duration": round(duration, 2),
                "container_id": None,
            }

        finally:
            # Limpiar archivo temporal
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except OSError:
                pass

    # ----------------------------------------------------------
    # EJECUCION DE ARCHIVO EN DOCKER
    # ----------------------------------------------------------
    def execute_file_in_docker(
        self,
        filepath: str,
        timeout: int = 60,
        allow_network: bool = False,
    ) -> dict:
        """Ejecuta un archivo existente dentro de un contenedor Docker.

        Monta el directorio del archivo como /workspace y lo ejecuta.

        Args:
            filepath: Ruta al archivo a ejecutar
            timeout: Timeout en segundos
            allow_network: Si True, permite acceso a red

        Returns:
            Dict con: {success, stdout, stderr, exit_code, duration, container_id}
        """
        # Validar ruta del archivo
        path_validation = validate_path(filepath)
        if "ACCESO DENEGADO" in str(path_validation):
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Acceso denegado al archivo: {filepath}",
                "exit_code": -1,
                "duration": 0,
                "container_id": None,
            }

        if not os.path.exists(filepath):
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Archivo no encontrado: {filepath}",
                "exit_code": -1,
                "duration": 0,
                "container_id": None,
            }

        # Si Docker no esta disponible, fallback local
        if not self._docker_available:
            logger.info("[DockerSandbox] Docker no disponible, usando fallback local para archivo")
            return self._fallback_file_local(filepath, timeout)

        # Directorio del archivo y nombre del archivo
        file_dir = os.path.dirname(os.path.abspath(filepath))
        filename = os.path.basename(filepath)

        # Detectar lenguaje por extension
        ext = os.path.splitext(filename)[1].lower()
        lang_config = self._get_language_config_by_ext(ext)
        if not lang_config:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Extension no soportada en Docker: {ext}",
                "exit_code": -1,
                "duration": 0,
                "container_id": None,
            }

        # Construir comando Docker
        network_mode = "none" if not allow_network else "bridge"
        cmd = [
            "docker", "run", "--rm",
            "--memory", self._memory_limit,
            "--cpus", "0.5",
            "--network", network_mode,
            "-v", f"{file_dir}:/workspace",
            "--read-only",
            "--tmpfs", "/tmp:size=50m",
            self._image,
            lang_config["runner"],
            f"/workspace/{filename}",
        ]

        logger.info(f"[DockerSandbox] Ejecutando archivo en Docker: {filepath} (timeout={timeout}s)")
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 5,
            )
            duration = time.time() - start_time

            stdout = result.stdout[:self._max_output]
            stderr = result.stderr[:self._max_output]

            return {
                "success": result.returncode == 0,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.returncode,
                "duration": round(duration, 2),
                "container_id": None,
            }

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            self._kill_orphaned_containers(filename)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Timeout de {timeout}s en contenedor Docker",
                "exit_code": -1,
                "duration": round(duration, 2),
                "container_id": None,
            }

        except Exception as e:
            duration = time.time() - start_time
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Error ejecutando archivo en Docker: {str(e)}",
                "exit_code": -1,
                "duration": round(duration, 2),
                "container_id": None,
            }

    # ----------------------------------------------------------
    # CONSTRUIR IMAGEN PERSONALIZADA
    # ----------------------------------------------------------
    def build_image(
        self,
        dockerfile_path: str,
        tag: str = "agent-sandbox",
    ) -> dict:
        """Construye una imagen Docker personalizada desde un Dockerfile.

        Args:
            dockerfile_path: Ruta al Dockerfile
            tag: Tag para la imagen construida

        Returns:
            Dict con: {success, output, image_tag, duration}
        """
        if not self._docker_available:
            return {
                "success": False,
                "output": "Docker no esta disponible",
                "image_tag": tag,
                "duration": 0,
            }

        # Validar ruta del Dockerfile
        path_validation = validate_path(dockerfile_path)
        if "ACCESO DENEGADO" in str(path_validation):
            return {
                "success": False,
                "output": f"Acceso denegado al Dockerfile: {dockerfile_path}",
                "image_tag": tag,
                "duration": 0,
            }

        if not os.path.exists(dockerfile_path):
            return {
                "success": False,
                "output": f"Dockerfile no encontrado: {dockerfile_path}",
                "image_tag": tag,
                "duration": 0,
            }

        # Directorio del Dockerfile (contexto de build)
        build_context = os.path.dirname(os.path.abspath(dockerfile_path))

        cmd = [
            "docker", "build",
            "-t", tag,
            "-f", os.path.abspath(dockerfile_path),
            build_context,
        ]

        logger.info(f"[DockerSandbox] Construyendo imagen Docker: {tag}")
        start_time = time.time()

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minutos para build
            )
            duration = time.time() - start_time

            output = result.stdout[:self._max_output]
            if result.returncode != 0:
                output += "\n" + result.stderr[:self._max_output]

            if result.returncode == 0:
                # Actualizar imagen por defecto si el build fue exitoso
                logger.info(f"[DockerSandbox] Imagen construida exitosamente: {tag}")
            else:
                logger.warning(f"[DockerSandbox] Error construyendo imagen: {tag}")

            return {
                "success": result.returncode == 0,
                "output": output,
                "image_tag": tag,
                "duration": round(duration, 2),
            }

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            return {
                "success": False,
                "output": f"Timeout construyendo imagen Docker (5 min)",
                "image_tag": tag,
                "duration": round(duration, 2),
            }

        except Exception as e:
            return {
                "success": False,
                "output": f"Error construyendo imagen: {str(e)}",
                "image_tag": tag,
                "duration": 0,
            }

    # ----------------------------------------------------------
    # LIMPIEZA DE CONTENEDORES
    # ----------------------------------------------------------
    def cleanup(self) -> dict:
        """Elimina contenedores huerfanos de este sandbox.

        Returns:
            Dict con: {removed_containers, freed_space, errors}
        """
        if not self._docker_available:
            return {
                "removed_containers": 0,
                "freed_space": "0B",
                "errors": ["Docker no disponible"],
            }

        removed = 0
        errors = []

        try:
            # Buscar contenedores del sandbox (incluyendo detenidos)
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", f"name={self._container_prefix}",
                 "--format", "{{.ID}} {{.Names}} {{.Status}}"],
                capture_output=True,
                text=True,
                timeout=15,
            )

            if result.returncode == 0 and result.stdout.strip():
                containers = result.stdout.strip().split("\n")
                for container_line in containers:
                    parts = container_line.split()
                    if len(parts) >= 2:
                        container_id = parts[0]
                        container_name = parts[1]
                        try:
                            # Forzar eliminacion
                            rm_result = subprocess.run(
                                ["docker", "rm", "-f", container_id],
                                capture_output=True,
                                text=True,
                                timeout=10,
                            )
                            if rm_result.returncode == 0:
                                removed += 1
                                logger.info(f"[DockerSandbox] Contenedor eliminado: {container_name}")
                            else:
                                errors.append(f"Error eliminando {container_name}: {rm_result.stderr[:100]}")
                        except Exception as e:
                            errors.append(f"Error eliminando {container_name}: {str(e)[:100]}")

        except subprocess.TimeoutExpired:
            errors.append("Timeout buscando contenedores huerfanos")
        except Exception as e:
            errors.append(f"Error en cleanup: {str(e)[:100]}")

        # Verificar espacio liberado
        freed = "0B"
        try:
            df_result = subprocess.run(
                ["docker", "system", "df", "--format", "{{.Size}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if df_result.returncode == 0:
                freed = df_result.stdout.strip().split("\n")[0] if df_result.stdout.strip() else "0B"
        except Exception:
            pass

        logger.info(f"[DockerSandbox] Cleanup: {removed} contenedores eliminados")
        return {
            "removed_containers": removed,
            "freed_space": freed,
            "errors": errors,
        }

    # ----------------------------------------------------------
    # METODOS AUXILIARES
    # ----------------------------------------------------------
    def _get_language_config(self, language: str) -> Optional[dict]:
        """Retorna la configuracion de ejecucion para un lenguaje."""
        configs = {
            "python": {"ext": ".py", "runner": "python3"},
            "javascript": {"ext": ".js", "runner": "node"},
            "bash": {"ext": ".sh", "runner": "bash"},
            "sh": {"ext": ".sh", "runner": "bash"},
            "typescript": {"ext": ".ts", "runner": "npx"},  # Requiere ts-node en imagen
        }
        return configs.get(language.lower())

    def _get_language_config_by_ext(self, ext: str) -> Optional[dict]:
        """Retorna la configuracion de ejecucion para una extension de archivo."""
        ext_map = {
            ".py": {"runner": "python3"},
            ".js": {"runner": "node"},
            ".sh": {"runner": "bash"},
            ".ts": {"runner": "npx"},
        }
        return ext_map.get(ext)

    def _kill_orphaned_containers(self, filename_hint: str = ""):
        """Intenta matar contenedores huerfanos que puedan estar ejecutando un archivo."""
        try:
            # Buscar contenedores que esten ejecutando el archivo
            result = subprocess.run(
                ["docker", "ps", "-q", "--filter", "ancestor=" + self._image],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                container_ids = result.stdout.strip().split("\n")
                for cid in container_ids:
                    try:
                        subprocess.run(
                            ["docker", "kill", cid],
                            capture_output=True,
                            timeout=5,
                        )
                        logger.info(f"[DockerSandbox] Contenedor huerfano eliminado: {cid[:12]}")
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"[DockerSandbox] Error limpiando contenedores huerfanos: {e}")

    def _fallback_local(
        self,
        code: str,
        language: str = "python",
        timeout: int = 60,
        working_dir: str = None,
        env_vars: dict = None,
    ) -> dict:
        """Fallback a ejecucion local usando code_executor cuando Docker no esta disponible."""
        try:
            from tools.code_executor import execute_code
            result = execute_code(
                code=code,
                language=language,
                timeout=timeout,
                working_dir=working_dir,
                env_vars=env_vars,
            )
            return {
                "success": result.success,
                "stdout": result.stdout[:self._max_output],
                "stderr": result.stderr[:self._max_output],
                "exit_code": result.exit_code,
                "duration": round(result.duration, 2),
                "container_id": None,
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Error en fallback local: {str(e)}",
                "exit_code": -1,
                "duration": 0,
                "container_id": None,
            }

    def _fallback_file_local(self, filepath: str, timeout: int = 60) -> dict:
        """Fallback a ejecucion local de archivo cuando Docker no esta disponible."""
        try:
            from tools.code_executor import execute_file
            result = execute_file(filepath=filepath, timeout=timeout)
            return {
                "success": result.success,
                "stdout": result.stdout[:self._max_output],
                "stderr": result.stderr[:self._max_output],
                "exit_code": result.exit_code,
                "duration": round(result.duration, 2),
                "container_id": None,
            }
        except Exception as e:
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Error en fallback local de archivo: {str(e)}",
                "exit_code": -1,
                "duration": 0,
                "container_id": None,
            }


# ============================================================
# SINGLETON Y FUNCIONES DE CONVENIENCIA
# ============================================================

_sandbox_instance: Optional[DockerSandbox] = None


def get_docker_sandbox() -> DockerSandbox:
    """Retorna la instancia singleton del DockerSandbox."""
    global _sandbox_instance
    if _sandbox_instance is None:
        _sandbox_instance = DockerSandbox()
    return _sandbox_instance


def execute_in_container(
    code: str,
    language: str = "python",
    timeout: int = 60,
    working_dir: str = None,
    env_vars: dict = None,
    allow_network: bool = False,
) -> dict:
    """Ejecuta codigo en un contenedor Docker (wrapper simple del singleton).

    Args:
        code: Codigo fuente a ejecutar
        language: Lenguaje (python, javascript, bash)
        timeout: Timeout en segundos
        working_dir: Directorio de trabajo
        env_vars: Variables de entorno adicionales
        allow_network: Si True, permite acceso a red

    Returns:
        Dict con: {success, stdout, stderr, exit_code, duration, container_id}
    """
    sandbox = get_docker_sandbox()
    return sandbox.execute_in_docker(
        code=code,
        language=language,
        timeout=timeout,
        working_dir=working_dir,
        env_vars=env_vars,
        allow_network=allow_network,
    )
