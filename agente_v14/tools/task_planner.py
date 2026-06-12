"""
=============================================================
AGENTE v16 - Planificador de Tareas Jerarquico
=============================================================
Descompone tareas complejas en subtareas ejecutables,
gestiona dependencias, y orquesta la ejecucion.

Ejemplo: "Construyeme una app web" -> 
  1. Diseñar arquitectura
  2. Crear proyecto (npm init)
  3. Implementar modelos
  4. Crear APIs
  5. Construir frontend
  6. Escribir tests
  7. Verificar funcionamiento

v16: Motor de planificacion con descomposicion automatica.
=============================================================
"""

import os
import json
import uuid
import logging
import re
import time
from datetime import datetime
from enum import Enum
from typing import Optional

from config import LEARN_DIR, logger

# Importar cliente Ollama con manejo graceful de errores
try:
    from llm import ollama
    _LLM_AVAILABLE = True
except ImportError:
    ollama = None
    _LLM_AVAILABLE = False
    logger.warning("[Planner] Modulo llm no disponible, descomposicion LLM deshabilitada")

# Importar modulo de recuperacion de errores con manejo graceful
try:
    from tools.error_recovery import diagnose_error, record_error_fix
    _ERROR_RECOVERY_AVAILABLE = True
except ImportError:
    try:
        from error_recovery import diagnose_error, record_error_fix
        _ERROR_RECOVERY_AVAILABLE = True
    except ImportError:
        diagnose_error = None
        record_error_fix = None
        _ERROR_RECOVERY_AVAILABLE = False
        logger.warning("[Planner] Modulo error_recovery no disponible, auto-diagnostico deshabilitado")

# ============================================================
# ESTADOS DE TAREAS
# ============================================================

class TaskStatus(str, Enum):
    PENDING = "pending"
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ============================================================
# MODELO DE TAREA
# ============================================================

class Task:
    """Representa una tarea individual dentro de un plan."""

    def __init__(self, title: str, description: str = "",
                 priority: TaskPriority = TaskPriority.MEDIUM,
                 dependencies: list = None, parent_id: str = None):
        self.id = str(uuid.uuid4())[:8]
        self.title = title
        self.description = description
        self.priority = priority
        self.status = TaskStatus.PENDING
        self.dependencies = dependencies or []
        self.parent_id = parent_id
        self.subtasks: list[str] = []
        self.result: Optional[str] = None
        self.error: Optional[str] = None
        self.created_at = datetime.now().isoformat()
        self.started_at: Optional[str] = None
        self.completed_at: Optional[str] = None
        self.tool_calls: list[dict] = []
        self.attempts = 0
        self.max_attempts = 3

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "dependencies": self.dependencies,
            "parent_id": self.parent_id,
            "subtasks": self.subtasks,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "attempts": self.attempts,
            "tool_calls": self.tool_calls,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        task = cls(
            title=data.get("title", ""),
            description=data.get("description", ""),
            priority=TaskPriority(data.get("priority", "medium")),
            dependencies=data.get("dependencies", []),
            parent_id=data.get("parent_id"),
        )
        task.id = data.get("id", task.id)
        task.status = TaskStatus(data.get("status", "pending"))
        task.result = data.get("result")
        task.error = data.get("error")
        task.subtasks = data.get("subtasks", [])
        task.attempts = data.get("attempts", 0)
        task.created_at = data.get("created_at", task.created_at)
        task.started_at = data.get("started_at")
        task.completed_at = data.get("completed_at")
        task.tool_calls = data.get("tool_calls", [])
        return task


# ============================================================
# PLAN DE EJECUCION
# ============================================================

