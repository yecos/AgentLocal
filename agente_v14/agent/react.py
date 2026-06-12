"""
=============================================================
AGENTE v19 - Motor ReAct
=============================================================
Piensa -> Actua -> Observa -> Piensa de nuevo -> Repite.
v19: + Direct Intent Parser - ejecuta herramientas sin depender
      del LLM para generar JSON. Los modelos locales fallan mucho
      en formato JSON, asi que ahora parseamos la intencion
      directamente del mensaje del usuario.
v18: + Model Router, Orchestrator delegation, Scaffolding/Deploy tools
v14.3: Streaming REAL token-a-token, metacognicion integrada,
       optimizacion de contexto y llamadas API.
       Usa TripleMemory como unica fuente de historial.
=============================================================
"""

import os
import re
import json
import logging
from datetime import datetime

from config import (
    REPOS_DIR, MAX_REACT_ITERATIONS, MAX_CONVERSATION_MEMORY, logger,
    USER_PROFILE_FILE
)
from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
from memory.triple_memory import TripleMemory, learning
from llm import ollama
from agent.schemas import SYSTEM_PROMPT, JSON_TOOLS_PROMPT, SYSTEM_PROMPT_COMPACT, JSON_TOOLS_PROMPT_COMPACT
from agent.metacognition import Metacognition
from utils.metrics import get_metrics

# Importar orquestador con fallback graceful
try:
    from agent.orchestrator import Orchestrator, get_orchestrator
    ORCHESTRATOR_AVAILABLE = True
except Exception:
    ORCHESTRATOR_AVAILABLE = False

# Importar enriquecimiento de skills con fallback graceful
try:
    from tools.skill_loader import enrich_prompt_with_skills
    SKILLS_ENRICHMENT_AVAILABLE = True
except Exception:
    SKILLS_ENRICHMENT_AVAILABLE = False

# Importar model router con fallback graceful
try:
    from tools.model_router import get_router
    MODEL_ROUTER_AVAILABLE = True
except Exception:
    MODEL_ROUTER_AVAILABLE = False

# Importar Direct Intent Parser con fallback graceful
try:
    from tools.direct_intent import get_intent_parser, parse_direct_intent
    DIRECT_INTENT_AVAILABLE = True
except Exception:
    DIRECT_INTENT_AVAILABLE = False


