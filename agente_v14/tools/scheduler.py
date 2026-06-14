"""
=============================================================
AGENTE v22 - Scheduler & Monitoring
=============================================================
Sistema de scheduling y monitoreo para tareas periodicas:

- Cron-like scheduling: ejecuta tareas a intervalos regulares
- File watchers: monitorea cambios en archivos/directorios
- Health checks: verifica periodicamente que los servicios estan ok
- Callbacks: el agente define que hacer cuando se dispara un evento

v22: Primera implementacion - cron scheduler + file watchers
     + health checks + herramientas del agente
=============================================================
"""

import os
import re
import json
import time
import hashlib
import threading
import logging
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

from tools.registry import register_tool
from config import logger

# ============================================================
# CONFIGURACION
# ============================================================

_AGENT_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHEDULES_FILE = os.path.normpath(os.path.join(_AGENT_DIR, "..", "data", "schedules.json"))
_WATCHES_FILE = os.path.normpath(os.path.join(_AGENT_DIR, "..", "data", "file_watches.json"))

# Intervalo minimo entre ejecuciones (segundos)
_MIN_INTERVAL = 60  # 1 minuto

# ============================================================
# CRON SCHEDULER
# ============================================================

class ScheduledTask:
    """Representa una tarea programada."""

    def __init__(self, task_id: str, name: str, instruction: str,
                 interval_seconds: int, enabled: bool = True):
        self.task_id = task_id
        self.name = name
        self.instruction = instruction  # Que debe hacer el agente
        self.interval_seconds = max(interval_seconds, _MIN_INTERVAL)
        self.enabled = enabled
        self.created_at = datetime.now().isoformat()
        self.last_run = None
        self.last_result = ""
        self.run_count = 0
        self.error_count = 0

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "name": self.name,
            "instruction": self.instruction,
            "interval_seconds": self.interval_seconds,
            "enabled": self.enabled,
            "created_at": self.created_at,
            "last_run": self.last_run,
            "last_result": self.last_result[:200] if self.last_result else "",
            "run_count": self.run_count,
            "error_count": self.error_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScheduledTask":
        task = cls(
            task_id=data.get("task_id", ""),
            name=data.get("name", ""),
            instruction=data.get("instruction", ""),
            interval_seconds=data.get("interval_seconds", 300),
            enabled=data.get("enabled", True),
        )
        task.created_at = data.get("created_at", task.created_at)
        task.last_run = data.get("last_run")
        task.last_result = data.get("last_result", "")
        task.run_count = data.get("run_count", 0)
        task.error_count = data.get("error_count", 0)
        return task