class ExecutionPlan:
    """Plan de ejecucion que contiene tareas organizadas con dependencias."""

    def __init__(self, goal: str, description: str = ""):
        self.id = str(uuid.uuid4())[:8]
        self.goal = goal
        self.description = description
        self.tasks: dict[str, Task] = {}
        self.created_at = datetime.now().isoformat()
        self.status = TaskStatus.PLANNING
        self.current_task_id: Optional[str] = None
        # Seguimiento de progreso avanzado (v16+)
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.total_execution_time: float = 0.0  # Tiempo total en segundos
        self.decomposition_method: str = "template"  # "template" o "llm"

    def add_task(self, task: Task) -> str:
        """Agrega una tarea al plan."""
        self.tasks[task.id] = task
        # Si tiene parent, agregar como subtarea
        if task.parent_id and task.parent_id in self.tasks:
            self.tasks[task.parent_id].subtasks.append(task.id)
        return task.id

    def get_next_task(self) -> Optional[Task]:
        """Obtiene la proxima tarea ejecutable (pendiente y sin dependencias)."""
        for task in self.tasks.values():
            if task.status != TaskStatus.PENDING:
                continue
            # Verificar que todas las dependencias esten completadas
            deps_met = all(
                self.tasks.get(dep_id, Task("")).status == TaskStatus.COMPLETED
                for dep_id in task.dependencies
                if dep_id in self.tasks
            )
            if deps_met:
                return task
        return None

    def get_task(self, task_id: str) -> Optional[Task]:
        return self.tasks.get(task_id)

    def mark_in_progress(self, task_id: str):
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.IN_PROGRESS
            self.tasks[task_id].started_at = datetime.now().isoformat()
            self.current_task_id = task_id
            self.status = TaskStatus.IN_PROGRESS

    def mark_completed(self, task_id: str, result: str = ""):
        if task_id in self.tasks:
            self.tasks[task_id].status = TaskStatus.COMPLETED
            self.tasks[task_id].result = result
            self.tasks[task_id].completed_at = datetime.now().isoformat()
            if self.current_task_id == task_id:
                self.current_task_id = None
            # Verificar si el plan esta completo
            if all(t.status == TaskStatus.COMPLETED for t in self.tasks.values()):
                self.status = TaskStatus.COMPLETED

    def mark_failed(self, task_id: str, error: str = ""):
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.status = TaskStatus.FAILED
            task.error = error
            task.attempts += 1
            # Si puede reintentar, volver a pending
            if task.attempts < task.max_attempts:
                task.status = TaskStatus.PENDING
                logger.info(f"[Planner] Reintentando tarea {task.title} (intento {task.attempts}/{task.max_attempts})")

    def get_progress(self) -> dict:
        """Retorna progreso del plan."""
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in self.tasks.values() if t.status == TaskStatus.FAILED)
        in_progress = sum(1 for t in self.tasks.values() if t.status == TaskStatus.IN_PROGRESS)
        pending = sum(1 for t in self.tasks.values() if t.status == TaskStatus.PENDING)

        return {
            "plan_id": self.id,
            "goal": self.goal,
            "total": total,
            "completed": completed,
            "failed": failed,
            "in_progress": in_progress,
            "pending": pending,
            "progress_pct": round(completed / total * 100, 1) if total > 0 else 0,
            "status": self.status.value,
            "decomposition_method": self.decomposition_method,
            "total_execution_time": round(self.total_execution_time, 2),
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "description": self.description,
            "status": self.status.value,
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
            "created_at": self.created_at,
            "current_task_id": self.current_task_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_execution_time": self.total_execution_time,
            "decomposition_method": self.decomposition_method,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionPlan":
        plan = cls(goal=data.get("goal", ""), description=data.get("description", ""))
        plan.id = data.get("id", plan.id)
        plan.status = TaskStatus(data.get("status", "planning"))
        plan.created_at = data.get("created_at", plan.created_at)
        plan.current_task_id = data.get("current_task_id")
        plan.started_at = data.get("started_at")
        plan.finished_at = data.get("finished_at")
        plan.total_execution_time = data.get("total_execution_time", 0.0)
        plan.decomposition_method = data.get("decomposition_method", "template")
        for tid, tdata in data.get("tasks", {}).items():
            plan.tasks[tid] = Task.from_dict(tdata)
        return plan


# ============================================================
# MOTOR DE PLANIFICACION
# ============================================================

class TaskPlanner:
    """Motor de planificacion que descompone objetivos en tareas ejecutables."""

    # Templates de descomposicion para tareas comunes
    TASK_TEMPLATES = {
        "web_app": [
            {"title": "Disenar arquitectura", "desc": "Definir estructura del proyecto, stack tecnologico, y componentes principales", "priority": "critical"},
            {"title": "Crear proyecto base", "desc": "Inicializar proyecto con package.json, configuracion, y estructura de carpetas", "priority": "critical", "deps": [0]},
            {"title": "Implementar base de datos", "desc": "Crear schema, modelos, y migraciones", "priority": "high", "deps": [1]},
            {"title": "Crear APIs backend", "desc": "Implementar endpoints REST/GraphQL con logica de negocio", "priority": "high", "deps": [2]},
            {"title": "Construir frontend", "desc": "Crear componentes UI, paginas, y navegacion", "priority": "high", "deps": [1]},
            {"title": "Integrar frontend con backend", "desc": "Conectar APIs, manejar estado, y datos en tiempo real", "priority": "high", "deps": [3, 4]},
            {"title": "Escribir tests", "desc": "Tests unitarios y de integracion para backend y frontend", "priority": "medium", "deps": [5]},
            {"title": "Verificar y documentar", "desc": "Ejecutar tests, verificar funcionamiento, crear README", "priority": "medium", "deps": [6]},
        ],
        "script": [
            {"title": "Analizar requisitos", "desc": "Definir que hace el script, entradas, salidas, y dependencias", "priority": "critical"},
            {"title": "Escribir codigo", "desc": "Implementar la logica del script", "priority": "high", "deps": [0]},
            {"title": "Probar y corregir", "desc": "Ejecutar el script, verificar salida, corregir errores", "priority": "high", "deps": [1]},
            {"title": "Documentar", "desc": "Agregar comentarios, help text, y README si aplica", "priority": "low", "deps": [2]},
        ],
        "automation": [
            {"title": "Identificar proceso", "desc": "Definir que proceso automatizar, pasos manuales actuales, y objetivo", "priority": "critical"},
            {"title": "Disenar flujo", "desc": "Crear diagrama de flujo con pasos, condiciones, y manejo de errores", "priority": "high", "deps": [0]},
            {"title": "Implementar automatizacion", "desc": "Escribir codigo/script para cada paso del flujo", "priority": "high", "deps": [1]},
            {"title": "Probar en seco", "desc": "Ejecutar sin efectos reales, verificar logica", "priority": "high", "deps": [2]},
            {"title": "Ejecutar y monitorear", "desc": "Ejecutar con datos reales, monitorear resultado, ajustar si necesario", "priority": "medium", "deps": [3]},
        ],
        "analysis": [
            {"title": "Recopilar datos", "desc": "Buscar y obtener los datos necesarios para el analisis", "priority": "critical"},
            {"title": "Limpiar y procesar", "desc": "Normalizar, filtrar, y estructurar los datos", "priority": "high", "deps": [0]},
            {"title": "Analizar", "desc": "Aplicar metodos de analisis, calcular metricas, identificar patrones", "priority": "high", "deps": [1]},
            {"title": "Generar reporte", "desc": "Crear visualizaciones y reporte con hallazgos", "priority": "medium", "deps": [2]},
        ],
        "project_setup": [
            {"title": "Clonar repositorio", "desc": "Clonar el repositorio y revisar estructura", "priority": "critical"},
            {"title": "Instalar dependencias", "desc": "Instalar todas las dependencias del proyecto", "priority": "critical", "deps": [0]},
            {"title": "Configurar entorno", "desc": "Crear archivos .env, configurar variables, setup inicial", "priority": "high", "deps": [1]},
            {"title": "Verificar funcionamiento", "desc": "Ejecutar proyecto, verificar que funciona correctamente", "priority": "high", "deps": [2]},
        ],
    }

    # Palabras clave para detectar tipo de tarea
    TASK_TYPE_KEYWORDS = {
        "web_app": ["web app", "aplicacion web", "pagina web", "website", "sitio web", "frontend", "fullstack", "dashboard", "app web", "aplicacion"],
        "script": ["script", "automatizar", "automatizacion", "batch", "proceso", "tarea automatica"],
        "automation": ["automatizar", "automatizacion", "flujo", "workflow", "pipeline", "cron", "programar"],
        "analysis": ["analizar", "analisis", "datos", "estadisticas", "metricas", "reporte", "grafico"],
        "project_setup": ["clonar", "instalar", "setup", "configurar proyecto", "iniciar proyecto"],
    }

    def __init__(self):
        self._plans: dict[str, ExecutionPlan] = {}
        self._active_plan_id: Optional[str] = None
        self._plans_dir = os.path.join(LEARN_DIR, "plans")
        os.makedirs(self._plans_dir, exist_ok=True)
        # Umbral de score para decidir si usar template o LLM
        self._template_score_threshold = 1
        # Tracking de tiempos de ejecucion por tarea
        self._task_start_times: dict[str, float] = {}

    def detect_task_type(self, goal: str) -> str:
        """Detecta el tipo de tarea basado en palabras clave.

        Args:
            goal: Objetivo del usuario

        Returns:
            Tipo de tarea detectado
        """
        goal_lower = goal.lower()
        best_match = "script"  # default
        best_score = 0

        for task_type, keywords in self.TASK_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in goal_lower)
            if score > best_score:
                best_score = score
                best_match = task_type

        return best_match

    def create_plan(self, goal: str, task_type: str = None) -> ExecutionPlan:
        """Crea un plan de ejecucion descomponiendo el objetivo en tareas.

        Args:
            goal: Objetivo del usuario
            task_type: Tipo de tarea (auto-detectado si no se especifica)

        Returns:
            ExecutionPlan con las tareas descompuestas
        """
        if not task_type:
            task_type = self.detect_task_type(goal)

        plan = ExecutionPlan(goal=goal, description=f"Plan tipo: {task_type}")

        # Obtener template
        template = self.TASK_TEMPLATES.get(task_type, self.TASK_TEMPLATES["script"])

        # Crear tareas desde template
        task_ids = []
        for i, step in enumerate(template):
            task = Task(
                title=step["title"],
                description=step.get("desc", ""),
                priority=TaskPriority(step.get("priority", "medium")),
                dependencies=[task_ids[d] for d in step.get("deps", [])],
            )
            task_id = plan.add_task(task)
            task_ids.append(task_id)

        # Guardar plan
        self._plans[plan.id] = plan
        self._active_plan_id = plan.id
        self._save_plan(plan)

        logger.info(f"[Planner] Plan creado: {plan.id} - {goal} ({len(plan.tasks)} tareas, tipo: {task_type})")
        return plan

    def create_custom_plan(self, goal: str, tasks: list[dict]) -> ExecutionPlan:
        """Crea un plan con tareas personalizadas.

        Args:
            goal: Objetivo del usuario
            tasks: Lista de dicts con title, description, priority, dependencies

        Returns:
            ExecutionPlan con las tareas personalizadas
        """
        plan = ExecutionPlan(goal=goal)
        task_ids = []

        for task_data in tasks:
            deps = [task_ids[d] for d in task_data.get("dependencies", []) if d < len(task_ids)]
            task = Task(
                title=task_data.get("title", "Tarea"),
                description=task_data.get("description", ""),
                priority=TaskPriority(task_data.get("priority", "medium")),
                dependencies=deps,
            )
            task_id = plan.add_task(task)
            task_ids.append(task_id)

        self._plans[plan.id] = plan
        self._active_plan_id = plan.id
        self._save_plan(plan)

        logger.info(f"[Planner] Plan custom creado: {plan.id} - {goal} ({len(plan.tasks)} tareas)")
        return plan

    # ============================================================
    # DESCOMPOSICION CON LLM
    # ============================================================

    def decompose_with_llm(self, goal: str) -> ExecutionPlan:
        """Descompone una tarea usando el LLM local (Ollama) en vez de templates.

        Envia el objetivo al LLM con un prompt estructurado pidiendo
        subtareas en formato JSON. Si el LLM falla o no esta disponible,
        cae de vuelta al metodo basado en templates.

        Args:
            goal: Objetivo del usuario a descomponer

        Returns:
            ExecutionPlan con las subtareas generadas por el LLM
        """
        # Verificar que el LLM este disponible
        if not _LLM_AVAILABLE or ollama is None:
            logger.warning("[Planner] LLM no disponible, usando template como fallback")
            return self.create_plan(goal)

        # Construir prompt estructurado para descomposicion
        prompt = (
            "Eres un planificador de proyectos experto. Descompone la siguiente tarea en subtareas ejecutables.\n"
            "\n"
            f"Tarea: {goal}\n"
            "\n"
            "Responde SOLO con JSON en este formato exacto (sin markdown, sin backticks):\n"
            "[\n"
            "  {{\n"
            '    "title": "Nombre corto de la subtarea",\n'
            '    "description": "Descripcion detallada de que hacer",\n'
            '    "priority": "critical|high|medium|low",\n'
            '    "dependencies": [0, 1]\n'
            "  }}\n"
            "]\n"
            "\n"
            "Reglas:\n"
            "- Cada subtarea debe ser especifica y ejecutable por un agente de software\n"
            "- Las dependencias son indices (0-based) de subtareas anteriores\n"
            "- La primera subtarea (indice 0) no debe tener dependencias\n"
            "- Ordena de forma que las dependencias se resuelvan antes\n"
            "- Incluye pasos de verificacion/testing cuando sea apropiado\n"
            "- Minimo 3 subtareas, maximo 10\n"
        )

        try:
            # Llamar al LLM con timeout
            logger.info(f"[Planner] Solicitando descomposicion LLM para: {goal[:80]}...")
            messages = [{"role": "user", "content": prompt}]
            response = ollama.generate(messages, timeout_overwrite=120)

            if not response or not isinstance(response, str):
                logger.warning("[Planner] LLM retorno respuesta vacia o invalida, usando template")
                return self.create_plan(goal)

            # Limpiar respuesta: remover markdown code blocks si el LLM los incluyo
            cleaned = response.strip()
            if cleaned.startswith("```"):
                # Remover bloques de codigo markdown
                cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned)
                cleaned = re.sub(r'\n?```\s*$', '', cleaned)
                cleaned = cleaned.strip()

            # Parsear JSON
            subtasks_data = json.loads(cleaned)

            # Validar estructura basica
            if not isinstance(subtasks_data, list) or len(subtasks_data) == 0:
                logger.warning("[Planner] LLM retorno JSON vacio o invalido, usando template")
                return self.create_plan(goal)

            # Crear plan desde la respuesta del LLM
            plan = ExecutionPlan(goal=goal, description="Plan generado por LLM")
            plan.decomposition_method = "llm"
            task_ids = []

            for i, subtask in enumerate(subtasks_data):
                # Validar campos requeridos
                if not isinstance(subtask, dict):
                    continue

                title = subtask.get("title", f"Subtarea {i+1}")
                description = subtask.get("description", "")
                priority_str = subtask.get("priority", "medium")

                # Validar que el priority sea valido
                try:
                    priority = TaskPriority(priority_str)
                except ValueError:
                    priority = TaskPriority.MEDIUM

                # Resolver dependencias: indices -> task_ids
                raw_deps = subtask.get("dependencies", [])
                deps = []
                if isinstance(raw_deps, list):
                    for dep_idx in raw_deps:
                        if isinstance(dep_idx, int) and 0 <= dep_idx < len(task_ids):
                            deps.append(task_ids[dep_idx])

                task = Task(
                    title=title,
                    description=description,
                    priority=priority,
                    dependencies=deps,
                )
                task_id = plan.add_task(task)
                task_ids.append(task_id)

            # Validar que el plan tenga al menos 1 tarea
            if len(plan.tasks) == 0:
                logger.warning("[Planner] Plan LLM sin tareas validas, usando template")
                return self.create_plan(goal)

            # Guardar plan
            self._plans[plan.id] = plan
            self._active_plan_id = plan.id
            self._save_plan(plan)

            logger.info(
                f"[Planner] Plan LLM creado: {plan.id} - {goal[:50]}... "
                f"({len(plan.tasks)} tareas)"
            )
            return plan

        except json.JSONDecodeError as e:
            logger.error(f"[Planner] Error parseando JSON del LLM: {e}, usando template")
            return self.create_plan(goal)
        except Exception as e:
            logger.error(f"[Planner] Error en descomposicion LLM: {e}, usando template")
            return self.create_plan(goal)

    # ============================================================
    # ROUTER INTELIGENTE DE DESCOMPOSICION
    # ============================================================

    def smart_decompose(self, goal: str) -> ExecutionPlan:
        """Router inteligente: elige entre template o LLM segun la complejidad del goal.

        Flujo:
        1. Intenta hacer match del goal con templates via palabras clave
        2. Si el score de match es bajo (no coincide bien con ningun template),
           usa descomposicion LLM para obtener un plan personalizado
        3. Si el LLM falla, cae de vuelta al template (el mejor match disponible)
        4. Registra que metodo se uso para analisis posterior

        Args:
            goal: Objetivo del usuario

        Returns:
            ExecutionPlan generado por el metodo mas apropiado
        """
        # Paso 1: Calcular score de match con templates
        goal_lower = goal.lower()
        best_match = "script"  # default
        best_score = 0

        for task_type, keywords in self.TASK_TYPE_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in goal_lower)
            if score > best_score:
                best_score = score
                best_match = task_type

        logger.info(
            f"[Planner] smart_decompose: goal='{goal[:60]}...' "
            f"best_match={best_match} score={best_score} "
            f"threshold={self._template_score_threshold}"
        )

        # Paso 2: Si el score es bajo, intentar LLM
        if best_score < self._template_score_threshold:
            logger.info(
                f"[Planner] Score bajo ({best_score} < {self._template_score_threshold}), "
                f"intentando descomposicion LLM"
            )
            try:
                plan = self.decompose_with_llm(goal)
                if plan and len(plan.tasks) > 0 and plan.decomposition_method == "llm":
                    logger.info(
                        f"[Planner] smart_decompose: usando LLM "
                        f"(plan {plan.id}, {len(plan.tasks)} tareas)"
                    )
                    return plan
                else:
                    logger.info("[Planner] smart_decompose: LLM retorno fallback a template")
            except Exception as e:
                logger.warning(f"[Planner] smart_decompose: LLM fallo ({e}), usando template")

        # Paso 3: Usar template (fallback o score alto)
        plan = self.create_plan(goal, task_type=best_match)
        logger.info(
            f"[Planner] smart_decompose: usando template '{best_match}' "
            f"(plan {plan.id}, {len(plan.tasks)} tareas, score={best_score})"
        )
        return plan

    # ============================================================
    # VALIDACION DE PLANES
    # ============================================================

    def validate_plan(self, plan: ExecutionPlan) -> dict:
        """Valida un plan de ejecucion verificando integridad y coherencia.

        Verifica:
        - Que el plan tenga al menos 1 tarea
        - Que todas las referencias de dependencias existan
        - Que no haya dependencias circulares
        - Advertencias sobre posibles problemas

        Args:
            plan: ExecutionPlan a validar

        Returns:
            Dict con: {valid: bool, issues: list[str], warnings: list[str]}
        """
        issues = []
        warnings = []

        # Verificar que el plan tenga al menos 1 tarea
        if len(plan.tasks) == 0:
            issues.append("El plan no tiene tareas")

        # Mapear IDs de tareas para verificacion rapida
        task_ids = set(plan.tasks.keys())

        # Verificar que todas las dependencias referenciadas existan
        for task_id, task in plan.tasks.items():
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    issues.append(
                        f"Tarea '{task.title}' (id={task_id}) depende de "
                        f"id={dep_id} que no existe en el plan"
                    )

        # Detectar dependencias circulares usando DFS
        # Construir grafo de dependencias
        def _has_cycle(task_id: str, visited: set, rec_stack: set) -> bool:
            """Detecta ciclos usando DFS con pila de recursion."""
            visited.add(task_id)
            rec_stack.add(task_id)

            task = plan.tasks.get(task_id)
            if task:
                for dep_id in task.dependencies:
                    if dep_id not in visited:
                        if _has_cycle(dep_id, visited, rec_stack):
                            return True
                    elif dep_id in rec_stack:
                        return True

            rec_stack.remove(task_id)
            return False

        visited: set = set()
        for task_id in plan.tasks:
            if task_id not in visited:
                if _has_cycle(task_id, visited, set()):
                    issues.append("Se detecto una dependencia circular en el plan")
                    break  # No necesitamos reportar multiples veces

        # Advertencias (no invalidan el plan, pero son utiles)
        # Verificar que la primera tarea no tenga dependencias
        first_task = next(iter(plan.tasks.values())) if plan.tasks else None
        if first_task and first_task.dependencies:
            warnings.append(
                f"La primera tarea '{first_task.title}' tiene dependencias, "
                f"lo que podria bloquear el inicio del plan"
            )

        # Verificar tareas sin dependencias pero no primera (posblemente aisladas)
        task_list = list(plan.tasks.values())
        for i, task in enumerate(task_list):
            if i > 0 and not task.dependencies:
                warnings.append(
                    f"Tarea '{task.title}' (posicion {i}) no tiene dependencias "
                    f"pero no es la primera tarea"
                )

        # Verificar que existan tareas con prioridad critical o high
        high_priority = sum(
            1 for t in plan.tasks.values()
            if t.priority in (TaskPriority.CRITICAL, TaskPriority.HIGH)
        )
        if high_priority == 0:
            warnings.append("Ninguna tarea tiene prioridad critical o high")

        # Verificar tareas con maximos reintentos ya alcanzados
        for task in plan.tasks.values():
            if task.attempts >= task.max_attempts and task.status == TaskStatus.FAILED:
                warnings.append(
                    f"Tarea '{task.title}' alcanzo maximo de intentos "
                    f"({task.max_attempts}) y sigue fallida"
                )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }

    def get_active_plan(self) -> Optional[ExecutionPlan]:
        """Retorna el plan activo actual."""
        if self._active_plan_id:
            return self._plans.get(self._active_plan_id)
        return None

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        """Retorna un plan por ID."""
        return self._plans.get(plan_id)

    def advance_plan(self, result: str = "", tool_calls: list[dict] = None) -> Optional[Task]:
        """Avanza el plan activo: marca la tarea actual como completada y retorna la siguiente.

        Mejorado (v16+):
        - Trackea tiempo total de ejecucion del plan
        - Registra las herramientas usadas en cada tarea
        - Inicializa el timestamp de inicio del plan si es la primera tarea

        Args:
            result: Resultado de la tarea completada
            tool_calls: Lista de llamadas a herramientas ejecutadas en esta tarea

        Returns:
            Siguiente tarea ejecutable o None si el plan esta completo
        """
        plan = self.get_active_plan()
        if not plan:
            return None

        # Marcar tarea actual como completada
        if plan.current_task_id:
            current_task = plan.get_task(plan.current_task_id)

            # Calcular tiempo de ejecucion de la tarea
            if plan.current_task_id in self._task_start_times:
                task_elapsed = time.time() - self._task_start_times[plan.current_task_id]
                plan.total_execution_time += task_elapsed
                del self._task_start_times[plan.current_task_id]
                task_title = current_task.title if current_task else "desconocida"
                logger.debug(
                    f"[Planner] Tarea '{task_title}' "
                    f"tomo {task_elapsed:.1f}s"
                )

            # Registrar herramientas usadas en la tarea
            if tool_calls and current_task:
                current_task.tool_calls.extend(tool_calls)

            plan.mark_completed(plan.current_task_id, result)

            # Verificar si el plan esta completo
            if plan.status == TaskStatus.COMPLETED:
                plan.finished_at = datetime.now().isoformat()
                logger.info(
                    f"[Planner] Plan {plan.id} completado! "
                    f"Tiempo total: {plan.total_execution_time:.1f}s"
                )

            self._save_plan(plan)

        # Obtener siguiente tarea
        next_task = plan.get_next_task()
        if next_task:
            plan.mark_in_progress(next_task.id)
            # Registrar tiempo de inicio de la tarea
            self._task_start_times[next_task.id] = time.time()
            # Inicializar tiempo de inicio del plan si es la primera tarea
            if plan.started_at is None:
                plan.started_at = datetime.now().isoformat()
            self._save_plan(plan)

        return next_task

    def fail_current_task(self, error: str = "", tool_name: str = "",
                          context: dict = None) -> Optional[Task]:
        """Marca la tarea actual como fallida y retorna la siguiente.

        Mejorado (v16+):
        - Auto-diagnostica el error usando error_recovery si esta disponible
        - Registra el diagnostico para aprendizaje futuro
        - Trackea tiempo de ejecucion incluso en fallos

        Args:
            error: Descripcion del error
            tool_name: Nombre de la herramienta que fallo (opcional)
            context: Contexto adicional del error (comando, parametros, etc.)

        Returns:
            Siguiente tarea ejecutable o None
        """
        plan = self.get_active_plan()
        if not plan:
            return None

        if plan.current_task_id:
            # Trackear tiempo de ejecucion de la tarea fallida
            if plan.current_task_id in self._task_start_times:
                task_elapsed = time.time() - self._task_start_times[plan.current_task_id]
                plan.total_execution_time += task_elapsed
                del self._task_start_times[plan.current_task_id]

            # Auto-diagnosticar error si error_recovery esta disponible
            if _ERROR_RECOVERY_AVAILABLE and diagnose_error and error:
                try:
                    diagnosis = diagnose_error(error, tool_name=tool_name, context=context)
                    # Adjuntar diagnostico al error de la tarea
                    current_task = plan.get_task(plan.current_task_id)
                    if current_task:
                        current_task.error = (
                            f"{error}\n[Diagnostico: {diagnosis.get('error_type', 'unknown')} "
                            f"({diagnosis.get('severity', '?')})] "
                            f"Causa: {diagnosis.get('root_cause', '?')}"
                        )
                    logger.info(
                        f"[Planner] Auto-diagnostico: {diagnosis.get('error_type', 'unknown')} "
                        f"({diagnosis.get('severity', '?')}) - "
                        f"{diagnosis.get('root_cause', '?')[:100]}"
                    )
                    # Registrar en historial de errores para aprendizaje
                    if record_error_fix:
                        record_error_fix(diagnosis, fix_applied=None, fix_success=None)
                except Exception as diag_err:
                    logger.debug(f"[Planner] Error en auto-diagnostico: {diag_err}")

            plan.mark_failed(plan.current_task_id, error)
            self._save_plan(plan)

        return plan.get_next_task()

    def replan(self, reason: str = "") -> Optional[ExecutionPlan]:
        """Re-planifica el plan actual basado en el motivo dado.

        Args:
            reason: Motivo de la re-planificacion

        Returns:
            Nuevo plan o None
        """
        plan = self.get_active_plan()
        if not plan:
            return None

        logger.info(f"[Planner] Re-planificando {plan.id}: {reason}")

        # Marcar tareas pendientes como canceladas
        for task in plan.tasks.values():
            if task.status == TaskStatus.PENDING:
                task.status = TaskStatus.CANCELLED

        # Crear nuevo plan con el mismo objetivo
        new_plan = self.create_plan(plan.goal)
        return new_plan

    def get_progress(self) -> dict:
        """Retorna el progreso del plan activo."""
        plan = self.get_active_plan()
        if not plan:
            return {"active": False}
        return {**plan.get_progress(), "active": True}

    def list_plans(self) -> list[dict]:
        """Lista todos los planes."""
        return [
            {"id": p.id, "goal": p.goal, "status": p.status.value,
             "progress": p.get_progress()["progress_pct"]}
            for p in self._plans.values()
        ]

    def _save_plan(self, plan: ExecutionPlan):
        """Persiste un plan a disco."""
        try:
            filepath = os.path.join(self._plans_dir, f"plan_{plan.id}.json")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(plan.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"[Planner] Error guardando plan: {e}")

    def load_plans(self):
        """Carga planes existentes desde disco."""
        try:
            for fname in os.listdir(self._plans_dir):
                if fname.startswith("plan_") and fname.endswith(".json"):
                    filepath = os.path.join(self._plans_dir, fname)
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    plan = ExecutionPlan.from_dict(data)
                    self._plans[plan.id] = plan
                    logger.info(f"[Planner] Plan cargado: {plan.id} - {plan.goal}")
        except Exception as e:
            logger.error(f"[Planner] Error cargando planes: {e}")


# ============================================================
# INSTANCIA SINGLETON
# ============================================================

_planner: Optional[TaskPlanner] = None

def get_planner() -> TaskPlanner:
    """Obtiene o crea la instancia singleton del planificador."""
    global _planner
    if _planner is None:
        _planner = TaskPlanner()
        _planner.load_plans()
    return _planner
