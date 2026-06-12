"""
=============================================================
AGENTE v17 - Multi-Agent Orchestrator
=============================================================
Orquesta multiples sub-agentes para ejecutar tareas en
paralelo o secuencia. Cada sub-agente es una instancia
del ReactAgent con su propio contexto.

Estrategias:
- SEQUENTIAL: Ejecuta subtareas una por una
- PARALLEL: Ejecuta subtareas independientes en paralelo
- ADAPTIVE: Decide automaticamente segun dependencias

v17: Multi-agent orchestration para tareas complejas.
=============================================================
"""

import json
import uuid
import traceback
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any, Optional
from concurrent.futures import ThreadPoolExecutor, Future

from config import logger

# Importar herramientas - intentar desde registry, fallback a tools
try:
    from tools.registry import TOOL_FUNCTIONS, TOOL_SCHEMAS
except ImportError:
    try:
        from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
    except ImportError:
        TOOL_FUNCTIONS = {}
        TOOL_SCHEMAS = []

# Importar LLM
try:
    from llm import ollama
except ImportError:
    ollama = None


# ============================================================
# DATA MODEL: SubAgente
# ============================================================

@dataclass
class SubAgent:
    """Representa un sub-agente que ejecuta una subtarea especifica."""

    id: str
    task: str                                   # Descripcion de la tarea
    status: str = "pending"                     # pending / running / completed / failed
    result: Optional[str] = None                # Resultado de la ejecucion
    error: Optional[str] = None                 # Mensaje de error si fallo
    dependencies: list[str] = field(default_factory=list)  # IDs de tareas dependientes
    started_at: Optional[str] = None            # Timestamp inicio
    completed_at: Optional[str] = None          # Timestamp fin

    # Referencia al Future para poder cancelar ejecucion paralela
    _future: Optional[Future] = field(default=None, repr=False)

    def to_dict(self) -> dict:
        """Serializa el sub-agente a diccionario."""
        return {
            "id": self.id,
            "task": self.task,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "dependencies": self.dependencies,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# ============================================================
# ORQUESTADOR MULTI-AGENTE
# ============================================================

class Orchestrator:
    """
    Orquesta multiples sub-agentes para ejecutar tareas complejas.

    Recibe un ExecutionPlan del TaskPlanner y lo ejecuta usando
    sub-agentes ligeros que usan el LLM directamente (sin instanciar
    ReactAgent completo, que seria demasiado costoso).

    Estrategias de ejecucion:
    - sequential: Una tarea a la vez, en orden de dependencias
    - parallel: Tareas sin dependencias mutuas en paralelo
    - adaptive: Decide automaticamente segun el grafo de dependencias
    """

    # Limite de iteraciones del bucle LLM por sub-agente
    MAX_SUBAGENT_ITERATIONS = 5

    def __init__(self):
        self._agents: dict[str, SubAgent] = {}       # Sub-agentes activos
        self._results: dict[str, Any] = {}            # Resultados de sub-agentes completados
        self._max_parallel: int = 3                   # Maximo agentes en paralelo
        self._strategy: str = "adaptive"              # Estrategia por defecto
        self._cancelled: set[str] = set()             # IDs de tareas canceladas
        self._plan_data: Optional[dict] = None        # Referencia al plan original

    # ============================================================
    # METODO PRINCIPAL: ORQUESTAR
    # ============================================================

    def orchestrate(self, plan: dict) -> dict:
        """
        Metodo principal de orquestacion.

        Args:
            plan: ExecutionPlan serializado (de task_planner.to_dict())
                  Debe contener: id, goal, tasks (dict de tareas),
                  status, description

        Returns:
            Dict con resultado de la orquestacion:
            {
                "plan_id": str,
                "goal": str,
                "strategy_used": str,
                "status": "completed" | "partial" | "failed",
                "total_tasks": int,
                "completed_tasks": int,
                "failed_tasks": int,
                "results": dict[str, dict],   # id -> subagent.to_dict()
                "duration_seconds": float,
            }
        """
        inicio = datetime.now()
        self._plan_data = plan

        plan_id = plan.get("id", "unknown")
        goal = plan.get("goal", "")
        tasks_data = plan.get("tasks", {})

        logger.info(f"[Orchestrator] Iniciando orquestacion plan {plan_id}: {goal}")
        logger.info(f"[Orchestrator] {len(tasks_data)} tareas a ejecutar")

        # Resetear estado
        self._agents.clear()
        self._results.clear()
        self._cancelled.clear()

        # Crear sub-agentes desde las tareas del plan
        for task_id, task_info in tasks_data.items():
            sub = SubAgent(
                id=task_id,
                task=task_info.get("title", task_info.get("description", "Tarea sin descripcion")),
                dependencies=task_info.get("dependencies", []),
                status="pending",
            )
            self._agents[task_id] = sub

        if not self._agents:
            logger.warning("[Orchestrator] Plan sin tareas, nada que orquestar")
            return self._build_result(plan_id, goal, "completed", inicio)

        # Determinar estrategia de ejecucion
        strategy = self._strategy
        if strategy == "adaptive":
            strategy = "parallel" if self._should_parallelize(self._agents) else "sequential"
            logger.info(f"[Orchestrator] Estrategia adaptativa: elegida '{strategy}'")

        logger.info(f"[Orchestrator] Ejecutando con estrategia: {strategy}")

        # Ejecutar segun estrategia
        try:
            if strategy == "parallel":
                self._execute_parallel()
            else:
                self._execute_sequential()
        except Exception as e:
            logger.error(f"[Orchestrator] Error durante orquestacion: {e}")
            logger.debug(traceback.format_exc())

        # Determinar estado final
        completed = sum(1 for a in self._agents.values() if a.status == "completed")
        failed = sum(1 for a in self._agents.values() if a.status == "failed")
        total = len(self._agents)

        if completed == total:
            final_status = "completed"
        elif completed > 0:
            final_status = "partial"
        else:
            final_status = "failed"

        # Guardar resultados
        for aid, agent in self._agents.items():
            self._results[aid] = agent.to_dict()

        resultado = self._build_result(plan_id, goal, final_status, inicio)
        resultado["strategy_used"] = strategy

        logger.info(
            f"[Orchestrator] Orquestacion finalizada: {completed}/{total} completadas, "
            f"{failed} fallidas, estado={final_status}"
        )

        return resultado

    # ============================================================
    # EJECUCION SECUENCIAL
    # ============================================================

    def _execute_sequential(self):
        """Ejecuta las tareas una por una respetando el orden de dependencias."""
        remaining = set(self._agents.keys())

        while remaining:
            # Buscar la siguiente tarea ejecutable (pendiente con deps completadas)
            next_id = self._find_executable_task(remaining)

            if next_id is None:
                # No hay tareas ejecutables: verificar si hay bloqueo
                pending = [aid for aid in remaining if self._agents[aid].status == "pending"]
                if pending:
                    logger.warning(
                        f"[Orchestrator] Deadlock detectado: {len(pending)} tareas "
                        f"pendientes sin poder ejecutarse. Marcando como failed."
                    )
                    for aid in pending:
                        self._agents[aid].status = "failed"
                        self._agents[aid].error = "Deadlock: dependencias no resueltas"
                    break
                else:
                    # Todas las restantes ya no estan pendientes
                    break

            agent = self._agents[next_id]
            remaining.discard(next_id)

            # Verificar si fue cancelada
            if next_id in self._cancelled:
                agent.status = "failed"
                agent.error = "Cancelada por el usuario"
                continue

            # Ejecutar sub-agente
            context = self._get_execution_context(agent)
            self._execute_subagent(agent, context)

            # Si fallo pero hay dependientes, los marcamos como bloqueados
            if agent.status == "failed":
                self._mark_dependents_failed(next_id, "Tarea dependiente fallo")

    # ============================================================
    # EJECUCION PARALELA
    # ============================================================

    def _execute_parallel(self):
        """
        Ejecuta tareas en paralelo usando ThreadPoolExecutor.
        Las tareas con dependencias esperan a que sus deps terminen.
        """
        remaining = set(self._agents.keys())
        completed_ids: set[str] = set()

        with ThreadPoolExecutor(max_workers=self._max_parallel) as executor:
            futures: dict[str, Future] = {}

            while remaining or futures:
                # Lanzar todas las tareas ejecutables que no esten en ejecucion
                for aid in list(remaining):
                    if aid in futures:
                        continue
                    agent = self._agents[aid]

                    # Verificar si fue cancelada
                    if aid in self._cancelled:
                        agent.status = "failed"
                        agent.error = "Cancelada por el usuario"
                        remaining.discard(aid)
                        completed_ids.add(aid)
                        continue

                    # Verificar que las dependencias esten completadas
                    deps_met = all(
                        dep_id in completed_ids and self._agents[dep_id].status == "completed"
                        for dep_id in agent.dependencies
                        if dep_id in self._agents
                    )

                    # Verificar si alguna dependencia fallo
                    deps_failed = any(
                        dep_id in completed_ids and self._agents[dep_id].status == "failed"
                        for dep_id in agent.dependencies
                        if dep_id in self._agents
                    )

                    if deps_failed:
                        agent.status = "failed"
                        agent.error = "Tarea dependiente fallo"
                        remaining.discard(aid)
                        completed_ids.add(aid)
                        continue

                    if deps_met:
                        # Lanzar en paralelo
                        context = self._get_execution_context(agent)
                        future = executor.submit(self._execute_subagent, agent, context)
                        futures[aid] = future
                        agent._future = future
                        remaining.discard(aid)

                # Verificar si hay futures completados
                done_futures = {
                    aid: fut for aid, fut in futures.items() if fut.done()
                }

                if not done_futures and futures:
                    # Ninguno termino todavia, esperar un poco
                    import time
                    time.sleep(0.2)
                    continue

                # Recolectar resultados de futures completados
                for aid, fut in done_futures.items():
                    try:
                        fut.result()  # Propaga excepciones si las hubo
                    except Exception as e:
                        logger.error(f"[Orchestrator] Error en future de tarea {aid}: {e}")
                        if self._agents[aid].status == "running":
                            self._agents[aid].status = "failed"
                            self._agents[aid].error = str(e)

                    del futures[aid]
                    completed_ids.add(aid)

                # Si no hay mas tareas pendientes ni futures, terminar
                if not remaining and not futures:
                    break

                # Detectar deadlock
                if not done_futures and not remaining:
                    break

    # ============================================================
    # EJECUCION DE SUB-AGENTE
    # ============================================================

    def _execute_subagent(self, sub_agent: SubAgent, context: dict) -> SubAgent:
        """
        Ejecuta la tarea de un sub-agente usando el LLM directamente.

        No instancia un ReactAgent completo (demasiado costoso). En su lugar:
        1. Crea un prompt enfocado con la tarea, herramientas disponibles, y contexto
        2. Llama al LLM para decidir que herramientas usar
        3. Ejecuta las herramientas y alimenta resultados de vuelta
        4. Repite hasta obtener respuesta final o alcanzar limite de iteraciones

        Args:
            sub_agent: SubAgente a ejecutar (se modifica in-place)
            context: Contexto de tareas previas completadas

        Returns:
            El SubAgent con resultado o error actualizado
        """
        sub_agent.status = "running"
        sub_agent.started_at = datetime.now().isoformat()

        logger.info(f"[Orchestrator] Ejecutando sub-agente {sub_agent.id}: {sub_agent.task[:60]}...")

        try:
            # Construir lista de herramientas disponibles
            tools_list = self._build_tools_description()

            # Bucle de iteraciones del sub-agente
            conversation_history = []
            iteration = 0
            final_answer = None

            # Prompt inicial del sub-agente
            system_prompt = self._build_subagent_prompt(sub_agent, context, tools_list)
            conversation_history.append({"role": "system", "content": system_prompt})
            conversation_history.append({"role": "user", "content": f"Ejecuta tu tarea: {sub_agent.task}"})

            while iteration < self.MAX_SUBAGENT_ITERATIONS:
                iteration += 1
                logger.debug(
                    f"[Orchestrator] Sub-agente {sub_agent.id} iteracion {iteration}/{self.MAX_SUBAGENT_ITERATIONS}"
                )

                # Verificar cancelacion
                if sub_agent.id in self._cancelled:
                    sub_agent.status = "failed"
                    sub_agent.error = "Cancelada durante ejecucion"
                    return sub_agent

                # Llamar al LLM
                if ollama is None:
                    sub_agent.status = "failed"
                    sub_agent.error = "LLM no disponible (ollama=None)"
                    return sub_agent

                llm_response = ollama.generate(conversation_history)

                if not llm_response:
                    logger.warning(f"[Orchestrator] Sub-agente {sub_agent.id}: LLM sin respuesta")
                    sub_agent.status = "failed"
                    sub_agent.error = "LLM no retorno respuesta"
                    return sub_agent

                # Parsear respuesta del LLM
                parsed = self._parse_llm_response(llm_response)

                if parsed.get("final_answer"):
                    # El sub-agente tiene una respuesta final
                    final_answer = parsed["final_answer"]
                    break

                if parsed.get("tool_name"):
                    # El sub-agente quiere usar una herramienta
                    tool_name = parsed["tool_name"]
                    tool_params = parsed.get("tool_params", {})

                    tool_result = self._execute_tool(tool_name, tool_params)

                    # Alimentar resultado de vuelta al LLM
                    conversation_history.append({"role": "assistant", "content": llm_response if isinstance(llm_response, str) else str(llm_response)})
                    conversation_history.append({
                        "role": "user",
                        "content": f"Resultado de {tool_name}: {tool_result}"
                    })
                else:
                    # No hay tool ni final_answer, intentar extraer respuesta del texto
                    if isinstance(llm_response, str) and len(llm_response.strip()) > 10:
                        final_answer = llm_response.strip()
                        break
                    else:
                        # Pedir al LLM que produzca una respuesta concreta
                        conversation_history.append({"role": "assistant", "content": str(llm_response)})
                        conversation_history.append({
                            "role": "user",
                            "content": "Por favor, proporciona tu respuesta final en formato JSON con el campo 'final_answer'."
                        })

            # Determinar resultado final
            if final_answer:
                sub_agent.status = "completed"
                sub_agent.result = final_answer
                logger.info(f"[Orchestrator] Sub-agente {sub_agent.id} completado exitosamente")
            else:
                # No llego a respuesta final pero termino iteraciones
                sub_agent.status = "completed"
                sub_agent.result = (
                    f"Tarea ejecutada ({iteration} iteraciones). "
                    f"Resultado parcial obtenido."
                )
                logger.warning(
                    f"[Orchestrator] Sub-agente {sub_agent.id}: max iteraciones alcanzadas sin respuesta final"
                )

        except Exception as e:
            logger.error(f"[Orchestrator] Sub-agente {sub_agent.id} fallo: {e}")
            logger.debug(traceback.format_exc())
            sub_agent.status = "failed"
            sub_agent.error = str(e)

        finally:
            sub_agent.completed_at = datetime.now().isoformat()

        return sub_agent

    # ============================================================
    # CONSTRUCCION DE PROMPT DE SUB-AGENTE
    # ============================================================

    def _build_subagent_prompt(self, sub_agent: SubAgent, context: dict, tools_list: str) -> str:
        """
        Construye el prompt del sistema para un sub-agente.

        Args:
            sub_agent: Sub-agente que ejecutara
            context: Contexto de tareas previas
            tools_list: Descripcion de herramientas disponibles

        Returns:
            Prompt del sistema para el sub-agente
        """
        # Construir seccion de contexto previo
        context_section = ""
        if context.get("completed_results"):
            context_section = "\n## CONTEXTO DE TAREAS PREVIAS\n"
            for dep_id, dep_result in context["completed_results"].items():
                task_name = dep_result.get("task", "Tarea")
                result_text = dep_result.get("result", "Sin resultado")
                # Truncar resultados largos para no saturar el prompt
                if len(result_text) > 500:
                    result_text = result_text[:500] + "...[truncado]"
                context_section += f"- [{dep_id}] {task_name}: {result_text}\n"

        prompt = (
            "Eres un sub-agente especializado. Tu mision es ejecutar UNA tarea especifica "
            "de forma eficiente y precisa.\n\n"
            f"## TU TAREA\n{sub_agent.task}\n\n"
            f"## HERRAMIENTAS DISPONIBLES\n{tools_list}\n\n"
            f"{context_section}\n"
            "## FORMATO DE RESPUESTA\n"
            "Debes responder SIEMPRE en JSON con este formato exacto:\n"
            '{"thought": "tu razonamiento interno", '
            '"tool_name": "nombre_herramienta_o_vacio", '
            '"tool_params": {}, '
            '"final_answer": "tu respuesta final aqui si ya terminaste"}\n\n'
            "REGLAS:\n"
            "- Si puedes responder directamente sin herramientas, pon tu respuesta en final_answer "
            "y deja tool_name vacio.\n"
            "- Si necesitas una herramienta, pon su nombre en tool_name y los parametros en tool_params, "
            "deja final_answer vacio.\n"
            "- Despues de usar una herramienta, analiza el resultado y decide si necesitas otra "
            "o si ya puedes dar tu respuesta final.\n"
            "- Se conciso y directo. No repitas informacion innecesaria.\n"
            "- Responde en espanol.\n"
        )

        return prompt

    # ============================================================
    # CONTEXTO DE EJECUCION
    # ============================================================

    def _get_execution_context(self, sub_agent: SubAgent) -> dict:
        """
        Construye el contexto de ejecucion a partir de las dependencias completadas.

        Cada sub-agente recibe informacion de lo que ya se hizo antes,
        para que no repita trabajo y pueda construir sobre resultados previos.

        Args:
            sub_agent: Sub-agente que necesita contexto

        Returns:
            Dict con:
            - completed_results: {task_id: {task, result}} de deps completadas
            - failed_deps: lista de IDs de deps que fallaron
        """
        completed_results = {}
        failed_deps = []

        for dep_id in sub_agent.dependencies:
            if dep_id not in self._agents:
                # Dependencia no existe en el plan, ignorar
                continue

            dep_agent = self._agents[dep_id]

            if dep_agent.status == "completed" and dep_agent.result:
                completed_results[dep_id] = {
                    "task": dep_agent.task,
                    "result": dep_agent.result,
                    "completed_at": dep_agent.completed_at,
                }
            elif dep_agent.status == "failed":
                failed_deps.append(dep_id)

        return {
            "completed_results": completed_results,
            "failed_deps": failed_deps,
            "task_id": sub_agent.id,
            "task_description": sub_agent.task,
        }

    # ============================================================
    # ANALISIS DE PARALELIZACION
    # ============================================================

    def _should_parallelize(self, tasks: dict) -> bool:
        """
        Analiza las dependencias de las tareas para determinar si
        hay oportunidades de paralelizacion.

        Retorna True si existen al menos 2 tareas que se pueden
        ejecutar simultaneamente (sin dependencias mutuas).

        Args:
            tasks: Dict de {id: SubAgent} o similar

        Returns:
            True si se puede paralelizar, False si todo es secuencial
        """
        # Contar tareas sin dependencias (se pueden ejecutar de inmediato)
        no_deps = [
            tid for tid, agent in tasks.items()
            if isinstance(agent, SubAgent) and len(agent.dependencies) == 0
        ]

        # Si hay 2+ tareas sin dependencias, vale la pena paralelizar
        if len(no_deps) >= 2:
            return True

        # Analizar si hay "niveles" de dependencias con multiples tareas
        # que se pueden ejecutar en paralelo
        levels = self._build_dependency_levels(tasks)
        for level_tasks in levels.values():
            if len(level_tasks) >= 2:
                return True

        return False

    def _build_dependency_levels(self, tasks: dict) -> dict[int, list[str]]:
        """
        Construye niveles de dependencias (topological sort por niveles).

        Nivel 0: tareas sin dependencias
        Nivel 1: tareas que dependen solo de nivel 0
        Nivel N: tareas que dependen de nivel N-1 como maximo

        Args:
            tasks: Dict de {id: SubAgent}

        Returns:
            Dict {nivel: [task_ids]}
        """
        levels: dict[int, list[str]] = {}
        assigned: set[str] = set()

        # Iterar hasta asignar todas las tareas (o detectar ciclo)
        max_iterations = len(tasks) + 1
        iteration = 0

        while len(assigned) < len(tasks) and iteration < max_iterations:
            iteration += 1

            for tid, agent in tasks.items():
                if tid in assigned:
                    continue

                if not isinstance(agent, SubAgent):
                    assigned.add(tid)
                    continue

                # Todas las dependencias asignadas?
                deps_assigned = all(
                    dep_id in assigned
                    for dep_id in agent.dependencies
                    if dep_id in tasks
                )

                if not deps_assigned:
                    continue

                # Calcular nivel: max nivel de deps + 1
                if not agent.dependencies:
                    level = 0
                else:
                    dep_levels = [
                        self._find_level(levels, dep_id)
                        for dep_id in agent.dependencies
                        if dep_id in tasks
                    ]
                    level = max(dep_levels) + 1 if dep_levels else 0

                levels.setdefault(level, []).append(tid)
                assigned.add(tid)

        return levels

    def _find_level(self, levels: dict[int, list[str]], task_id: str) -> int:
        """Encuentra en que nivel esta una tarea."""
        for lvl, tids in levels.items():
            if task_id in tids:
                return lvl
        return 0

    # ============================================================
    # EJECUCION PARALELA VIA CALLBACK (para ReactAgent)
    # ============================================================

    def execute_parallel(self, descriptions: list[dict], agent_run_fn=None) -> Optional[dict]:
        """
        Ejecuta multiples tareas independientes en paralelo usando ThreadPoolExecutor.

        A diferencia de orchestrate(), este metodo no crea sub-agentes propios
        sino que delega la ejecucion a una funcion callback (tipicamente
        ReactAgent.run). Esto permite que las tareas se beneficien de todo
        el motor ReAct (memoria, metacognicion, herramientas, etc.).

        Args:
            descriptions: Lista de dicts, cada uno con:
                - "id": Identificador de la tarea
                - "description": Descripcion completa de la tarea a ejecutar
                - "context": Contexto previo opcional (JSON string)
            agent_run_fn: Funcion callable que recibe un prompt (str) y retorna
                          un resultado (str o tuple). Si es None, usa el LLM directo.

        Returns:
            Dict {task_id: result} con los resultados de cada tarea,
            o None si hubo un error y se debe hacer fallback a secuencial.
        """
        if not descriptions or len(descriptions) < 2:
            logger.debug("[Orchestrator] execute_parallel: menos de 2 tareas, no vale la pena")
            return None

        results: dict[str, str] = {}
        max_workers = min(len(descriptions), self._max_parallel)

        logger.info(
            f"[Orchestrator] execute_parallel: ejecutando {len(descriptions)} tareas "
            f"en paralelo (max_workers={max_workers})"
        )

        def _run_single(desc: dict) -> tuple[str, str]:
            """Ejecuta una sola tarea y retorna (task_id, result)."""
            task_id = desc.get("id", "unknown")
            description = desc.get("description", "")
            context = desc.get("context", "")

            prompt = description
            if context:
                prompt = f"Contexto previo:\n{context}\n\n{description}"

            try:
                if agent_run_fn:
                    result = agent_run_fn(prompt)
                    # ReactAgent.run puede devolver tuple (respuesta, thinking_log)
                    if isinstance(result, tuple):
                        result = result[0]
                    return (task_id, str(result) if result else "")
                else:
                    # Fallback: usar LLM directo
                    if ollama is None:
                        return (task_id, "ERROR: LLM no disponible")
                    messages = [
                        {"role": "system", "content": "Eres un agente especializado. Ejecuta la tarea de forma concisa y completa."},
                        {"role": "user", "content": prompt},
                    ]
                    llm_result = ollama.generate(messages)
                    return (task_id, str(llm_result) if llm_result else "")
            except Exception as e:
                logger.error(f"[Orchestrator] execute_parallel: tarea {task_id} fallo: {e}")
                return (task_id, f"ERROR: {e}")

        try:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_run_single, desc): desc
                    for desc in descriptions
                }

                for future in as_completed(futures):
                    desc = futures[future]
                    task_id = desc.get("id", "unknown")
                    try:
                        tid, result = future.result()
                        results[tid] = result
                        logger.info(f"[Orchestrator] execute_parallel: tarea {tid} completada ({len(result)} chars)")
                    except Exception as e:
                        logger.error(f"[Orchestrator] execute_parallel: future de {task_id} fallo: {e}")
                        results[task_id] = f"ERROR: {e}"

            logger.info(
                f"[Orchestrator] execute_parallel: completadas {len(results)}/{len(descriptions)} tareas"
            )
            return results

        except Exception as e:
            logger.error(f"[Orchestrator] execute_parallel fallo: {e}")
            logger.debug(traceback.format_exc())
            return None

    # ============================================================
    # EJECUCION DE HERRAMIENTAS
    # ============================================================

    def _execute_tool(self, tool_name: str, tool_params: dict) -> str:
        """
        Ejecuta una herramienta registrada y retorna su resultado.

        Args:
            tool_name: Nombre de la herramienta
            tool_params: Parametros para la herramienta

        Returns:
            Resultado como string, o mensaje de error
        """
        if tool_name not in TOOL_FUNCTIONS:
            return f"Error: Herramienta '{tool_name}' no encontrada. Herramientas disponibles: {list(TOOL_FUNCTIONS.keys())}"

        try:
            func = TOOL_FUNCTIONS[tool_name]

            # Intentar llamar con parametros como kwargs
            if isinstance(tool_params, dict):
                result = func(**tool_params)
            elif tool_params:
                result = func(tool_params)
            else:
                result = func()

            # Truncar resultado si es muy largo
            result_str = str(result) if result is not None else ""
            max_len = 2000
            if len(result_str) > max_len:
                result_str = result_str[:max_len] + f"...[truncado, {len(result_str)} chars total]"

            logger.info(f"[Orchestrator] Herramienta {tool_name} ejecutada exitosamente")
            return result_str

        except TypeError as e:
            # Parametros incorrectos, intentar sin parametros
            logger.warning(f"[Orchestrator] Error de parametros en {tool_name}: {e}")
            try:
                result = func()
                return str(result) if result is not None else ""
            except Exception:
                return f"Error: Parametros incorrectos para {tool_name}. Esperado: {e}"
        except Exception as e:
            logger.error(f"[Orchestrator] Error ejecutando {tool_name}: {e}")
            return f"Error ejecutando {tool_name}: {str(e)}"

    # ============================================================
    # PARSER DE RESPUESTA LLM
    # ============================================================

    def _parse_llm_response(self, response) -> dict:
        """
        Parsea la respuesta del LLM para extraer accion o respuesta final.

        El LLM deberia responder en JSON con:
        {thought, tool_name, tool_params, final_answer}

        Pero a veces devuelve texto plano o JSON malformado,
        asi que parseamos de forma robusta.

        Args:
            response: Respuesta del LLM (str o dict)

        Returns:
            Dict con: thought, tool_name, tool_params, final_answer
        """
        # Si ya es dict (respuesta con tool_calls de Ollama)
        if isinstance(response, dict):
            # Formato de tool calling nativo de Ollama
            if "tool_calls" in response:
                tc = response["tool_calls"][0] if response["tool_calls"] else {}
                func = tc.get("function", {})
                return {
                    "thought": response.get("content", ""),
                    "tool_name": func.get("name", ""),
                    "tool_params": func.get("arguments", {}),
                    "final_answer": "",
                }
            # Respuesta con contenido
            content = response.get("content", "")
            if content:
                return self._parse_json_response(content)
            return {"thought": "", "tool_name": "", "tool_params": {}, "final_answer": ""}

        # Si es string, intentar parsear como JSON
        if isinstance(response, str):
            return self._parse_json_response(response)

        # Fallback
        return {"thought": "", "tool_name": "", "tool_params": {}, "final_answer": str(response)}

    def _parse_json_response(self, text: str) -> dict:
        """
        Parsea un string de texto intentando extraer JSON.

        Intenta multiples estrategias:
        1. Parsear todo el texto como JSON
        2. Buscar JSON dentro de bloques de codigo
        3. Buscar JSON entre llaves
        4. Si nada funciona, usar el texto como final_answer

        Args:
            text: Texto de respuesta del LLM

        Returns:
            Dict con: thought, tool_name, tool_params, final_answer
        """
        default = {"thought": "", "tool_name": "", "tool_params": {}, "final_answer": ""}

        # Estrategia 1: Parsear todo como JSON
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict):
                return {
                    "thought": parsed.get("thought", parsed.get("pensamiento", "")),
                    "tool_name": parsed.get("tool_name", parsed.get("accion", "")),
                    "tool_params": parsed.get("tool_params", parsed.get("params", {})),
                    "final_answer": parsed.get("final_answer", parsed.get("respuesta_final", "")),
                }
        except (json.JSONDecodeError, ValueError):
            pass

        # Estrategia 2: Buscar JSON en bloques de codigo
        import re
        json_block = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if json_block:
            try:
                parsed = json.loads(json_block.group(1).strip())
                if isinstance(parsed, dict):
                    return {
                        "thought": parsed.get("thought", parsed.get("pensamiento", "")),
                        "tool_name": parsed.get("tool_name", parsed.get("accion", "")),
                        "tool_params": parsed.get("tool_params", parsed.get("params", {})),
                        "final_answer": parsed.get("final_answer", parsed.get("respuesta_final", "")),
                    }
            except (json.JSONDecodeError, ValueError):
                pass

        # Estrategia 3: Buscar JSON entre llaves mas externo
        brace_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if brace_match:
            try:
                parsed = json.loads(brace_match.group(0))
                if isinstance(parsed, dict):
                    return {
                        "thought": parsed.get("thought", parsed.get("pensamiento", "")),
                        "tool_name": parsed.get("tool_name", parsed.get("accion", "")),
                        "tool_params": parsed.get("tool_params", parsed.get("params", {})),
                        "final_answer": parsed.get("final_answer", parsed.get("respuesta_final", "")),
                    }
            except (json.JSONDecodeError, ValueError):
                pass

        # Estrategia 4: Usar todo el texto como final_answer
        default["final_answer"] = text.strip()
        default["thought"] = "Respuesta directa sin formato JSON"
        return default

    # ============================================================
    # UTILIDADES DE HERRAMIENTAS
    # ============================================================

    def _build_tools_description(self) -> str:
        """
        Construye una descripcion legible de las herramientas disponibles
        para incluir en el prompt del sub-agente.

        Returns:
            String con la lista de herramientas y sus parametros
        """
        if not TOOL_SCHEMAS:
            # Fallback: usar nombres de funciones
            names = list(TOOL_FUNCTIONS.keys())
            return "Herramientas: " + ", ".join(names) if names else "Sin herramientas disponibles"

        descriptions = []
        for schema in TOOL_SCHEMAS:
            func_info = schema.get("function", {})
            name = func_info.get("name", "unknown")
            desc = func_info.get("description", "")
            params = func_info.get("parameters", {})
            properties = params.get("properties", {})
            required = params.get("required", [])

            # Construir firma simplificada
            param_strs = []
            for pname, pinfo in properties.items():
                ptype = pinfo.get("type", "any")
                is_req = pname in required
                param_strs.append(f"{pname}: {ptype}" + ("" if is_req else " (opcional)"))

            signature = f"{name}({', '.join(param_strs)})"
            line = f"- {signature}"
            if desc:
                # Truncar descripcion larga
                short_desc = desc[:80] + "..." if len(desc) > 80 else desc
                line += f" - {short_desc}"

            descriptions.append(line)

        return "\n".join(descriptions)

    # ============================================================
    # BUSQUEDA DE TAREAS EJECUTABLES
    # ============================================================

    def _find_executable_task(self, remaining: set[str]) -> Optional[str]:
        """
        Encuentra la siguiente tarea que se puede ejecutar:
        pendiente y con todas sus dependencias completadas.

        Args:
            remaining: Conjunto de IDs de tareas que faltan

        Returns:
            ID de la siguiente tarea ejecutable, o None
        """
        for aid in remaining:
            agent = self._agents.get(aid)
            if not agent or agent.status != "pending":
                continue

            # Verificar que todas las dependencias esten completadas
            all_deps_done = True
            for dep_id in agent.dependencies:
                if dep_id not in self._agents:
                    # Dependencia fuera del plan, ignorar
                    continue
                dep_status = self._agents[dep_id].status
                if dep_status != "completed":
                    all_deps_done = False
                    break

            if all_deps_done:
                return aid

        return None

    # ============================================================
    # MARCAR DEPENDIENTES COMO FALLIDOS
    # ============================================================

    def _mark_dependents_failed(self, failed_id: str, reason: str):
        """
        Marca como fallidas todas las tareas que dependen de la tarea fallida.

        Args:
            failed_id: ID de la tarea que fallo
            reason: Razon del fallo para propagar
        """
        for aid, agent in self._agents.items():
            if failed_id in agent.dependencies and agent.status == "pending":
                agent.status = "failed"
                agent.error = f"Bloqueada: {reason} (depende de {failed_id})"
                logger.warning(
                    f"[Orchestrator] Tarea {aid} marcada como fallida: depende de {failed_id}"
                )

    # ============================================================
    # CONSTRUIR RESULTADO FINAL
    # ============================================================

    def _build_result(self, plan_id: str, goal: str, status: str, inicio: datetime) -> dict:
        """
        Construye el diccionario de resultado de la orquestacion.

        Args:
            plan_id: ID del plan
            goal: Objetivo del plan
            status: Estado final (completed/partial/failed)
            inicio: Timestamp de inicio

        Returns:
            Dict con resultado completo
        """
        duracion = (datetime.now() - inicio).total_seconds()
        total = len(self._agents)
        completed = sum(1 for a in self._agents.values() if a.status == "completed")
        failed = sum(1 for a in self._agents.values() if a.status == "failed")

        return {
            "plan_id": plan_id,
            "goal": goal,
            "strategy_used": self._strategy,
            "status": status,
            "total_tasks": total,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "results": {aid: agent.to_dict() for aid, agent in self._agents.items()},
            "duration_seconds": round(duracion, 2),
            "progress_pct": round(completed / total * 100, 1) if total > 0 else 0,
        }

    # ============================================================
    # ESTADO Y CONTROL
    # ============================================================

    def get_status(self) -> dict:
        """
        Retorna el estado actual de la orquestacion.

        Returns:
            Dict con:
            - active_agents: lista de sub-agentes corriendo
            - pending_tasks: lista de tareas pendientes
            - completed_tasks: lista de tareas completadas
            - failed_tasks: lista de tareas fallidas
            - progress_pct: porcentaje de progreso
            - strategy: estrategia actual
        """
        active = [a.to_dict() for a in self._agents.values() if a.status == "running"]
        pending = [a.to_dict() for a in self._agents.values() if a.status == "pending"]
        completed = [a.to_dict() for a in self._agents.values() if a.status == "completed"]
        failed = [a.to_dict() for a in self._agents.values() if a.status == "failed"]

        total = len(self._agents)
        done = len(completed)
        progress = round(done / total * 100, 1) if total > 0 else 0

        return {
            "active_agents": active,
            "pending_tasks": pending,
            "completed_tasks": completed,
            "failed_tasks": failed,
            "progress_pct": progress,
            "total_tasks": total,
            "strategy": self._strategy,
            "plan_id": self._plan_data.get("id") if self._plan_data else None,
            "goal": self._plan_data.get("goal") if self._plan_data else None,
        }

    def cancel(self, task_id: str) -> bool:
        """
        Cancela una tarea de sub-agente en ejecucion o pendiente.

        Si la tarea esta en un ThreadPoolExecutor, intenta cancelar el Future.
        Si esta pendiente, la marca para no ejecutarse.

        Args:
            task_id: ID de la tarea a cancelar

        Returns:
            True si se cancelo exitosamente, False si no se encontro
        """
        if task_id not in self._agents:
            logger.warning(f"[Orchestrator] cancel: tarea {task_id} no encontrada")
            return False

        agent = self._agents[task_id]

        if agent.status == "completed":
            logger.warning(f"[Orchestrator] cancel: tarea {task_id} ya completada")
            return False

        # Marcar como cancelada
        self._cancelled.add(task_id)

        # Si esta corriendo, intentar cancelar el Future
        if agent.status == "running" and agent._future is not None:
            cancelled = agent._future.cancel()
            if cancelled:
                agent.status = "failed"
                agent.error = "Cancelada por el usuario"
                agent.completed_at = datetime.now().isoformat()
                logger.info(f"[Orchestrator] Tarea {task_id} cancelada (Future cancelado)")
                return True

        # Si esta pendiente, simplemente marcar
        if agent.status == "pending":
            agent.status = "failed"
            agent.error = "Cancelada por el usuario"
            logger.info(f"[Orchestrator] Tarea {task_id} cancelada (pendiente)")
            return True

        # Si esta corriendo pero no se pudo cancelar el Future,
        # el flag _cancelled hara que se detecte en la siguiente iteracion
        logger.info(f"[Orchestrator] Tarea {task_id} marcada para cancelacion")
        return True

    def set_strategy(self, strategy: str):
        """
        Establece la estrategia de ejecucion.

        Args:
            strategy: "sequential", "parallel", o "adaptive"
        """
        valid = {"sequential", "parallel", "adaptive"}
        if strategy not in valid:
            logger.warning(f"[Orchestrator] Estrategia invalida: {strategy}. Validas: {valid}")
            return
        self._strategy = strategy
        logger.info(f"[Orchestrator] Estrategia cambiada a: {strategy}")

    def set_max_parallel(self, max_parallel: int):
        """
        Establece el maximo de sub-agentes en paralelo.

        Args:
            max_parallel: Numero maximo (minimo 1, maximo 10)
        """
        self._max_parallel = max(1, min(10, max_parallel))
        logger.info(f"[Orchestrator] Max paralelo ajustado a: {self._max_parallel}")

    def reset(self):
        """Resetea el estado del orquestador para una nueva ejecucion."""
        self._agents.clear()
        self._results.clear()
        self._cancelled.clear()
        self._plan_data = None
        logger.info("[Orchestrator] Estado reseteado")


# ============================================================
# INSTANCIA SINGLETON
# ============================================================

_orchestrator: Optional[Orchestrator] = None

def get_orchestrator() -> Orchestrator:
    """Obtiene o crea la instancia singleton del orquestador."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