class ReactAgent:
    """Motor ReAct: Piensa -> Actua -> Observa -> Piensa de nuevo."""

    # Rate limiting: max llamadas a la misma herramienta por conversacion
    MAX_SAME_TOOL_CALLS = 5
    MAX_TOTAL_TOOL_CALLS = 12

    # Palabras clave para detectar tareas complejas que se benefician de planificacion
    _COMPLEX_TASK_KEYWORDS = [
        "construir", "crear app", "desarrollar", "automatizar", "implementar",
        "build", "create app", "desarrolla", "hazme una app", "proyecto"
    ]

    def __init__(self, memory=None):
        self.memory = memory or TripleMemory()
        self.thinking_log = []
        self.supports_tool_calling = None
        self.metacognition = Metacognition()
        self._models_cache = None  # Cache de modelos para no llamar API cada vez
        self._tool_call_counts = {}  # Rate limiting por herramienta
        self._total_tool_calls = 0   # Total de tool calls en esta conversacion
        self.orchestrator = get_orchestrator() if ORCHESTRATOR_AVAILABLE else None
        self.intent_parser = get_intent_parser() if DIRECT_INTENT_AVAILABLE else None

    # ----------------------------------------------------------
    # DIRECT INTENT PARSER (v19)
    # Ejecuta herramientas directamente sin pasar por el LLM
    # cuando la intención del usuario es clara.
    # ----------------------------------------------------------
    def _try_direct_intent(self, user_message: str):
        """
        Intenta ejecutar la herramienta directamente basándose en
        pattern matching del mensaje del usuario.

        Returns:
            (response, thinking_log) si la intención fue ejecutada directamente
            None si no se detectó intención clara (dejar al LLM decidir)
        """
        if not self.intent_parser:
            return None

        result = parse_direct_intent(user_message)
        if result is None:
            return None

        tool_name, params, confidence = result

        # Solo ejecutar directamente si la confianza es alta
        if confidence < 0.80:
            self._log(f"Direct intent detectado pero confianza baja ({confidence}): {tool_name}", "intent")
            return None

        # No ejecutar directamente herramientas que tienen side effects significativos
        # a menos que la confianza sea muy alta
        high_risk_tools = {"ejecutar_comando", "escribir_archivo", "matar_proceso", "git_operacion"}
        if tool_name in high_risk_tools and confidence < 0.95:
            self._log(f"Direct intent: herramienta de riesgo ({tool_name}), requiere confianza 0.95+, tiene {confidence}", "intent")
            return None

        self._log(f"Direct intent detectado: {tool_name}({params}) [confianza={confidence}]", "intent")

        # Ejecutar la herramienta directamente
        try:
            tool_fn = TOOL_FUNCTIONS.get(tool_name)
            if not tool_fn:
                self._log(f"Direct intent: herramienta no encontrada: {tool_name}", "warning")
                return None

            # Filtrar params vacíos o None
            clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
            if not clean_params:
                # La herramienta necesita parámetros pero no los pudimos extraer
                self._log(f"Direct intent: parámetros vacíos para {tool_name}, dejando al LLM", "intent")
                return None

            tool_result = tool_fn(**clean_params)

            # Formatear respuesta amigable
            self._log(f"Direct intent ejecutado exitosamente: {tool_name}", "success")
            self._save_interaction(user_message, tool_result)

            return tool_result, self.thinking_log

        except Exception as e:
            self._log(f"Direct intent falló: {tool_name} -> {e}", "error")
            # No retornar error, dejar que el LLM lo intente
            return None

    def _try_direct_intent_stream(self, user_message: str):
        """
        Versión streaming del Direct Intent Parser.
        Yields eventos SSE para la UI.

        Returns:
            Generator de eventos SSE si la intención fue ejecutada directamente
            None si no se detectó intención clara
        """
        if not self.intent_parser:
            return None

        result = parse_direct_intent(user_message)
        if result is None:
            return None

        tool_name, params, confidence = result

        # Solo ejecutar directamente si la confianza es alta
        if confidence < 0.80:
            self._log(f"Direct intent detectado pero confianza baja ({confidence}): {tool_name}", "intent")
            return None

        # No ejecutar directamente herramientas de riesgo sin confianza muy alta
        high_risk_tools = {"ejecutar_comando", "escribir_archivo", "matar_proceso", "git_operacion"}
        if tool_name in high_risk_tools and confidence < 0.95:
            self._log(f"Direct intent: herramienta de riesgo ({tool_name}), requiere confianza 0.95+, tiene {confidence}", "intent")
            return None

        self._log(f"Direct intent detectado (stream): {tool_name}({params}) [confianza={confidence}]", "intent")

        # Generar eventos de streaming
        def _stream_direct():
            # Evento: pensamiento
            yield {
                "type": "thinking",
                "data": {
                    "phase": "direct_intent",
                    "message": f"Ejecutando directamente: {tool_name}",
                    "iteration": 1,
                    "confidence": confidence,
                }
            }

            # Evento: tool start
            yield {
                "type": "tool_start",
                "data": {
                    "name": tool_name,
                    "params": params,
                }
            }

            # Ejecutar la herramienta
            try:
                tool_fn = TOOL_FUNCTIONS.get(tool_name)
                if not tool_fn:
                    self._log(f"Direct intent: herramienta no encontrada: {tool_name}", "warning")
                    return

                clean_params = {k: v for k, v in params.items() if v is not None and v != ""}
                if not clean_params:
                    self._log(f"Direct intent: parámetros vacíos para {tool_name}, dejando al LLM", "intent")
                    return

                tool_result = tool_fn(**clean_params)

                # Evento: tool result
                yield {
                    "type": "tool_result",
                    "data": {
                        "tool": {"name": tool_name},
                        "result": tool_result[:500] if tool_result else "(sin resultado)",
                    }
                }

                self._log(f"Direct intent ejecutado exitosamente (stream): {tool_name}", "success")

                # Evento: respuesta final
                yield {
                    "type": "text",
                    "data": tool_result if tool_result else "(sin resultado)",
                }

                # Guardar interacción
                self._save_interaction(user_message, tool_result or "(sin resultado)")

                # Evento: done
                yield {
                    "type": "done",
                    "data": tool_result if tool_result else "(sin resultado)",
                    "thinking_log": self.thinking_log,
                    "meta_status": self.metacognition.get_status() if hasattr(self, 'metacognition') else {},
                }

            except Exception as e:
                self._log(f"Direct intent falló (stream): {tool_name} -> {e}", "error")
                yield {
                    "type": "error",
                    "data": f"Error ejecutando {tool_name}: {e}",
                }

        return _stream_direct()

    def _log(self, message, category="info"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.thinking_log.append(f"[{timestamp}] [{category.upper()}] {message}")

    # ----------------------------------------------------------
    # RUN SIN STREAMING (original, para compatibilidad)
    # ----------------------------------------------------------
    def run(self, user_message):
        """
        Bucle ReAct principal. Retorna (respuesta, thinking_log).
        """
        self.thinking_log = []
        self.metacognition.reset()
        self._tool_call_counts = {}
        self._total_tool_calls = 0
        self._log(f"Mensaje del usuario: {user_message}", "input")

        # *** NUEVO v19: Direct Intent Parser ***
        # Intentar ejecutar directamente si la intención es clara
        # Esto evita depender del LLM para generar JSON válido
        direct_result = self._try_direct_intent(user_message)
        if direct_result is not None:
            return direct_result

        messages = self._build_messages(user_message)

        if self.supports_tool_calling is None:
            self.supports_tool_calling = self._detect_tool_calling_support()
            self._log(
                f"Tool calling nativo: {'SI' if self.supports_tool_calling else 'NO (usando JSON fallback)'}",
                "info"
            )

        for iteration in range(MAX_REACT_ITERATIONS):
            self._log(f"--- Iteracion {iteration + 1}/{MAX_REACT_ITERATIONS} ---", "react")

            # *** FIX: Metacognicion ANTES de decidir la accion ***
            # Antes: se evaluaba DESPUES de actuar (paso 4→5→2)
            # Ahora: se evalua ANTES (paso 2→3→4) para mejor toma de decisiones
            meta_prompt = self.metacognition.get_metacognitive_prompt(iteration)
            if meta_prompt:
                self._log("Alerta metacognitiva inyectada ANTES de accion", "evaluation")
                self._inject_metacognitive_prompt(messages, meta_prompt)

            # Verificar si metacognicion indica que necesitamos mas contexto
            if self.metacognition.confidence < 0.3 and iteration > 0:
                extra_context = self.memory.get_context_for(user_message)
                if extra_context and not any(extra_context[:50] in str(m.get("content", "")) for m in messages[-3:]):
                    self._log("Metacognicion: inyectando contexto adicional de memoria", "evaluation")
                    # No re-agregar contexto que ya esta en mensajes
                    context_added = False
                    for m in messages[-3:]:
                        if "CONTEXTO DE MEMORIA" in m.get("content", ""):
                            context_added = True
                            break
                    if not context_added:
                        messages.append({
                            "role": "user",
                            "content": f"[Contexto adicional relevante]:\n{extra_context[:500]}\n\nUsa esta informacion si es relevante."
                        })
            
            # *** NUEVO: AUTO-BUSQUEDA WEB cuando la confianza baja y no se ha buscado ***
            if self.metacognition.confidence < 0.5 and iteration > 0:
                web_tools = ["buscar_web", "buscar_web_profundo", "leer_web"]
                already_searched = any(t in self.metacognition.tool_history for t in web_tools)
                
                if not already_searched:
                    self._log("Confianza baja: ejecutando busqueda web automatica", "cloud")
                    try:
                        search_result = TOOL_FUNCTIONS["buscar_web"](consulta=user_message)
                        if search_result and "No se encontraron" not in search_result:
                            self._log(f"Busqueda web automatica exitosa: {search_result[:150]}...", "cloud")
                            # Inyectar resultados como contexto
                            messages.append({
                                "role": "user", 
                                "content": f"[RESULTADO DE BUSQUEDA WEB AUTOMATICA]:\n{search_result[:1500]}\n\nUsa esta informacion para responder. Si necesitas mas detalle, usa leer_web o buscar_web_profundo."
                            })
                            # Guardar en memoria
                            self.memory.remember(
                                f"Busqueda web para '{user_message[:50]}': {search_result[:300]}",
                                metadata={"type": "web_search", "query": user_message[:50]},
                                fast=True
                            )
                            self.metacognition.record_iteration(
                                iteration=iteration, action_type="tool_call", 
                                tool_name="buscar_web", result_summary=search_result[:100]
                            )
                            self.metacognition.confidence = min(0.7, self.metacognition.confidence + 0.2)
                        else:
                            self._log("Busqueda web automatica sin resultados", "warning")
                    except Exception as e:
                        self._log(f"Error en busqueda web automatica: {e}", "error")
                
                # Si ya se busco pero confianza sigue baja, intentar busqueda profunda
                elif "buscar_web_profundo" not in self.metacognition.tool_history and self.metacognition.confidence < 0.4:
                    self._log("Confianza muy baja tras busqueda: ejecutando busqueda profunda", "cloud")
                    try:
                        deep_result = TOOL_FUNCTIONS["buscar_web_profundo"](consulta=user_message)
                        if deep_result and len(deep_result) > 200:
                            self._log(f"Busqueda profunda exitosa: {deep_result[:150]}...", "cloud")
                            messages.append({
                                "role": "user",
                                "content": f"[RESULTADO DE BUSQUEDA PROFUNDA]:\n{deep_result[:2000]}\n\nResponde al usuario usando esta informacion detallada."
                            })
                            self.memory.remember(
                                f"Busqueda profunda para '{user_message[:50]}': {deep_result[:400]}",
                                metadata={"type": "web_search_deep", "query": user_message[:50]},
                                fast=True
                            )
                            self.metacognition.confidence = min(0.7, self.metacognition.confidence + 0.15)
                    except Exception as e:
                        self._log(f"Error en busqueda profunda automatica: {e}", "error")

            if self.supports_tool_calling:
                action_result = self._react_with_tools(messages, iteration)
            else:
                action_result = self._react_with_json(messages, iteration)

            if action_result[0] == "respond":
                final_response = action_result[1]

                # SAFETY CHECK: Si la respuesta es JSON de tool call, ejecutarlo
                # en vez de mostrarlo como texto al usuario
                parsed_json = self._parse_json(final_response)
                if parsed_json:
                    accion = parsed_json.get("accion", "").strip()
                    if accion and accion in TOOL_FUNCTIONS:
                        self._log(f"JSON de tool detectado en respuesta: {accion}", "thinking")
                        action_result = ("tool_calls", [{"name": accion, "params": parsed_json.get("params", {})}])
                        # Procesar como tool call en vez de respuesta
                        for tc in action_result[1]:
                            self.metacognition.record_iteration(
                                iteration=iteration, action_type="tool_call", tool_name=tc["name"]
                            )
                        results = self._execute_tool_calls(action_result[1], messages)
                        for tc, res in zip(action_result[1], results):
                            had_error = "ERROR" in res
                            self.metacognition.record_iteration(
                                iteration=iteration, action_type="tool_result",
                                tool_name=tc["name"], result_summary=res[:200], had_error=had_error
                            )
                        self._feed_tool_results(action_result[1], results, messages)
                        continue  # Siguiente iteracion del bucle ReAct
                    elif not parsed_json.get("respuesta_final", "").strip():
                        # JSON sin respuesta_final ni accion valida - limpiar
                        clean = self._clean_json_leak(final_response)
                        if clean != final_response:
                            final_response = clean

                # Evaluar resultado para poblar _last_evaluation
                reflection = self.metacognition.evaluate_result(
                    user_message, final_response, iteration + 1
                )
                self._log(
                    f"Evaluacion: {reflection['assessment']} "
                    f"(confianza={reflection['confidence_final']})",
                    "evaluation"
                )

                # SEGUNDO: Ahora get_final_reflection_prompt() tiene datos reales
                reflection_prompt = self.metacognition.get_final_reflection_prompt()
                if reflection_prompt:
                    self._log("Reflexion metacognitiva inyectada en respuesta final", "evaluation")
                    # Re-generar con contexto de reflexion (solo si la respuesta puede mejorar)
                    if len(final_response) < 100 and self.metacognition.error_count > 0:
                        messages.append({"role": "assistant", "content": final_response})
                        messages.append({"role": "user", "content": reflection_prompt + "\n\nMejora tu respuesta anterior si es incompleta."})
                        improved = ollama.generate_chat(messages)
                        if improved and len(improved) > len(final_response):
                            final_response = improved
                            self._log("Respuesta mejorada via metacognicion", "success")

                for lesson in reflection.get("lessons", []):
                    learning.add_knowledge(lesson, source="metacognition")
                self._log("Respuesta final generada", "success")
                self._save_interaction(user_message, final_response)
                return final_response, self.thinking_log

            elif action_result[0] == "tool_calls":
                tool_calls = action_result[1]
                for tc in tool_calls:
                    self.metacognition.record_iteration(
                        iteration=iteration, action_type="tool_call", tool_name=tc["name"]
                    )
                results = self._execute_tool_calls(tool_calls, messages)
                for tc, res in zip(tool_calls, results):
                    had_error = "ERROR" in res
                    self.metacognition.record_iteration(
                        iteration=iteration, action_type="tool_result",
                        tool_name=tc["name"], result_summary=res[:200], had_error=had_error
                    )
                self._feed_tool_results(tool_calls, results, messages)

            elif action_result[0] == "error":
                self._log(f"Error: {action_result[1]}", "error")
                self.metacognition.record_iteration(
                    iteration=iteration, action_type="error", had_error=True
                )
                if iteration >= MAX_REACT_ITERATIONS - 1:
                    return "Tuve problemas para procesar tu solicitud. Puedes reformularla?", self.thinking_log

        self._log("Alcanzado limite de iteraciones", "warning")
        return "Alcance el limite de iteraciones. Puede que necesites ser mas especifico.", self.thinking_log

    # ----------------------------------------------------------
    # RUN CON STREAMING REAL (token a token)
    # ----------------------------------------------------------
    def run_stream(self, user_message):
        """
        Bucle ReAct con streaming REAL. Yields cada token al instante.
        Eventos: {"type": "text"|"thinking"|"tool_start"|"tool_result"|"meta"|"done", "data": ...}
        v15: Agrega evento "thinking" para que la UI muestre el proceso de pensamiento.
        """
        self.thinking_log = []
        self.metacognition.reset()
        self._tool_call_counts = {}
        self._total_tool_calls = 0
        self._log(f"Mensaje del usuario: {user_message}", "input")

        # *** NUEVO v19: Direct Intent Parser ***
        # Intentar ejecutar directamente si la intención es clara
        direct_result = self._try_direct_intent_stream(user_message)
        if direct_result is not None:
            yield from direct_result
            return

        # Emitir evento thinking: recibiendo pregunta
        yield {
            "type": "thinking",
            "data": {
                "phase": "receiving",
                "message": f"Recibiendo pregunta: {user_message[:80]}...",
                "iteration": 0,
                "confidence": 0.7,
            }
        }

        messages = self._build_messages(user_message)

        # *** NUEVO: Deteccion de tareas complejas - sugerir planificacion ***
        if self._is_complex_task(user_message):
            self._log("Tarea compleja detectada: sugiriendo planificacion_tarea", "info")
            # Inyectar hint en el system prompt para que el agente considere planificar
            plan_hint = (
                "\n\n[NOTA DEL SISTEMA]: Esta parece una tarea compleja. "
                "Considera usar la herramienta 'planificar_tarea' primero para descomponer "
                "el problema en subtareas antes de ejecutar. Esto mejorara la calidad del resultado."
            )
            for msg in messages:
                if msg["role"] == "system":
                    msg["content"] += plan_hint
                    break

        if self.supports_tool_calling is None:
            self.supports_tool_calling = self._detect_tool_calling_support()
            self._log(
                f"Tool calling nativo: {'SI' if self.supports_tool_calling else 'NO (usando JSON fallback)'}",
                "info"
            )

        # Emitir evento thinking: buscando en memoria
        yield {
            "type": "thinking",
            "data": {
                "phase": "memory_search",
                "message": "Buscando en memoria conocimiento relevante...",
                "iteration": 0,
                "confidence": self.metacognition.confidence,
            }
        }

        for iteration in range(MAX_REACT_ITERATIONS):
            self._log(f"--- Iteracion {iteration + 1}/{MAX_REACT_ITERATIONS} ---", "react")

            # Emitir evento thinking: nueva iteracion
            yield {
                "type": "thinking",
                "data": {
                    "phase": "iteration_start",
                    "message": f"Iteracion {iteration + 1}/{MAX_REACT_ITERATIONS}: Pensando como responder...",
                    "iteration": iteration + 1,
                    "confidence": self.metacognition.confidence,
                }
            }

            # *** FIX: Metacognicion ANTES de decidir la accion ***
            meta_prompt = self.metacognition.get_metacognitive_prompt(iteration)
            if meta_prompt:
                self._log("Alerta metacognitiva inyectada ANTES de accion", "evaluation")
                self._inject_metacognitive_prompt(messages, meta_prompt)
                yield {
                    "type": "meta",
                    "data": {
                        "confidence": self.metacognition.confidence,
                        "errors": self.metacognition.error_count,
                        "successes": self.metacognition.success_count,
                        "plan_changes": self.metacognition.plan_changes,
                    }
                }

            # *** NUEVO: AUTO-BUSQUEDA WEB en streaming cuando confianza baja ***
            if self.metacognition.confidence < 0.5 and iteration > 0:
                web_tools = ["buscar_web", "buscar_web_profundo", "leer_web"]
                already_searched = any(t in self.metacognition.tool_history for t in web_tools)
                
                if not already_searched:
                    self._log("Confianza baja (streaming): ejecutando busqueda web automatica", "cloud")
                    yield {"type": "tool_start", "data": {"name": "buscar_web", "params": {"consulta": user_message}}}
                    try:
                        search_result = TOOL_FUNCTIONS["buscar_web"](consulta=user_message)
                        if search_result and "No se encontraron" not in search_result:
                            self._log(f"Busqueda web automatica exitosa", "cloud")
                            yield {"type": "tool_result", "data": {"tool": {"name": "buscar_web"}, "result": search_result[:200]}}
                            messages.append({
                                "role": "user", 
                                "content": f"[RESULTADO DE BUSQUEDA WEB AUTOMATICA]:\n{search_result[:1500]}\n\nUsa esta informacion para responder."
                            })
                            self.memory.remember(
                                f"Busqueda web para '{user_message[:50]}': {search_result[:300]}",
                                metadata={"type": "web_search", "query": user_message[:50]},
                                fast=True
                            )
                            self.metacognition.record_iteration(
                                iteration=iteration, action_type="tool_call",
                                tool_name="buscar_web", result_summary=search_result[:100]
                            )
                            self.metacognition.confidence = min(0.7, self.metacognition.confidence + 0.2)
                        else:
                            self._log("Busqueda web automatica sin resultados", "warning")
                    except Exception as e:
                        self._log(f"Error en busqueda web automatica: {e}", "error")
                
                elif "buscar_web_profundo" not in self.metacognition.tool_history and self.metacognition.confidence < 0.4:
                    self._log("Confianza muy baja tras busqueda: ejecutando busqueda profunda", "cloud")
                    yield {"type": "tool_start", "data": {"name": "buscar_web_profundo", "params": {"consulta": user_message}}}
                    try:
                        deep_result = TOOL_FUNCTIONS["buscar_web_profundo"](consulta=user_message)
                        if deep_result and len(deep_result) > 200:
                            self._log(f"Busqueda profunda exitosa", "cloud")
                            yield {"type": "tool_result", "data": {"tool": {"name": "buscar_web_profundo"}, "result": deep_result[:200]}}
                            messages.append({
                                "role": "user",
                                "content": f"[RESULTADO DE BUSQUEDA PROFUNDA]:\n{deep_result[:2000]}\n\nResponde usando esta informacion."
                            })
                            self.memory.remember(
                                f"Busqueda profunda para '{user_message[:50]}': {deep_result[:400]}",
                                metadata={"type": "web_search_deep", "query": user_message[:50]},
                                fast=True
                            )
                            self.metacognition.confidence = min(0.7, self.metacognition.confidence + 0.15)
                    except Exception as e:
                        self._log(f"Error en busqueda profunda automatica: {e}", "error")

            # ---- NUCLEO: Streaming token-a-token ----
            full_text = ""
            tool_calls_found = []
            is_final_response = False

            if self.supports_tool_calling:
                # Stream del LLM y procesar en tiempo real
                for event in self._stream_llm_with_tools(messages):
                    if event["type"] == "token":
                        full_text += event["data"]
                        yield {"type": "text", "data": event["data"]}
                    elif event["type"] == "tool_calls":
                        tool_calls_found = event["data"]
                    elif event["type"] == "done":
                        is_final_response = event["data"]  # True si es respuesta final
            else:
                # JSON fallback (sin streaming real)
                result_type, result_data = self._react_with_json(messages, iteration)
                if result_type == "respond":
                    full_text = result_data
                    yield {"type": "text", "data": result_data}
                    is_final_response = True
                elif result_type == "tool_calls":
                    tool_calls_found = result_data
                elif result_type == "error":
                    self._log(f"Error: {result_data}", "error")
                    self.metacognition.record_iteration(
                        iteration=iteration, action_type="error", had_error=True
                    )
                    if iteration >= MAX_REACT_ITERATIONS - 1:
                        yield {
                            "type": "done",
                            "data": "Tuve problemas para procesar tu solicitud. Puedes reformularla?",
                            "thinking_log": self.thinking_log,
                            "meta_status": self.metacognition.get_status(),
                        }
                        return
                    continue

            # Procesar resultado de esta iteracion
            # SAFETY CHECK: Si full_text parece JSON de tool call, parsearlo y ejecutar
            # en vez de mostrarlo como texto al usuario
            if is_final_response and not tool_calls_found and full_text:
                parsed_json = self._parse_json(full_text)
                if parsed_json:
                    accion = parsed_json.get("accion", "").strip()
                    if accion and accion in TOOL_FUNCTIONS:
                        self._log(f"JSON de tool detectado en respuesta final: {accion}", "thinking")
                        tool_calls_found = [{"name": accion, "params": parsed_json.get("params", {})}]
                        is_final_response = False  # No es respuesta final, es tool call
                    elif not parsed_json.get("respuesta_final", "").strip():
                        # JSON sin respuesta_final ni accion valida - extraer contenido util
                        clean = self._clean_json_leak(full_text)
                        if clean != full_text:
                            full_text = clean

            if is_final_response and not tool_calls_found:
                # Emitir evento thinking: generando respuesta final
                yield {
                    "type": "thinking",
                    "data": {
                        "phase": "final_response",
                        "message": "Tengo suficiente informacion. Generando respuesta final...",
                        "iteration": iteration + 1,
                        "confidence": self.metacognition.confidence,
                    }
                }
                # PRIMERO: Evaluar resultado para poblar _last_evaluation
                reflection = self.metacognition.evaluate_result(
                    user_message, full_text, iteration + 1
                )
                self._log(
                    f"Evaluacion: {reflection['assessment']} (confianza={reflection['confidence_final']})",
                    "evaluation"
                )

                # SEGUNDO: Ahora get_final_reflection_prompt() tiene datos reales
                reflection_prompt = self.metacognition.get_final_reflection_prompt()
                if reflection_prompt and len(full_text) < 100 and self.metacognition.error_count > 0:
                    self._log("Reflexion metacognitiva: reintentando respuesta mejorada", "evaluation")
                    try:
                        messages.append({"role": "assistant", "content": full_text})
                        messages.append({"role": "user", "content": reflection_prompt + "\n\nDa una respuesta mas completa."})
                        improved = ollama.generate_chat(messages)
                        if improved and len(improved) > len(full_text):
                            full_text = improved
                            yield {"type": "text", "data": "\n\n[Respuesta mejorada] " + improved}
                    except Exception:
                        pass

                # Respuesta final - terminar
                for lesson in reflection.get("lessons", []):
                    learning.add_knowledge(lesson, source="metacognition")

                self._log("Respuesta final generada (streaming)", "success")
                self._save_interaction(user_message, full_text)
                yield {
                    "type": "done",
                    "data": full_text,
                    "thinking_log": self.thinking_log,
                    "meta_status": self.metacognition.get_status(),
                }
                return

            elif tool_calls_found:
                # Ejecutar tool calls
                for tc in tool_calls_found:
                    self.metacognition.record_iteration(
                        iteration=iteration, action_type="tool_call", tool_name=tc["name"]
                    )
                    # Emitir evento thinking: decidi usar una herramienta
                    yield {
                        "type": "thinking",
                        "data": {
                            "phase": "tool_decision",
                            "message": f"Decidi usar la herramienta: {tc['name']} — buscando informacion o ejecutando accion...",
                            "iteration": iteration + 1,
                            "confidence": self.metacognition.confidence,
                            "tool": tc["name"],
                        }
                    }
                    yield {"type": "tool_start", "data": tc}

                results = self._execute_tool_calls(tool_calls_found, messages)

                for tc, res in zip(tool_calls_found, results):
                    had_error = "ERROR" in res
                    self.metacognition.record_iteration(
                        iteration=iteration, action_type="tool_result",
                        tool_name=tc["name"], result_summary=res[:200], had_error=had_error
                    )
                    # Emitir evento thinking: observando resultado
                    status = "exitoso" if not had_error else "con error"
                    yield {
                        "type": "thinking",
                        "data": {
                            "phase": "observation",
                            "message": f"Observacion: {tc['name']} termino {status}. Analizando si tengo suficiente informacion...",
                            "iteration": iteration + 1,
                            "confidence": self.metacognition.confidence,
                            "tool": tc["name"],
                            "success": not had_error,
                        }
                    }
                    yield {"type": "tool_result", "data": {"tool": tc, "result": res}}

                self._feed_tool_results(tool_calls_found, results, messages)

            elif not full_text:
                # Ni respuesta ni tool calls - error
                self._log("Respuesta vacia del modelo", "error")
                self.metacognition.record_iteration(
                    iteration=iteration, action_type="error", had_error=True
                )
                if iteration >= MAX_REACT_ITERATIONS - 1:
                    yield {
                        "type": "done",
                        "data": "Tuve problemas para procesar tu solicitud. Puedes reformularla?",
                        "thinking_log": self.thinking_log,
                        "meta_status": self.metacognition.get_status(),
                    }
                    return

        # Limite de iteraciones
        yield {
            "type": "done",
            "data": "Alcance el limite de iteraciones. Puede que necesites ser mas especifico.",
            "thinking_log": self.thinking_log,
            "meta_status": self.metacognition.get_status(),
        }

    # ----------------------------------------------------------
    # DETECCION DE TAREAS COMPLEJAS
    # ----------------------------------------------------------
    def _is_complex_task(self, message: str) -> bool:
        """Detecta si un mensaje parece una tarea compleja que se beneficia de planificacion."""
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in self._COMPLEX_TASK_KEYWORDS)

    # ----------------------------------------------------------
    # RUN PLANNED (ejecucion con planificacion y orquestacion)
    # ----------------------------------------------------------
    def run_planned(self, message: str) -> str:
        """Ejecuta una tarea compleja usando planificacion y orquestacion."""
        from tools.task_planner import get_planner

        planner = get_planner()
        plan = planner.smart_decompose(message)

        # Validar plan
        validation = planner.validate_plan(plan)
        if not validation["valid"]:
            # Fallback a ejecucion normal
            self._log("Plan invalido, fallback a ejecucion normal", "warning")
            return self.run(message)

        # Ejecutar plan
        results = []
        while True:
            # Obtener todas las tareas listas (pendientes con dependencias resueltas)
            ready_tasks = plan.get_ready_tasks()
            if not ready_tasks:
                break

            # --- EJECUCION PARALELA: si hay 2+ tareas listas y el Orchestrator esta disponible ---
            if len(ready_tasks) >= 2 and ORCHESTRATOR_AVAILABLE and self.orchestrator:
                # Limitar a maximo 3 tareas en paralelo
                parallel_tasks = ready_tasks[:3]
                parallel_titles = [t.title for t in parallel_tasks]
                self._log(
                    f"Ejecutando {len(parallel_tasks)} tareas en paralelo: {parallel_titles}",
                    "info"
                )

                # Marcar todas como in_progress
                for t in parallel_tasks:
                    plan.mark_in_progress(t.id)

                # Delegar al Orchestrator
                parallel_result = self._execute_parallel_tasks(parallel_tasks, plan, results)

                if parallel_result:
                    # Procesar resultados paralelos
                    for task in parallel_tasks:
                        task_result = parallel_result.get(task.id, "")
                        if task_result and not task_result.startswith("ERROR:"):
                            plan.mark_completed(task.id, task_result)
                            results.append({"task": task.title, "result": task_result[:500]})
                        else:
                            error_msg = task_result if task_result else "Resultado vacio"
                            plan.mark_failed(task.id, error_msg)
                    planner._save_plan(plan)
                else:
                    # Fallback: ejecutar la primera tarea secuencialmente
                    self._log("Fallback a ejecucion secuencial tras fallo del Orchestrator", "warning")
                    next_task = parallel_tasks[0]

                    task_prompt = (
                        f"Ejecuta esta subtarea: {next_task.title}\n"
                        f"Descripcion: {next_task.description}\n"
                        f"Contexto previo: {json.dumps(results[-3:], ensure_ascii=False) if results else 'Ninguno'}"
                    )

                    if SKILLS_ENRICHMENT_AVAILABLE:
                        try:
                            skills_context = enrich_prompt_with_skills(next_task.description, "")
                            if skills_context:
                                task_prompt += f"\n\n--- CONTEXTO DE SKILLS PARA SUBTAREA ---\n{skills_context}"
                        except Exception:
                            pass

                    try:
                        result = self.run(task_prompt)
                        if isinstance(result, tuple):
                            result = result[0]
                        plan.mark_completed(next_task.id, result)
                        results.append({"task": next_task.title, "result": result[:500]})
                        planner._save_plan(plan)
                    except Exception as e:
                        plan.mark_failed(next_task.id, str(e))
                        planner._save_plan(plan)

            # --- EJECUCION SECUENCIAL: si solo hay 1 tarea lista o no hay Orchestrator ---
            else:
                next_task = ready_tasks[0]
                plan.mark_in_progress(next_task.id)

                # Ejecutar la subtarea
                task_prompt = (
                    f"Ejecuta esta subtarea: {next_task.title}\n"
                    f"Descripcion: {next_task.description}\n"
                    f"Contexto previo: {json.dumps(results[-3:], ensure_ascii=False) if results else 'Ninguno'}"
                )

                # Enriquecer prompt de subtarea con contexto de skills relevantes
                if SKILLS_ENRICHMENT_AVAILABLE:
                    try:
                        skills_context = enrich_prompt_with_skills(next_task.description, "")
                        if skills_context:
                            task_prompt += f"\n\n--- CONTEXTO DE SKILLS PARA SUBTAREA ---\n{skills_context}"
                    except Exception:
                        pass  # No dejar que el enriquecimiento rompa la ejecucion planificada

                try:
                    result = self.run(task_prompt)
                    # self.run devuelve (respuesta, thinking_log)
                    if isinstance(result, tuple):
                        result = result[0]
                    plan.mark_completed(next_task.id, result)
                    results.append({"task": next_task.title, "result": result[:500]})
                    planner._save_plan(plan)
                except Exception as e:
                    plan.mark_failed(next_task.id, str(e))
                    planner._save_plan(plan)
                    # Intentar continuar con la siguiente subtarea

        # Retornar resumen
        progress = plan.get_progress()
        summary = f"Plan completado: {progress['completed']}/{progress['total']} tareas\n\n"
        for r in results:
            summary += f"- {r['task']}: {r['result'][:200]}\n"
        return summary

    # ----------------------------------------------------------
    # EJECUCION PARALELA DE TAREAS (via Orchestrator)
    # ----------------------------------------------------------
    def _execute_parallel_tasks(self, tasks, plan, results):
        """
        Ejecuta multiples tareas independientes en paralelo usando el Orchestrator.

        Args:
            tasks: Lista de objetos Task con status=pending y dependencias resueltas
            plan: ExecutionPlan al que pertenecen las tareas
            results: Lista acumulada de resultados previos

        Returns:
            Dict {task_id: result} con los resultados de cada tarea,
            o None si fallo y se debe hacer fallback a secuencial.
        """
        if not self.orchestrator or not ORCHESTRATOR_AVAILABLE:
            self._log("Orchestrator no disponible para ejecucion paralela", "warning")
            return None

        # Crear descripciones de sub-tareas para el orchestrator
        subtask_descriptions = []
        for task in tasks:
            subtask_descriptions.append({
                "id": task.id,
                "description": f"{task.title}: {task.description}",
                "context": json.dumps(results[-3:], ensure_ascii=False) if results else "",
            })

        self._log(
            f"Delegando {len(tasks)} tareas al Orchestrator en paralelo: "
            f"{[t.title for t in tasks]}",
            "info"
        )

        # Usar orchestrator para ejecutar en paralelo
        try:
            orch_result = self.orchestrator.execute_parallel(
                descriptions=subtask_descriptions,
                agent_run_fn=self.run,  # Pasar el metodo run del propio agente
            )
            if orch_result:
                self._log(
                    f"Orchestrator completo {len(orch_result)}/{len(tasks)} tareas en paralelo",
                    "info"
                )
            return orch_result
        except Exception as e:
            self._log(f"Orchestrator parallel fallo: {e}, fallback a secuencial", "warning")
            return None

    # ----------------------------------------------------------
    # RUN PLANNED STREAM (ejecucion planificada con streaming)
    # ----------------------------------------------------------
    def run_planned_stream(self, message: str):
        """Ejecuta una tarea compleja con planificacion, emitiendo eventos de streaming."""
        try:
            from tools.task_planner import get_planner
        except Exception as e:
            # Si task_planner no esta disponible, fallback a run_stream
            self._log(f"task_planner no disponible: {e}, fallback a run_stream", "warning")
            yield from self.run_stream(message)
            return

        planner = get_planner()

        # Emitir evento de inicio de planificacion
        yield {
            "type": "plan_update",
            "data": {
                "phase": "decomposing",
                "message": "Analizando tarea compleja y creando plan...",
                "task": message[:100],
            }
        }

        try:
            plan = planner.smart_decompose(message)
        except Exception as e:
            self._log(f"Error al descomponer tarea: {e}", "error")
            yield from self.run_stream(message)
            return

        # Validar plan
        validation = planner.validate_plan(plan)
        if not validation["valid"]:
            self._log("Plan invalido, fallback a ejecucion normal (streaming)", "warning")
            yield {
                "type": "plan_update",
                "data": {
                    "phase": "invalid",
                    "message": "No se pudo crear un plan valido. Ejecutando normalmente...",
                }
            }
            yield from self.run_stream(message)
            return

        # Emitir plan creado
        progress = plan.get_progress()
        yield {
            "type": "plan_update",
            "data": {
                "phase": "plan_created",
                "message": f"Plan creado: {progress['total']} subtareas",
                "total_tasks": progress['total'],
                "tasks": [
                    {"id": t.id, "title": t.title, "status": t.status.value if hasattr(t.status, 'value') else str(t.status)}
                    for t in plan.tasks
                ],
            }
        }

        # Ejecutar plan
        results = []
        while True:
            # Obtener todas las tareas listas (pendientes con dependencias resueltas)
            ready_tasks = plan.get_ready_tasks()
            if not ready_tasks:
                break

            # --- EJECUCION PARALELA: si hay 2+ tareas listas y el Orchestrator esta disponible ---
            if len(ready_tasks) >= 2 and ORCHESTRATOR_AVAILABLE and self.orchestrator:
                # Limitar a maximo 3 tareas en paralelo para no sobrecargar
                parallel_tasks = ready_tasks[:3]
                parallel_titles = [t.title for t in parallel_tasks]
                self._log(
                    f"Ejecutando {len(parallel_tasks)} tareas en paralelo: {parallel_titles}",
                    "info"
                )

                # Marcar todas como in_progress ANTES de delegar
                for t in parallel_tasks:
                    plan.mark_in_progress(t.id)

                # Emitir evento de ejecucion paralela
                yield {
                    "type": "plan_update",
                    "data": {
                        "phase": "parallel",
                        "message": f"Ejecutando en paralelo: {', '.join(parallel_titles)}",
                        "tasks": parallel_titles,
                        "task_ids": [t.id for t in parallel_tasks],
                        "progress": f"{len(results) + 1}-{len(results) + len(parallel_tasks)}/{progress['total']}",
                    }
                }

                # Delegar al Orchestrator
                parallel_result = self._execute_parallel_tasks(parallel_tasks, plan, results)

                if parallel_result:
                    # Procesar resultados paralelos
                    for task in parallel_tasks:
                        task_result = parallel_result.get(task.id, "")
                        if task_result and not task_result.startswith("ERROR:"):
                            plan.mark_completed(task.id, task_result)
                            results.append({"task": task.title, "result": task_result[:500]})
                            yield {
                                "type": "text",
                                "data": f"✅ {task.title}: {task_result[:200]}\n\n"
                            }
                        else:
                            error_msg = task_result if task_result else "Resultado vacio"
                            plan.mark_failed(task.id, error_msg)
                            yield {
                                "type": "plan_update",
                                "data": {
                                    "phase": "task_failed",
                                    "message": f"Subtarea paralela fallo: {task.title} - {error_msg[:100]}",
                                    "task_id": task.id,
                                }
                            }
                    planner._save_plan(plan)
                else:
                    # Fallback: ejecutar las tareas secuencialmente (la primera de las paralelas)
                    self._log("Fallback a ejecucion secuencial tras fallo del Orchestrator", "warning")
                    next_task = parallel_tasks[0]
                    # Resetear las que no vamos a ejecutar ahora a pending
                    for t in parallel_tasks[1:]:
                        t.status = plan.tasks[t.id].status  # quedan in_progress, se retomaran

                    # Ejecutar la primera tarea secuencialmente
                    task_prompt = (
                        f"Ejecuta esta subtarea: {next_task.title}\n"
                        f"Descripcion: {next_task.description}\n"
                        f"Contexto previo: {json.dumps(results[-3:], ensure_ascii=False) if results else 'Ninguno'}"
                    )

                    if SKILLS_ENRICHMENT_AVAILABLE:
                        try:
                            skills_context = enrich_prompt_with_skills(next_task.description, "")
                            if skills_context:
                                task_prompt += f"\n\n--- CONTEXTO DE SKILLS PARA SUBTAREA ---\n{skills_context}"
                        except Exception:
                            pass

                    yield {
                        "type": "plan_update",
                        "data": {
                            "phase": "task_started",
                            "message": f"Ejecutando (secuencial fallback): {next_task.title}",
                            "task_id": next_task.id,
                            "task_title": next_task.title,
                            "progress": f"{len(results) + 1}/{progress['total']}",
                        }
                    }

                    try:
                        result = self.run(task_prompt)
                        if isinstance(result, tuple):
                            result = result[0]
                        plan.mark_completed(next_task.id, result)
                        results.append({"task": next_task.title, "result": result[:500]})
                        planner._save_plan(plan)
                        yield {
                            "type": "text",
                            "data": f"✅ {next_task.title}: {result[:200]}\n\n"
                        }
                    except Exception as e:
                        plan.mark_failed(next_task.id, str(e))
                        planner._save_plan(plan)
                        yield {
                            "type": "plan_update",
                            "data": {
                                "phase": "task_failed",
                                "message": f"Subtarea fallo: {next_task.title} - {str(e)[:100]}",
                                "task_id": next_task.id,
                            }
                        }

            # --- EJECUCION SECUENCIAL: si solo hay 1 tarea lista o no hay Orchestrator ---
            else:
                next_task = ready_tasks[0]
                plan.mark_in_progress(next_task.id)

                # Emitir evento de subtarea iniciada
                yield {
                    "type": "plan_update",
                    "data": {
                        "phase": "task_started",
                        "message": f"Ejecutando: {next_task.title}",
                        "task_id": next_task.id,
                        "task_title": next_task.title,
                        "progress": f"{len(results) + 1}/{progress['total']}",
                    }
                }

                # Ejecutar la subtarea
                task_prompt = (
                    f"Ejecuta esta subtarea: {next_task.title}\n"
                    f"Descripcion: {next_task.description}\n"
                    f"Contexto previo: {json.dumps(results[-3:], ensure_ascii=False) if results else 'Ninguno'}"
                )

                # Enriquecer prompt de subtarea (streaming) con contexto de skills relevantes
                if SKILLS_ENRICHMENT_AVAILABLE:
                    try:
                        skills_context = enrich_prompt_with_skills(next_task.description, "")
                        if skills_context:
                            task_prompt += f"\n\n--- CONTEXTO DE SKILLS PARA SUBTAREA ---\n{skills_context}"
                    except Exception:
                        pass  # No dejar que el enriquecimiento rompa la ejecucion planificada

                try:
                    result = self.run(task_prompt)
                    # self.run devuelve (respuesta, thinking_log)
                    if isinstance(result, tuple):
                        result = result[0]
                    plan.mark_completed(next_task.id, result)
                    results.append({"task": next_task.title, "result": result[:500]})
                    planner._save_plan(plan)

                    # Emitir resultado de subtarea
                    yield {
                        "type": "text",
                        "data": f"✅ {next_task.title}: {result[:200]}\n\n"
                    }

                except Exception as e:
                    plan.mark_failed(next_task.id, str(e))
                    planner._save_plan(plan)

                    yield {
                        "type": "plan_update",
                        "data": {
                            "phase": "task_failed",
                            "message": f"Subtarea fallo: {next_task.title} - {str(e)[:100]}",
                            "task_id": next_task.id,
                        }
                    }
                    # Intentar continuar con la siguiente subtarea

        # Emitir resumen final
        progress = plan.get_progress()
        summary = f"Plan completado: {progress['completed']}/{progress['total']} tareas\n\n"
        for r in results:
            summary += f"- {r['task']}: {r['result'][:200]}\n"

        yield {
            "type": "plan_update",
            "data": {
                "phase": "completed",
                "message": summary[:500],
                "completed": progress['completed'],
                "total": progress['total'],
            }
        }

        yield {
            "type": "done",
            "data": summary,
            "thinking_log": self.thinking_log,
            "meta_status": self.metacognition.get_status() if hasattr(self, 'metacognition') else {},
        }

    # ----------------------------------------------------------
    # STREAMING LLM CON TOOL CALLING (token a token)
    # ----------------------------------------------------------
    def _stream_llm_with_tools(self, messages):
        """
        Genera respuesta del LLM con streaming REAL.
        Yields: {"type": "token"|"tool_calls"|"done", "data": ...}
        """
        import time as _time
        _llm_start = _time.monotonic()
        full_content = ""
        full_tool_calls = []

        try:
            # Intentar streaming HTTP directo (mas rapido, sin overhead de lib)
            for chunk in ollama.generate_stream(messages, tools=TOOL_SCHEMAS):
                if isinstance(chunk, str):
                    # Token de texto - emitir inmediatamente
                    # PERO: si parece JSON de tool call, no emitirlo al usuario
                    full_content += chunk
                    # Detectar si el contenido es JSON de herramienta
                    if self._looks_like_tool_json(full_content):
                        continue  # Acumular sin emitir
                    # Si antes se acumulaba JSON pero ya no, limpiar
                    yield {"type": "token", "data": chunk}
                elif isinstance(chunk, dict):
                    # Resultado final con tool_calls
                    msg = chunk.get("message", chunk)
                    tool_calls = msg.get("tool_calls", [])
                    content = msg.get("content", "")

                    if content and not full_content:
                        # Contenido que no se streameo (fallback)
                        full_content = content
                        yield {"type": "token", "data": content}

                    if tool_calls:
                        # Parsear tool calls
                        parsed_calls = []
                        for tc in tool_calls:
                            tool_name = tc.get("function", {}).get("name", "")
                            tool_params = tc.get("function", {}).get("arguments", {})
                            self._log(f"Tool call: {tool_name}({tool_params})", "thinking")
                            parsed_calls.append({"name": tool_name, "params": tool_params})
                        yield {"type": "tool_calls", "data": parsed_calls}
                        yield {"type": "done", "data": False}
                        return

            # Si llegamos aqui sin tool_calls, verificar si el contenido es JSON de herramientas
            if full_content:
                # Si el contenido acumulado era JSON de tool calls (no se emitio),
                # parsearlo y ejecutar como tool calls
                if self._looks_like_tool_json(full_content):
                    parsed = self._parse_json(full_content)
                    if parsed:
                        # Verificar si son multiples tool calls
                        if parsed.get("_multi_tool_calls") and parsed.get("tool_calls"):
                            yield {"type": "tool_calls", "data": parsed["tool_calls"]}
                            yield {"type": "done", "data": False}
                            return
                        accion = parsed.get("accion", "").strip()
                        if accion and accion in TOOL_FUNCTIONS:
                            yield {"type": "tool_calls", "data": [{"name": accion, "params": parsed.get("params", {})}]}
                            yield {"type": "done", "data": False}
                            return
                    # Si no se pudo parsear como tool call, emitir el texto limpio
                    clean = self._clean_json_leak(full_content)
                    if clean != full_content:
                        # El texto era JSON, emitir version limpia
                        yield {"type": "token", "data": clean}
                _llm_elapsed = (_time.monotonic() - _llm_start) * 1000.0
                get_metrics().record_llm_call(_llm_elapsed)
                yield {"type": "done", "data": True}
                return

        except Exception as e:
            self._log(f"Error en streaming: {e}", "error")
            get_metrics().record_error("llm_stream")

        # Fallback: modo no-streaming
        try:
            response = ollama.generate(messages, tools=TOOL_SCHEMAS)
            # generate() already records llm_call via @timed, so no duplicate
            if isinstance(response, str):
                yield {"type": "token", "data": response}
                yield {"type": "done", "data": True}
                return

            message = response.get("message", response)
            tool_calls = message.get("tool_calls", [])
            content = message.get("content", "")

            if tool_calls:
                parsed_calls = []
                for tc in tool_calls:
                    tool_name = tc.get("function", {}).get("name", "")
                    tool_params = tc.get("function", {}).get("arguments", {})
                    self._log(f"Tool call: {tool_name}({tool_params})", "thinking")
                    parsed_calls.append({"name": tool_name, "params": tool_params})
                yield {"type": "tool_calls", "data": parsed_calls}
                yield {"type": "done", "data": False}
                return

            if content:
                yield {"type": "token", "data": content}
                yield {"type": "done", "data": True}
                return

        except Exception as e:
            self._log(f"Error en fallback: {e}", "error")

        yield {"type": "done", "data": False}

    # ----------------------------------------------------------
    # REACT CON TOOL CALLING (sin streaming)
    # ----------------------------------------------------------
    def _react_with_tools(self, messages, iteration):
        """ReAct usando function calling nativo. Soporta multiple tool calls."""
        # generate() already records llm_call via @timed decorator
        try:
            response = ollama.generate(messages, tools=TOOL_SCHEMAS)

            if isinstance(response, str):
                return ("respond", response)

            message = response.get("message", response)
            tool_calls = message.get("tool_calls", [])

            if tool_calls:
                parsed_calls = []
                for tc in tool_calls:
                    tool_name = tc.get("function", {}).get("name", "")
                    tool_params = tc.get("function", {}).get("arguments", {})
                    self._log(f"Tool call: {tool_name}({tool_params})", "thinking")
                    parsed_calls.append({"name": tool_name, "params": tool_params})
                return ("tool_calls", parsed_calls)

            content = message.get("content", "")
            if content:
                # SAFETY CHECK: Si el modelo genero JSON de tool call en vez de
                # usar function calling nativo, parsearlo y ejecutarlo
                parsed = self._parse_json(content)
                if parsed:
                    accion = parsed.get("accion", "").strip()
                    if accion and accion in TOOL_FUNCTIONS:
                        self._log(f"Tool call via JSON (modelo no uso function calling nativo): {accion}", "thinking")
                        params = parsed.get("params", {})
                        return ("tool_calls", [{"name": accion, "params": params}])
                    # Si tiene respuesta_final, usarla
                    respuesta_final = parsed.get("respuesta_final", "").strip()
                    if respuesta_final:
                        return ("respond", respuesta_final)
                return ("respond", content)

            return ("error", "Respuesta vacia del modelo")

        except Exception as e:
            self._log(f"Error en tool calling: {e}", "error")
            self.supports_tool_calling = False
            return ("error", str(e))

    # ----------------------------------------------------------
    # REACT CON JSON FALLBACK
    # ----------------------------------------------------------
    def _react_with_json(self, messages, iteration):
        """ReAct usando JSON parsing (fallback)."""
        # generate_chat() already records llm_call via @timed decorator
        if not any("HERRAMIENTAS DISPONIBLES" in str(m.get("content", "")) for m in messages):
            system_msg_idx = next((i for i, m in enumerate(messages) if m["role"] == "system"), -1)
            if system_msg_idx >= 0:
                # Usar prompt de tools compacto o completo según el modelo
                tools_prompt = JSON_TOOLS_PROMPT_COMPACT if self._should_use_compact_prompt() else JSON_TOOLS_PROMPT
                messages[system_msg_idx]["content"] += tools_prompt

        try:
            response = ollama.generate_chat(messages)
            if not response:
                return ("error", "El LLM no respondio")

            parsed = self._parse_json(response)
            if not parsed:
                # No es JSON - probablemente respuesta directa del modelo
                # Limpiar posibles restos de formato JSON
                clean = self._clean_json_leak(response)
                return ("respond", clean)

            # 1. Si hay _multi_tool_calls, ejecutar todas las herramientas
            if parsed.get("_multi_tool_calls") and parsed.get("tool_calls"):
                return ("tool_calls", parsed["tool_calls"])

            # 2. Si hay respuesta_final con contenido, usarla
            respuesta_final = parsed.get("respuesta_final", "").strip()
            if respuesta_final:
                return ("respond", respuesta_final)

            accion = parsed.get("accion", "").strip()
            params = parsed.get("params", {})
            pensamiento = parsed.get("pensamiento", "").strip()

            if pensamiento:
                self._log(f"Pensamiento: {pensamiento}", "thinking")

            # 3. Si hay accion valida, ejecutar herramienta
            if accion and accion in TOOL_FUNCTIONS:
                # Si tambien hay pensamiento, inyectarlo como contexto
                if pensamiento:
                    messages.append({
                        "role": "assistant",
                        "content": f"[Pensamiento: {pensamiento}] Ejecutando {accion}..."
                    })
                return ("tool_calls", [{"name": accion, "params": params}])

            # 3. Si hay pensamiento pero no accion ni respuesta_final,
            #    el modelo esta respondiendo en campo equivocado - usar pensamiento
            if pensamiento and not accion:
                self._log("Modelo respondio en 'pensamiento' en vez de 'respuesta_final'", "info")
                return ("respond", pensamiento)

            # 4. Fallback: devolver texto limpio (no JSON crudo)
            clean = self._clean_json_leak(response)
            return ("respond", clean)

        except Exception as e:
            return ("error", str(e))

    def _clean_json_leak(self, text):
        """Limpia texto que tiene restos de formato JSON para mostrar al usuario.
        v3: Mas agresivo - tambien limpia JSON parcial al inicio/final del texto.
        """
        # Si el texto es JSON completo, extraer solo el contenido util
        parsed = self._parse_json(text)
        if parsed:
            # Prioridad: respuesta_final > pensamiento > texto original
            if parsed.get("respuesta_final", "").strip():
                return parsed["respuesta_final"].strip()
            if parsed.get("pensamiento", "").strip():
                return parsed["pensamiento"].strip()
        # Si no es JSON completo, intentar limpiar restos
        # Caso: texto que empieza con JSON parcial
        import re as _re
        # Remover JSON parcial al inicio: {"pensamiento": "..." ... restos
        cleaned = _re.sub(r'^\s*\{[^}]*$', '', text).strip()
        # Remover JSON parcial al final
        cleaned = _re.sub(r'\{[^}]*$\s*$', '', cleaned).strip()
        # Si despues de limpiar quedo vacio, devolver texto original
        return cleaned if cleaned else text

    # ----------------------------------------------------------
    # EJECUCION DE TOOLS (paralelo + retry)
    # ----------------------------------------------------------
    def _execute_tool_calls(self, tool_calls, messages):
        """Ejecuta multiples tool calls con rate limiting y paralelismo."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Rate limiting: filtrar herramientas que se llamaron demasiadas veces
        filtered_calls = []
        for tc in tool_calls:
            tool_name = tc["name"]
            self._tool_call_counts[tool_name] = self._tool_call_counts.get(tool_name, 0) + 1
            self._total_tool_calls += 1

            if self._total_tool_calls > self.MAX_TOTAL_TOOL_CALLS:
                self._log(f"Rate limit: max total tool calls alcanzado ({self.MAX_TOTAL_TOOL_CALLS})", "warning")
                break

            if self._tool_call_counts[tool_name] > self.MAX_SAME_TOOL_CALLS:
                self._log(f"Rate limit: {tool_name} llamada {self._tool_call_counts[tool_name]} veces (max {self.MAX_SAME_TOOL_CALLS})", "warning")
                continue

            filtered_calls.append(tc)

        tool_calls = filtered_calls

        # Validar parametros de todos los tool calls primero
        for tc in tool_calls:
            tc["params"] = self._validate_tool_params(tc["name"], tc["params"])

        # Si hay solo 1 tool, ejecutar directamente (sin overhead de threads)
        if len(tool_calls) == 1:
            return [self._execute_single_tool(tool_calls[0], messages)]

        # Si hay multiples tools, ejecutar en paralelo
        # PERO no paralelizar si alguno es "ejecutar_comando" (puede tener side effects)
        has_sequential = any(tc["name"] == "ejecutar_comando" for tc in tool_calls)
        
        if has_sequential:
            # Ejecutar secuencialmente para evitar race conditions
            results = []
            for tc in tool_calls:
                results.append(self._execute_single_tool(tc, messages))
            return results

        # Ejecucion paralela para tools de solo lectura
        results = [None] * len(tool_calls)
        with ThreadPoolExecutor(max_workers=min(len(tool_calls), 3)) as executor:
            futures = {}
            for i, tc in enumerate(tool_calls):
                future = executor.submit(self._execute_single_tool, tc, messages)
                futures[future] = i
            
            for future in as_completed(futures):
                idx = futures[future]
                try:
                    results[idx] = future.result(timeout=30)
                except Exception as e:
                    results[idx] = f"ERROR: {e}"

        return results

    def _execute_single_tool(self, tc, messages, max_retries=1):
        """Ejecuta un solo tool call con retry automatico."""
        import time as _time
        tool_name = tc["name"]
        tool_params = tc["params"]

        self._log(f"Ejecutando: {tool_name}({tool_params})", "execution")

        _tool_start = _time.monotonic()
        tool_result = self._execute_tool(tool_name, tool_params)

        # Retry si fallo y el tool es reintentable
        if "ERROR" in tool_result and max_retries > 0:
            retryable_errors = ["TIMEOUT", "ConnectionError", "empty", "vacia"]
            if any(err in tool_result for err in retryable_errors):
                self._log(f"Reintentando {tool_name} (error transitorio)...", "execution")
                tool_result = self._execute_tool(tool_name, tool_params)

        _tool_elapsed_ms = (_time.monotonic() - _tool_start) * 1000.0
        get_metrics().record_tool_call(tool_name, _tool_elapsed_ms)

        if "ERROR" in tool_result:
            get_metrics().record_error("tool:" + tool_name)

        self._log(f"Resultado: {tool_result[:150]}...", "observation")

        # Alimentar memoria de trabajo
        self.memory.add_step(f"{tool_name}({tool_params})", tool_result[:200])
        if "ERROR" in tool_result:
            self.memory.set_error(f"{tool_name}: {tool_result[:100]}")
        if "PELIGROSO" in tool_result:
            self._log(f"Comando peligroso bloqueado: {tool_name}", "warning")
        if len(tool_result) > 50 and "ERROR" not in tool_result:
            self.memory.remember(
                f"Resultado de {tool_name}: {tool_result[:300]}",
                metadata={"type": "tool_result", "tool": tool_name}
            )

        return tool_result

    def _validate_tool_params(self, tool_name, params):
        """Valida y limpia parametros de un tool call antes de ejecutar."""
        if not isinstance(params, dict):
            params = {}
        
        # Asegurar que params tenga las claves correctas
        clean_params = {}
        for key, value in params.items():
            if isinstance(key, str) and len(key) < 50:
                # Limpiar valores string de posibles inyecciones
                if isinstance(value, str):
                    # No sanitizar contenido de archivos (puede tener codigo legitimo)
                    if tool_name in ("escribir_archivo", "generar_codigo"):
                        clean_params[key] = value
                    else:
                        from utils.security import sanitize_input
                        clean_params[key] = sanitize_input(value)
                else:
                    clean_params[key] = value
        
        return clean_params

    def _feed_tool_results(self, tool_calls, results, messages):
        """Alimenta resultados de tools de vuelta al agente."""
        if self.supports_tool_calling:
            assistant_msg = {"role": "assistant", "content": "", "tool_calls": []}
            for tc in tool_calls:
                assistant_msg["tool_calls"].append({
                    "function": {"name": tc["name"], "arguments": tc["params"]}
                })
            messages.append(assistant_msg)
            for tc, result in zip(tool_calls, results):
                messages.append({"role": "tool", "content": result})
        else:
            for tc, result in zip(tool_calls, results):
                messages.append({
                    "role": "assistant",
                    "content": json.dumps({
                        "pensamiento": f"Ejecute {tc['name']}",
                        "accion": tc["name"],
                        "params": tc["params"]
                    })
                })
                messages.append({
                    "role": "user",
                    "content": f"Resultado de {tc['name']}: {result}\n\nQue hago ahora? Responde con JSON."
                })

    def _execute_tool(self, tool_name, params):
        """Ejecuta una herramienta por nombre."""
        if tool_name in TOOL_FUNCTIONS:
            try:
                params = self._resolve_params(params)
                return TOOL_FUNCTIONS[tool_name](**params)
            except Exception as e:
                return f"ERROR ejecutando {tool_name}: {e}"
        return f"Herramienta no encontrada: {tool_name}"

    # ----------------------------------------------------------
    # METACOGNICION: INYECCION DE PROMPT
    # ----------------------------------------------------------
    def _inject_metacognitive_prompt(self, messages, meta_prompt):
        """Inyecta el prompt metacognitivo en la conversacion."""
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                messages.insert(i + 1, {"role": "user", "content": meta_prompt})
                return
        messages.append({"role": "user", "content": meta_prompt})

    # ----------------------------------------------------------
    # CONSTRUCCION DE MENSAJES (OPTIMIZADA)
    # ----------------------------------------------------------
    def _build_messages(self, new_message):
        """Construye la lista de mensajes con contexto enriquecido (optimizado)."""
        # Cache de modelos para evitar llamada API en cada mensaje
        if self._models_cache is None:
            self._models_cache = ollama._fetch_available_models() or [ollama.model or "desconocido"]
        models = self._models_cache

        # *** v19: Detectar si el modelo es pequeño y usar prompt compacto ***
        use_compact = self._should_use_compact_prompt()

        if use_compact:
            system_content = SYSTEM_PROMPT_COMPACT.format(
                so=os.name,
                repos_dir=REPOS_DIR,
                models=", ".join(models),
            )
        else:
            system_content = SYSTEM_PROMPT.format(
                so=os.name,
                repos_dir=REPOS_DIR,
                models=", ".join(models),
                corrections="Ver correcciones abajo"
            )

        # Perfil de usuario (personalizacion)
        user_profile = self._load_user_profile()
        if user_profile:
            profile_parts = []
            for key, label in [("name", "Nombre"), ("role", "Rol"), ("interests", "Intereses"), ("language", "Idioma preferido"), ("style", "Estilo de respuesta")]:
                if key in user_profile and user_profile[key]:
                    profile_parts.append(f"{label}: {user_profile[key]}")
            if profile_parts:
                system_content += "\n\n--- PERFIL DEL USUARIO ---\n" + "\n".join(profile_parts)

        # Contexto enriquecido desde Triple Memoria (con cache de embedding)
        enriched_context = self.memory.get_context_for(new_message)
        if enriched_context:
            system_content += f"\n\n--- CONTEXTO DE MEMORIA ---\n{enriched_context}"

        # Conocimiento relevante (sistema antiguo como backup)
        relevant_knowledge = learning.get_knowledge(new_message)
        if relevant_knowledge:
            knowledge_text = "\n".join([f"- {k['content']}" for k in relevant_knowledge[:3]])
            system_content += f"\n\nConocimiento adicional:\n{knowledge_text}"
        
        # *** NUEVO: Conocimiento aprendido de busquedas web previas ***
        try:
            from tools.web import get_web_learned
            web_knowledge = get_web_learned(new_message)
            if web_knowledge:
                system_content += f"\n\n--- CONOCIMIENTO WEB APRENDIDO ---\n{web_knowledge}"
        except Exception:
            pass

        # Enrich system prompt con conocimiento de skills relevantes
        if SKILLS_ENRICHMENT_AVAILABLE:
            try:
                system_content = enrich_prompt_with_skills(new_message, system_content)
            except Exception:
                pass  # No dejar que el enriquecimiento de skills rompa el agente

        messages = [{"role": "system", "content": system_content}]

        # Historial desde TripleMemory (unica fuente)
        recent_history = self.memory.short_term[-MAX_CONVERSATION_MEMORY:]
        for msg in recent_history:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # Mensaje actual
        messages.append({"role": "user", "content": new_message})

        return messages

    def _load_user_profile(self):
        """Carga el perfil de usuario desde archivo JSON."""
        try:
            if os.path.exists(USER_PROFILE_FILE):
                with open(USER_PROFILE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _should_use_compact_prompt(self) -> bool:
        """
        Determina si se debe usar el prompt compacto basándose en el tamaño del modelo.
        Los modelos < 8B se benefician de prompts más cortos.
        """
        if not ollama.model:
            return False

        model_lower = ollama.model.lower()

        # Modelos pequeños conocidos
        small_models = [
            "qwen3:4b", "qwen2.5:3b", "qwen2.5-coder:3b",
            "llama3.2:1b", "llama3.2:3b", "llama3.1:8b",
            "mistral:7b", "phi3:mini", "phi3:3.8b",
            "gemma2:2b", "gemma2:9b", "tinyllama",
        ]

        # Check exact match first
        if model_lower in small_models:
            return True

        # Check pattern: if model name contains size indicators
        size_patterns = [
            (r':(\d+)b', lambda m: int(m.group(1)) <= 8),
            (r'[-_](\d+)b', lambda m: int(m.group(1)) <= 8),
        ]
        for pattern, check in size_patterns:
            match = re.search(pattern, model_lower)
            if match:
                return check(match)

        return False

    # ----------------------------------------------------------
    # HELPERS
    # ----------------------------------------------------------
    def _resolve_params(self, params):
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str):
                value = value.replace("REPOS_DIR", REPOS_DIR)
                value = value.replace("RUTA_DEL_REPO", self._find_repo_path())
            resolved[key] = value
        return resolved

    def _find_repo_path(self):
        try:
            dirs = [d for d in os.listdir(REPOS_DIR)
                    if os.path.isdir(os.path.join(REPOS_DIR, d)) and not d.startswith(".")]
            if dirs:
                latest = max(dirs, key=lambda d: os.path.getmtime(os.path.join(REPOS_DIR, d)))
                return os.path.join(REPOS_DIR, latest)
        except Exception:
            pass
        return REPOS_DIR

    def _parse_json(self, text):
        """Parsea JSON de la respuesta del LLM con múltiples estrategias y auto-corrección."""
        # Estrategia 1: JSON directo
        try:
            return json.loads(text)
        except Exception:
            pass

        # Estrategia 2: Extraer de bloques de código markdown
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    # Intentar auto-corregir el JSON dentro del bloque
                    corrected = self._auto_fix_json(match.group(1))
                    if corrected:
                        return corrected
                    continue

        # Estrategia 3: Auto-corrección del texto completo
        corrected = self._auto_fix_json(text)
        if corrected:
            return corrected

        # Estrategia 4: Buscar múltiples JSONs en el texto
        jsons = self._extract_all_jsons(text)
        if len(jsons) == 1:
            return jsons[0]
        elif len(jsons) > 1:
            tool_calls = []
            for j in jsons:
                accion = j.get("accion", "").strip()
                if accion:
                    tool_calls.append({"name": accion, "params": j.get("params", {})})
            if tool_calls:
                return {"_multi_tool_calls": True, "tool_calls": tool_calls}
            return jsons[0]

        # Estrategia 5: Regex flexible para objeto JSON
        match = re.search(r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                # Último intento con auto-corrección
                corrected = self._auto_fix_json(match.group(1))
                if corrected:
                    return corrected

        return None

    def _auto_fix_json(self, text: str):
        """
        Intenta auto-corregir JSON malformado.
        Los modelos locales frecuentemente generan JSON con:
        - Comillas simples en vez de dobles
        - Comas trailing
        - Comentarios // dentro del JSON
        - Keys sin comillas
        - Missing closing braces
        """
        import re as _re

        # Si no parece JSON, no intentar
        if '{' not in text and '}' not in text:
            return None

        fixed = text

        # 1. Remover comentarios // style
        fixed = _re.sub(r'//.*?$', '', fixed, flags=_re.MULTILINE)

        # 2. Reemplazar comillas simples por dobles (solo si no están dentro de strings)
        # Estrategia simple: reemplazar 'key': por "key":
        fixed = _re.sub(r"'([^']+)':", r'"\1":', fixed)
        # Y valores string con comillas simples
        fixed = _re.sub(r":\s*'([^']*)'", r': "\1"', fixed)

        # 3. Remover trailing commas antes de } o ]
        fixed = _re.sub(r',\s*([}\]])', r'\1', fixed)

        # 4. Agregar comillas a keys sin comillas
        fixed = _re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', fixed)

        # 5. Agregar closing braces faltantes
        open_braces = fixed.count('{') - fixed.count('}')
        if open_braces > 0:
            fixed += '}' * open_braces

        # 6. Agregar closing brackets faltantes
        open_brackets = fixed.count('[') - fixed.count(']')
        if open_brackets > 0:
            fixed += ']' * open_brackets

        # Intentar parsear el JSON corregido
        try:
            result = json.loads(fixed)
            if isinstance(result, dict):
                return result
        except Exception:
            pass

        # 7. Último intento: extraer solo los campos que nos importan
        # Buscar accion, params, pensamiento, respuesta_final
        extracted = {}
        for field in ['accion', 'action', 'pensamiento', 'thought', 'respuesta_final', 'final_answer']:
            match = _re.search(rf'"{field}"\s*:\s*"([^"]*)"', fixed)
            if match:
                key = field
                if field == 'action':
                    key = 'accion'
                elif field == 'thought':
                    key = 'pensamiento'
                elif field == 'final_answer':
                    key = 'respuesta_final'
                extracted[key] = match.group(1)

        # Buscar params como objeto
        params_match = _re.search(r'"params?"\s*:\s*\{([^}]*)\}', fixed)
        if params_match:
            try:
                params = json.loads('{' + params_match.group(1) + '}')
                extracted['params'] = params
            except Exception:
                pass

        if extracted:
            return extracted

        return None

    def _extract_all_jsons(self, text):
        """Extrae todos los objetos JSON validos de un texto."""
        results = []
        # Buscar secuencias que parezcan JSON
        i = 0
        while i < len(text):
            # Encontrar el proximo '{'
            start = text.find('{', i)
            if start == -1:
                break
            # Intentar parsear desde este punto
            depth = 0
            end = start
            for j in range(start, len(text)):
                if text[j] == '{':
                    depth += 1
                elif text[j] == '}':
                    depth -= 1
                if depth == 0:
                    end = j + 1
                    break
            if end > start:
                try:
                    parsed = json.loads(text[start:end])
                    if isinstance(parsed, dict):
                        results.append(parsed)
                except Exception:
                    pass
                i = end
            else:
                i = start + 1
        return results

    def _looks_like_tool_json(self, text):
        """Detecta si el texto parece ser JSON de tool call (no respuesta al usuario).
        v3: Mas robusto - detecta JSON que empieza despues de whitespace o texto corto.
        """
        text = text.strip()
        if not text:
            return False
        # Si el texto empieza con { probablemente es JSON de tool call
        if text.startswith('{'):
            return True
        # Si despues de whitespace/newline hay {, tambien es JSON
        # Esto captura casos donde el modelo genera: "\n{" o "  {"
        stripped = text.lstrip()
        if stripped.startswith('{'):
            return True
        # Si contiene patrones de tool calls en cualquier parte
        tool_indicators = ['"accion"', '"pensamiento"', '"params"', '"respuesta_final"',
                          '"abrir_', '"ejecutar_', '"leer_', '"escribir_', '"buscar_"']
        for indicator in tool_indicators:
            if indicator in text:
                return True
        # Si el texto es corto y parece inicio de JSON
        if len(text) < 5 and text in ['{', '"', '\n', '\r']:
            return True
        return False

    def _detect_tool_calling_support(self):
        """Detecta si el modelo soporta function calling nativo."""
        ollama.detect_models()
        if ollama.model:
            model_lower = ollama.model.lower()
            # Modelos que SI soportan tool calling nativo
            if "qwen3" in model_lower:
                return True
            if "qwen2.5-coder" in model_lower:
                return True
            # Modelos que NO soportan tool calling
            if any(x in model_lower for x in ["qwen2.5:14b", "qwen2.5:32b", "llama3.1"]):
                return False
        # Test rapido
        try:
            import ollama as ollama_lib
            for host in ['http://localhost:11434', 'http://127.0.0.1:11434']:
                try:
                    client = ollama_lib.Client(host=host)
                    client.chat(
                        model=ollama.model,
                        messages=[{"role": "user", "content": "hi"}],
                        tools=[TOOL_SCHEMAS[0]]
                    )
                    return True
                except Exception:
                    continue
        except Exception:
            pass
        return False

    def _save_interaction(self, user_message, final_response):
        """Guarda la interaccion en la triple memoria + auto-aprende de busquedas web."""
        self.memory.add_conversation("user", user_message)
        self.memory.add_conversation("assistant", final_response)
        # Guardar interaccion sin embedding (mas rapido)
        self.memory.remember(
            f"Usuario pregunto: {user_message[:100]} -> Respuesta: {final_response[:200]}",
            metadata={"type": "interaction", "user_msg": user_message[:50]},
            fast=True  # skip_embedding para velocidad
        )
        self.memory.set_success(final_response[:100])
        
        # *** NUEVO: Auto-aprender de busquedas web ***
        # Si se uso buscar_web en esta interaccion, guardar el conocimiento
        web_tools_used = [t for t in self.metacognition.tool_history 
                         if t in ["buscar_web", "buscar_web_profundo", "leer_web"]]
        if web_tools_used:
            # Guardar que se aprendio algo de internet
            learning.add_knowledge(
                content=f"Pregunta: {user_message[:100]} | Respuesta: {final_response[:200]} | Fuentes: busqueda web",
                topic=f"web_learned:{user_message[:50]}",
                source="web_search"
            )
            # Tambien guardar en el cache de conocimiento web
            try:
                from tools.web import get_web_learned
                web_knowledge = get_web_learned(user_message)
                # El conocimiento ya se guardo automaticamente en _auto_learn_from_search
            except Exception:
                pass