class CronScheduler:
    """Scheduler de tareas periodicas estilo cron.

    Ejecuta tareas en un thread daemon, verificando cada N segundos
    cuales tareas necesitan ejecutarse segun su intervalo.

    Las tareas se definen como instrucciones en lenguaje natural
    que el agente ejecutara cuando se dispare el schedule.
    """

    def __init__(self):
        self._tasks: dict[str, ScheduledTask] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._check_interval = 30  # Verificar cada 30 segundos
        self._on_task_trigger: Optional[Callable] = None
        self._load()

    def _load(self) -> None:
        """Carga las tareas programadas desde archivo."""
        if not os.path.exists(_SCHEDULES_FILE):
            return

        try:
            with open(_SCHEDULES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            for task_data in data.get("tasks", []):
                task = ScheduledTask.from_dict(task_data)
                if task.task_id:
                    self._tasks[task.task_id] = task

            logger.debug(f"[Scheduler] Cargadas {len(self._tasks)} tareas programadas")

        except Exception as e:
            logger.warning(f"[Scheduler] Error cargando tareas: {e}")

    def _save(self) -> None:
        """Guarda las tareas programadas a archivo."""
        try:
            os.makedirs(os.path.dirname(_SCHEDULES_FILE), exist_ok=True)

            data = {
                "tasks": [t.to_dict() for t in self._tasks.values()],
                "updated": datetime.now().isoformat(),
            }

            with open(_SCHEDULES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"[Scheduler] Error guardando tareas: {e}")

    def set_callback(self, callback: Callable) -> None:
        """Establece el callback que se ejecuta cuando una tarea se dispara.

        El callback recibe (task_id, instruction) y debe ejecutar
        la instruccion del agente.
        """
        self._on_task_trigger = callback

    def add_task(self, name: str, instruction: str, interval_seconds: int,
                 enabled: bool = True) -> dict:
        """Agrega una tarea programada.

        Args:
            name: Nombre descriptivo de la tarea
            instruction: Instruccion en lenguaje natural para el agente
            interval_seconds: Intervalo en segundos entre ejecuciones
            enabled: Si la tarea esta activa

        Returns:
            Dict con info de la tarea creada
        """
        # Generar ID unico
        task_id = f"task_{hashlib.md5(f'{name}_{time.time()}'.encode()).hexdigest()[:8]}"

        interval_seconds = max(interval_seconds, _MIN_INTERVAL)

        task = ScheduledTask(task_id, name, instruction, interval_seconds, enabled)

        with self._lock:
            self._tasks[task_id] = task
            self._save()

        # Iniciar scheduler si no esta corriendo
        if not self._running and enabled:
            self.start()

        logger.info(f"[Scheduler] Tarea agregada: {name} (cada {interval_seconds}s, id={task_id})")

        return task.to_dict()

    def remove_task(self, task_id: str) -> bool:
        """Elimina una tarea programada."""
        with self._lock:
            if task_id not in self._tasks:
                return False
            del self._tasks[task_id]
            self._save()

        logger.info(f"[Scheduler] Tarea eliminada: {task_id}")
        return True

    def toggle_task(self, task_id: str, enabled: bool = None) -> Optional[dict]:
        """Habilita o deshabilita una tarea."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None

            task.enabled = enabled if enabled is not None else not task.enabled
            self._save()

        return task.to_dict()

    def list_tasks(self) -> list[dict]:
        """Lista todas las tareas programadas."""
        with self._lock:
            return [t.to_dict() for t in self._tasks.values()]

    def get_task(self, task_id: str) -> Optional[dict]:
        """Retorna info de una tarea especifica."""
        with self._lock:
            task = self._tasks.get(task_id)
            return task.to_dict() if task else None

    def start(self) -> None:
        """Inicia el scheduler en un thread daemon."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        logger.info(f"[Scheduler] Iniciado (check interval: {self._check_interval}s)")

    def stop(self) -> None:
        """Detiene el scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[Scheduler] Detenido")

    def _run_loop(self) -> None:
        """Loop principal del scheduler."""
        while self._running:
            try:
                self._check_and_run()
            except Exception as e:
                logger.error(f"[Scheduler] Error en loop: {e}")

            time.sleep(self._check_interval)

    def _check_and_run(self) -> None:
        """Verifica y ejecuta las tareas que necesitan correr."""
        now = time.time()

        with self._lock:
            for task_id, task in self._tasks.items():
                if not task.enabled:
                    continue

                # Verificar si es tiempo de ejecutar
                if task.last_run:
                    last_run_ts = datetime.fromisoformat(task.last_run).timestamp()
                    if now - last_run_ts < task.interval_seconds:
                        continue

                # Ejecutar la tarea
                logger.info(f"[Scheduler] Ejecutando tarea: {task.name} ({task_id})")

                task.last_run = datetime.now().isoformat()
                task.run_count += 1

                try:
                    if self._on_task_trigger:
                        result = self._on_task_trigger(task_id, task.instruction)
                        task.last_result = str(result)[:200] if result else "OK"
                    else:
                        task.last_result = "No hay callback configurado"
                        logger.warning(f"[Scheduler] Tarea {task_id} sin callback")
                except Exception as e:
                    task.error_count += 1
                    task.last_result = f"ERROR: {str(e)[:150]}"
                    logger.error(f"[Scheduler] Error en tarea {task_id}: {e}")

                self._save()

    @property
    def is_running(self) -> bool:
        return self._running


# Singleton
_scheduler: Optional[CronScheduler] = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> CronScheduler:
    """Retorna el singleton de CronScheduler."""
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            if _scheduler is None:
                _scheduler = CronScheduler()
    return _scheduler


# ============================================================
# FILE WATCHER
# ============================================================

class FileWatch:
    """Vigila cambios en archivos o directorios.

    Monitorea modificaciones basandose en mtime y hash de contenido.
    Cuando detecta un cambio, dispara un callback con la info del cambio.
    """

    def __init__(self):
        self._watches: dict[str, dict] = {}  # path -> {pattern, instruction, last_hash, last_mtime, ...}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._check_interval = 10  # Verificar cada 10 segundos
        self._on_change_callback: Optional[Callable] = None
        self._load()

    def _load(self) -> None:
        """Carga los watches desde archivo."""
        if not os.path.exists(_WATCHES_FILE):
            return

        try:
            with open(_WATCHES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            for watch_data in data.get("watches", []):
                path = watch_data.get("path", "")
                if path:
                    self._watches[path] = watch_data

            logger.debug(f"[FileWatch] Cargados {len(self._watches)} watches")

        except Exception as e:
            logger.warning(f"[FileWatch] Error cargando watches: {e}")

    def _save(self) -> None:
        """Guarda los watches a archivo."""
        try:
            os.makedirs(os.path.dirname(_WATCHES_FILE), exist_ok=True)

            data = {
                "watches": list(self._watches.values()),
                "updated": datetime.now().isoformat(),
            }

            with open(_WATCHES_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"[FileWatch] Error guardando watches: {e}")

    def set_callback(self, callback: Callable) -> None:
        """Establece el callback para cambios detectados.

        El callback recibe (path, change_type, instruction).
        """
        self._on_change_callback = callback

    def add_watch(self, path: str, pattern: str = "*", instruction: str = "",
                  recursive: bool = True) -> dict:
        """Agrega un watch sobre un archivo o directorio.

        Args:
            path: Ruta al archivo o directorio a vigilar
            pattern: Patron glob para filtrar archivos (ej: "*.py", "*.log")
            instruction: Instruccion para el agente cuando detecta cambio
            recursive: Si vigilar subdirectorios

        Returns:
            Dict con info del watch creado
        """
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return {"error": f"Ruta no existe: {path}"}

        watch_id = hashlib.md5(path.encode()).hexdigest()[:8]

        watch_data = {
            "watch_id": watch_id,
            "path": path,
            "pattern": pattern,
            "instruction": instruction or f"El archivo {path} ha cambiado. Revisa los cambios.",
            "recursive": recursive,
            "last_hash": self._compute_hash(path, pattern, recursive),
            "last_mtime": self._get_max_mtime(path, pattern, recursive),
            "created_at": datetime.now().isoformat(),
            "trigger_count": 0,
            "enabled": True,
        }

        self._watches[path] = watch_data
        self._save()

        # Iniciar si no esta corriendo
        if not self._running:
            self.start()

        logger.info(f"[FileWatch] Watch agregado: {path} (pattern={pattern})")
        return watch_data

    def remove_watch(self, path: str) -> bool:
        """Elimina un watch."""
        path = os.path.abspath(path)
        if path not in self._watches:
            return False

        del self._watches[path]
        self._save()
        return True

    def list_watches(self) -> list[dict]:
        """Lista todos los watches activos."""
        return list(self._watches.values())

    def start(self) -> None:
        """Inicia el file watcher en un thread daemon."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        logger.info(f"[FileWatch] Iniciado (check interval: {self._check_interval}s)")

    def stop(self) -> None:
        """Detiene el file watcher."""
        self._running = False

    def _run_loop(self) -> None:
        """Loop principal del file watcher."""
        while self._running:
            try:
                self._check_changes()
            except Exception as e:
                logger.error(f"[FileWatch] Error en loop: {e}")

            time.sleep(self._check_interval)

    def _check_changes(self) -> None:
        """Verifica si hubo cambios en los archivos vigilados."""
        for path, watch in list(self._watches.items()):
            if not watch.get("enabled", True):
                continue

            if not os.path.exists(path):
                continue

            # Verificar por mtime primero (rapido)
            current_mtime = self._get_max_mtime(path, watch["pattern"], watch.get("recursive", True))
            last_mtime = watch.get("last_mtime", 0)

            if current_mtime > last_mtime:
                # Cambio detectado - verificar hash para confirmar
                current_hash = self._compute_hash(path, watch["pattern"], watch.get("recursive", True))
                last_hash = watch.get("last_hash", "")

                if current_hash != last_hash:
                    # Cambio confirmado
                    change_type = "modified"
                    watch["last_hash"] = current_hash
                    watch["last_mtime"] = current_mtime
                    watch["trigger_count"] = watch.get("trigger_count", 0) + 1
                    self._save()

                    logger.info(f"[FileWatch] Cambio detectado: {path}")

                    if self._on_change_callback:
                        try:
                            self._on_change_callback(path, change_type, watch["instruction"])
                        except Exception as e:
                            logger.error(f"[FileWatch] Error en callback: {e}")
                else:
                    # Mtime cambio pero hash igual (touch sin contenido)
                    watch["last_mtime"] = current_mtime

    def _compute_hash(self, path: str, pattern: str, recursive: bool) -> str:
        """Computa un hash del contenido de archivos que matchean el patron."""
        hasher = hashlib.md5()

        try:
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    hasher.update(f.read())
            elif os.path.isdir(path):
                import fnmatch
                for root, dirs, files in os.walk(path):
                    for fname in sorted(files):
                        if fnmatch.fnmatch(fname, pattern):
                            fpath = os.path.join(root, fname)
                            try:
                                with open(fpath, "rb") as f:
                                    hasher.update(f.read())
                            except Exception:
                                pass
                    if not recursive:
                        break
        except Exception:
            pass

        return hasher.hexdigest()

    def _get_max_mtime(self, path: str, pattern: str, recursive: bool) -> float:
        """Retorna el mtime mas reciente de los archivos que matchean."""
        max_mtime = 0.0

        try:
            if os.path.isfile(path):
                max_mtime = os.path.getmtime(path)
            elif os.path.isdir(path):
                import fnmatch
                for root, dirs, files in os.walk(path):
                    for fname in files:
                        if fnmatch.fnmatch(fname, pattern):
                            fpath = os.path.join(root, fname)
                            try:
                                mtime = os.path.getmtime(fpath)
                                max_mtime = max(max_mtime, mtime)
                            except Exception:
                                pass
                    if not recursive:
                        break
        except Exception:
            pass

        return max_mtime


# Singleton
_file_watcher: Optional[FileWatch] = None


def get_file_watcher() -> FileWatch:
    """Retorna el singleton de FileWatch."""
    global _file_watcher
    if _file_watcher is None:
        _file_watcher = FileWatch()
    return _file_watcher


# ============================================================
# HEALTH CHECK SYSTEM
# ============================================================

class HealthChecker:
    """Sistema de health checks para servicios criticos.

    Verifica periodicamente que los servicios estan operativos
    y reporta su estado.
    """

    def __init__(self):
        self._checks: dict[str, dict] = {}
        self._results: dict[str, dict] = {}

    def register_check(self, name: str, check_type: str, config: dict = None) -> None:
        """Registra un health check.

        Args:
            name: Nombre del check (ej: "ollama", "chromadb", "disk_space")
            check_type: Tipo de check ("http", "tcp", "disk", "memory", "custom")
            config: Configuracion especifica del tipo de check
        """
        self._checks[name] = {
            "type": check_type,
            "config": config or {},
            "registered_at": datetime.now().isoformat(),
        }

    def run_check(self, name: str) -> dict:
        """Ejecuta un health check especifico.

        Returns:
            Dict con: name, healthy, status, message, duration_ms
        """
        check = self._checks.get(name)
        if not check:
            return {"name": name, "healthy": False, "status": "not_found",
                    "message": f"Health check '{name}' no registrado"}

        check_type = check["type"]
        config = check["config"]
        start = time.time()

        try:
            if check_type == "http":
                result = self._check_http(config)
            elif check_type == "tcp":
                result = self._check_tcp(config)
            elif check_type == "disk":
                result = self._check_disk(config)
            elif check_type == "memory":
                result = self._check_memory(config)
            elif check_type == "ollama":
                result = self._check_ollama(config)
            else:
                result = {"healthy": False, "status": "unknown_type",
                          "message": f"Tipo de check desconocido: {check_type}"}
        except Exception as e:
            result = {"healthy": False, "status": "error",
                      "message": f"Error ejecutando check: {e}"}

        duration_ms = round((time.time() - start) * 1000, 1)
        result.update({
            "name": name,
            "duration_ms": duration_ms,
            "checked_at": datetime.now().isoformat(),
        })

        self._results[name] = result
        return result

    def run_all_checks(self) -> list[dict]:
        """Ejecuta todos los health checks registrados."""
        results = []
        for name in self._checks:
            results.append(self.run_check(name))
        return results

    def get_status(self) -> dict:
        """Retorna el estado actual de todos los checks."""
        # Run all checks
        results = self.run_all_checks()

        healthy_count = sum(1 for r in results if r.get("healthy"))
        total_count = len(results)

        return {
            "overall_healthy": healthy_count == total_count,
            "healthy_count": healthy_count,
            "total_count": total_count,
            "checks": results,
            "checked_at": datetime.now().isoformat(),
        }

    def _check_http(self, config: dict) -> dict:
        """Verifica un endpoint HTTP."""
        import urllib.request
        url = config.get("url", "")
        expected_status = config.get("expected_status", 200)
        timeout = config.get("timeout", 5)

        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == expected_status:
                    return {"healthy": True, "status": "ok",
                            "message": f"HTTP {resp.status}"}
                return {"healthy": False, "status": "wrong_status",
                        "message": f"Expected {expected_status}, got {resp.status}"}
        except Exception as e:
            return {"healthy": False, "status": "unreachable",
                    "message": str(e)[:100]}

    def _check_tcp(self, config: dict) -> dict:
        """Verifica un puerto TCP."""
        import socket
        host = config.get("host", "localhost")
        port = config.get("port", 11434)
        timeout = config.get("timeout", 3)

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()

            if result == 0:
                return {"healthy": True, "status": "ok",
                        "message": f"TCP {host}:{port} reachable"}
            return {"healthy": False, "status": "unreachable",
                    "message": f"TCP {host}:{port} unreachable (code={result})"}
        except Exception as e:
            return {"healthy": False, "status": "error",
                    "message": str(e)[:100]}

    def _check_disk(self, config: dict) -> dict:
        """Verifica espacio en disco."""
        path = config.get("path", "/")
        min_free_gb = config.get("min_free_gb", 1.0)

        try:
            stat = os.statvfs(path)
            free_gb = (stat.f_bavail * stat.f_frsize) / (1024 ** 3)

            if free_gb >= min_free_gb:
                return {"healthy": True, "status": "ok",
                        "message": f"Disk free: {free_gb:.1f} GB"}
            return {"healthy": False, "status": "low_disk",
                    "message": f"Low disk: {free_gb:.1f} GB (min: {min_free_gb} GB)"}
        except Exception as e:
            return {"healthy": False, "status": "error",
                    "message": str(e)[:100]}

    def _check_memory(self, config: dict) -> dict:
        """Verifica memoria disponible."""
        min_free_percent = config.get("min_free_percent", 10.0)

        try:
            with open("/proc/meminfo", "r") as f:
                meminfo = {}
                for line in f:
                    parts = line.split(":")
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip().split()[0]
                        meminfo[key] = int(value)

            total = meminfo.get("MemTotal", 0)
            available = meminfo.get("MemAvailable", 0)

            if total > 0:
                free_percent = (available / total) * 100
                if free_percent >= min_free_percent:
                    return {"healthy": True, "status": "ok",
                            "message": f"Memory: {free_percent:.1f}% free ({available // 1024} MB)"}
                return {"healthy": False, "status": "low_memory",
                        "message": f"Low memory: {free_percent:.1f}% free (min: {min_free_percent}%)"}
            return {"healthy": True, "status": "unknown",
                    "message": "Could not determine memory status"}
        except Exception as e:
            return {"healthy": False, "status": "error",
                    "message": str(e)[:100]}

    def _check_ollama(self, config: dict) -> dict:
        """Verifica que Ollama esta respondiendo."""
        import urllib.request
        url = config.get("url", "http://localhost:11434/api/tags")
        timeout = config.get("timeout", 5)

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    model_count = len(data.get("models", []))
                    return {"healthy": True, "status": "ok",
                            "message": f"Ollama OK: {model_count} modelos disponibles"}
                return {"healthy": False, "status": "error",
                        "message": f"Ollama respondio con HTTP {resp.status}"}
        except Exception as e:
            return {"healthy": False, "status": "unreachable",
                    "message": f"Ollama no disponible: {str(e)[:80]}"}


# Singleton
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Retorna el singleton de HealthChecker."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
        # Registrar checks por defecto
        _health_checker.register_check("ollama", "ollama")
        _health_checker.register_check("disk", "disk", {"path": "/", "min_free_gb": 1.0})
        _health_checker.register_check("memory", "memory", {"min_free_percent": 10.0})
    return _health_checker


# ============================================================
# HERRAMIENTAS REGISTRADAS PARA EL AGENTE
# ============================================================

def _scheduler_tool(accion: str, nombre: str = "", instruccion: str = "",
                    intervalo_segundos: int = 300, tarea_id: str = "") -> str:
    """Gestiona tareas programadas que se ejecutan periodicamente.

    Permite crear, eliminar, listar y controlar tareas que se
    ejecutan automaticamente a intervalos regulares. Las tareas
    son instrucciones en lenguaje natural que el agente ejecutara.

    Acciones:
    - crear: Crea una nueva tarea programada
    - eliminar: Elimina una tarea programada
    - listar: Lista todas las tareas programadas
    - pausar: Deshabilita una tarea temporalmente
    - reanudar: Re-habilita una tarea pausada
    - estado: Muestra el estado del scheduler

    Args:
        accion: Accion a realizar (crear, eliminar, listar, pausar, reanudar, estado)
        nombre: Nombre descriptivo de la tarea (para crear)
        instruccion: Instruccion para el agente cuando se dispare (para crear)
        intervalo_segundos: Intervalo en segundos (min: 60, para crear)
        tarea_id: ID de la tarea (para eliminar, pausar, reanudar)
    """
    scheduler = get_scheduler()
    accion = accion.lower().strip()

    if accion == "crear":
        if not nombre or not instruccion:
            return "ERROR: Se requiere nombre e instruccion para crear una tarea."
        result = scheduler.add_task(nombre, instruccion, intervalo_segundos)
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif accion == "eliminar":
        if not tarea_id:
            return "ERROR: Se requiere tarea_id para eliminar."
        deleted = scheduler.remove_task(tarea_id)
        return f"Tarea {tarea_id} eliminada." if deleted else f"Tarea {tarea_id} no encontrada."

    elif accion == "listar":
        tasks = scheduler.list_tasks()
        if not tasks:
            return "No hay tareas programadas."
        return json.dumps(tasks, ensure_ascii=False, indent=2)

    elif accion == "pausar":
        if not tarea_id:
            return "ERROR: Se requiere tarea_id para pausar."
        result = scheduler.toggle_task(tarea_id, enabled=False)
        if result:
            return f"Tarea '{result['name']}' pausada."
        return f"Tarea {tarea_id} no encontrada."

    elif accion == "reanudar":
        if not tarea_id:
            return "ERROR: Se requiere tarea_id para reanudar."
        result = scheduler.toggle_task(tarea_id, enabled=True)
        if result:
            return f"Tarea '{result['name']}' reanudada."
        return f"Tarea {tarea_id} no encontrada."

    elif accion == "estado":
        tasks = scheduler.list_tasks()
        running = scheduler.is_running
        return json.dumps({
            "running": running,
            "total_tasks": len(tasks),
            "enabled_tasks": sum(1 for t in tasks if t.get("enabled")),
            "disabled_tasks": sum(1 for t in tasks if not t.get("enabled")),
        }, ensure_ascii=False, indent=2)

    else:
        return f"ERROR: Accion '{accion}' no reconocida. Acciones validas: crear, eliminar, listar, pausar, reanudar, estado"


def _file_watcher_tool(accion: str, ruta: str = "", patron: str = "*",
                       instruccion: str = "") -> str:
    """Monitorea cambios en archivos y directorios.

    Vigila modificaciones en archivos y dispara acciones automaticas
    cuando detecta cambios. Usa hash de contenido para evitar falsos
    positivos.

    Acciones:
    - vigilar: Comienza a vigilar un archivo o directorio
    - ignorar: Deja de vigilar una ruta
    - listar: Lista todos los watches activos
    - estado: Muestra el estado del file watcher

    Args:
        accion: Accion a realizar (vigilar, ignorar, listar, estado)
        ruta: Ruta al archivo o directorio a vigilar
        patron: Patron glob para filtrar (ej: "*.py", "*.log", "*.json")
        instruccion: Instruccion para el agente cuando detecte cambio
    """
    watcher = get_file_watcher()
    accion = accion.lower().strip()

    if accion == "vigilar":
        if not ruta:
            return "ERROR: Se requiere la ruta a vigilar."
        result = watcher.add_watch(ruta, patron, instruccion)
        if "error" in result:
            return f"ERROR: {result['error']}"
        return json.dumps(result, ensure_ascii=False, indent=2)

    elif accion == "ignorar":
        if not ruta:
            return "ERROR: Se requiere la ruta a dejar de vigilar."
        removed = watcher.remove_watch(ruta)
        return f"Watch eliminado para {ruta}." if removed else f"No hay watch para {ruta}."

    elif accion == "listar":
        watches = watcher.list_watches()
        if not watches:
            return "No hay watches activos."
        return json.dumps(watches, ensure_ascii=False, indent=2)

    elif accion == "estado":
        watches = watcher.list_watches()
        return json.dumps({
            "running": True,
            "active_watches": len(watches),
        }, ensure_ascii=False, indent=2)

    else:
        return f"ERROR: Accion '{accion}' no reconocida. Acciones validas: vigilar, ignorar, listar, estado"


def _health_check_tool(servicio: str = "", accion: str = "verificar") -> str:
    """Verifica el estado de salud de los servicios del sistema.

    Ejecuta health checks en servicios criticos como Ollama,
    espacio en disco, memoria, y conexiones de red.

    Acciones:
    - verificar: Ejecuta un check especifico o todos
    - estado: Retorna el estado general del sistema

    Args:
        servicio: Servicio a verificar (ollama, disk, memory, o vacio para todos)
        accion: Accion a realizar (verificar, estado)
    """
    checker = get_health_checker()
    accion = accion.lower().strip()

    if accion == "verificar":
        if servicio:
            result = checker.run_check(servicio)
            if result.get("status") == "not_found":
                # Auto-registrar servicios comunes
                if servicio == "ollama":
                    checker.register_check("ollama", "ollama")
                    result = checker.run_check("ollama")
                elif servicio == "disk":
                    checker.register_check("disk", "disk", {"path": "/", "min_free_gb": 1.0})
                    result = checker.run_check("disk")
                elif servicio == "memory":
                    checker.register_check("memory", "memory", {"min_free_percent": 10.0})
                    result = checker.run_check("memory")
            return json.dumps(result, ensure_ascii=False, indent=2)
        else:
            # Ejecutar todos los checks
            status = checker.get_status()
            return json.dumps(status, ensure_ascii=False, indent=2)

    elif accion == "estado":
        status = checker.get_status()
        return json.dumps(status, ensure_ascii=False, indent=2)

    else:
        return f"ERROR: Accion '{accion}' no reconocida. Acciones validas: verificar, estado"


# ============================================================
# REGISTRO DE HERRAMIENTAS
# ============================================================

register_tool(
    "tarea_programada",
    _scheduler_tool,
    schema={
        "type": "function",
        "function": {
            "name": "tarea_programada",
            "description": "Gestiona tareas programadas que se ejecutan periodicamente. Crear, eliminar, pausar, reanudar tareas que corren automaticamente cada N segundos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {"type": "string", "description": "Accion: crear, eliminar, listar, pausar, reanudar, estado"},
                    "nombre": {"type": "string", "description": "Nombre descriptivo de la tarea (para crear)"},
                    "instruccion": {"type": "string", "description": "Instruccion para el agente cuando se dispare (para crear)"},
                    "intervalo_segundos": {"type": "integer", "description": "Intervalo en segundos (minimo 60, para crear)"},
                    "tarea_id": {"type": "string", "description": "ID de la tarea (para eliminar, pausar, reanudar)"},
                },
                "required": ["accion"],
            },
        },
    },
)

