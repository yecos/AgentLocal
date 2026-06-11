"""
=============================================================
AGENTE v14 - Motor ReAct
=============================================================
Piensa -> Actua -> Observa -> Piensa de nuevo -> Repite.
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
from agent.schemas import SYSTEM_PROMPT, JSON_TOOLS_PROMPT
from agent.metacognition import Metacognition
from utils.metrics import get_metrics


class ReactAgent:
    """Motor ReAct: Piensa -> Actua -> Observa -> Piensa de nuevo."""

    # Rate limiting: max llamadas a la misma herramienta por conversacion
    MAX_SAME_TOOL_CALLS = 5
    MAX_TOTAL_TOOL_CALLS = 12

    def __init__(self, memory=None):
        self.memory = memory or TripleMemory()
        self.thinking_log = []
        self.supports_tool_calling = None
        self.metacognition = Metacognition()
        self._models_cache = None  # Cache de modelos para no llamar API cada vez
        self._tool_call_counts = {}  # Rate limiting por herramienta
        self._total_tool_calls = 0   # Total de tool calls en esta conversacion

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

        messages = self._build_messages(user_message)

        if self.supports_tool_calling is None:
            self.supports_tool_calling = self._detect_tool_calling_support()
            self._log(
                f"Tool calling nativo: {'SI' if self.supports_tool_calling else 'NO (usando JSON fallback)'}",
                "info"
            )

        for iteration in range(MAX_REACT_ITERATIONS):
            self._log(f"--- Iteracion {iteration + 1}/{MAX_REACT_ITERATIONS} ---", "react")

            meta_prompt = self.metacognition.get_metacognitive_prompt(iteration)
            if meta_prompt:
                self._log("Alerta metacognitiva inyectada", "evaluation")
                self._inject_metacognitive_prompt(messages, meta_prompt)

            if self.supports_tool_calling:
                action_result = self._react_with_tools(messages, iteration)
            else:
                action_result = self._react_with_json(messages, iteration)

            if action_result[0] == "respond":
                final_response = action_result[1]

                # PRIMERO: Evaluar resultado para poblar _last_evaluation
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
        Eventos: {"type": "text"|"tool_start"|"tool_result"|"meta"|"done", "data": ...}
        """
        self.thinking_log = []
        self.metacognition.reset()
        self._tool_call_counts = {}
        self._total_tool_calls = 0
        self._log(f"Mensaje del usuario: {user_message}", "input")

        messages = self._build_messages(user_message)

        if self.supports_tool_calling is None:
            self.supports_tool_calling = self._detect_tool_calling_support()
            self._log(
                f"Tool calling nativo: {'SI' if self.supports_tool_calling else 'NO (usando JSON fallback)'}",
                "info"
            )

        for iteration in range(MAX_REACT_ITERATIONS):
            self._log(f"--- Iteracion {iteration + 1}/{MAX_REACT_ITERATIONS} ---", "react")

            # Check metacognitivo
            meta_prompt = self.metacognition.get_metacognitive_prompt(iteration)
            if meta_prompt:
                self._log("Alerta metacognitiva inyectada", "evaluation")
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
            if is_final_response and not tool_calls_found:
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
                    yield {"type": "tool_start", "data": tc}

                results = self._execute_tool_calls(tool_calls_found, messages)

                for tc, res in zip(tool_calls_found, results):
                    had_error = "ERROR" in res
                    self.metacognition.record_iteration(
                        iteration=iteration, action_type="tool_result",
                        tool_name=tc["name"], result_summary=res[:200], had_error=had_error
                    )
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
                    full_content += chunk
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

            # Si llegamos aqui sin tool_calls, es respuesta final
            if full_content:
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
                messages[system_msg_idx]["content"] += JSON_TOOLS_PROMPT

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

            # 1. Si hay respuesta_final con contenido, usarla
            respuesta_final = parsed.get("respuesta_final", "").strip()
            if respuesta_final:
                return ("respond", respuesta_final)

            accion = parsed.get("accion", "").strip()
            params = parsed.get("params", {})
            pensamiento = parsed.get("pensamiento", "").strip()

            if pensamiento:
                self._log(f"Pensamiento: {pensamiento}", "thinking")

            # 2. Si hay accion valida, ejecutar herramienta
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
        """Limpia texto que tiene restos de formato JSON para mostrar al usuario."""
        # Si el texto es JSON completo, extraer solo el contenido util
        parsed = self._parse_json(text)
        if parsed:
            # Prioridad: respuesta_final > pensamiento > texto original
            if parsed.get("respuesta_final", "").strip():
                return parsed["respuesta_final"].strip()
            if parsed.get("pensamiento", "").strip():
                return parsed["pensamiento"].strip()
        # Si no es JSON, devolver tal cual (respuesta natural del modelo)
        return text

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
        try:
            return json.loads(text)
        except Exception:
            pass
        patterns = [
            r'```json\s*(.*?)\s*```',
            r'```\s*(.*?)\s*```',
            r'(\{[\s\S]*\})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    continue
        return None

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
        """Guarda la interaccion en la triple memoria."""
        self.memory.add_conversation("user", user_message)
        self.memory.add_conversation("assistant", final_response)
        # Guardar interaccion sin embedding (mas rapido)
        self.memory.remember(
            f"Usuario pregunto: {user_message[:100]} -> Respuesta: {final_response[:200]}",
            metadata={"type": "interaction", "user_msg": user_message[:50]},
            fast=True  # skip_embedding para velocidad
        )
        self.memory.set_success(final_response[:100])