register_tool(
    "vigilar_archivo",
    _file_watcher_tool,
    schema={
        "type": "function",
        "function": {
            "name": "vigilar_archivo",
            "description": "Monitorea cambios en archivos y directorios. Cuando detecta un cambio, ejecuta una instruccion automaticamente. Usa hash para evitar falsos positivos.",
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {"type": "string", "description": "Accion: vigilar, ignorar, listar, estado"},
                    "ruta": {"type": "string", "description": "Ruta al archivo o directorio a vigilar"},
                    "patron": {"type": "string", "description": "Patron glob (ej: *.py, *.log, *.json)"},
                    "instruccion": {"type": "string", "description": "Instruccion cuando detecte cambio"},
                },
                "required": ["accion"],
            },
        },
    },
)

register_tool(
    "verificar_salud",
    _health_check_tool,
    schema={
        "type": "function",
        "function": {
            "name": "verificar_salud",
            "description": "Verifica el estado de salud de servicios del sistema: Ollama, espacio en disco, memoria disponible. Retorna si estan operativos o hay problemas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "servicio": {"type": "string", "description": "Servicio a verificar (ollama, disk, memory, o vacio para todos)"},
                    "accion": {"type": "string", "description": "Accion: verificar, estado"},
                },
                "required": [],
            },
        },
    },
)

logger.info("[Scheduler] Herramientas registradas: tarea_programada, vigilar_archivo, verificar_salud")
