"""
=============================================================
AGENTE v14 - Motor ReAct
=============================================================
Piensa -> Actua -> Observa -> Piensa de nuevo -> Repite.
v14.1: Streaming, tool calling multiple, metacognicion basica.
       Usa TripleMemory como unica fuente de historial.
       Inyeccion de dependencias (memory, llm).
=============================================================
"""

import os
import re
import json
import logging
from datetime import datetime

from config import (
    REPOS_DIR, MAX_REACT_ITERATIONS, MAX_CONVERSATION_MEMORY, logger
)
from tools import TOOL_FUNCTIONS, TOOL_SCHEMAS
from memory.triple_memory import TripleMemory, learning
from llm import ollama
from agent.schemas import SYSTEM_PROMPT, JSON_TOOLS_PROMPT


class ReactAgent:
    """Motor ReAct: Piensa -> Actua -> Observa -> Piensa de nuevo."""

    def __init__(self, memory=None):
        self.memory = memory or TripleMemory()
        self.thinking_log = []
        self.supports_tool_calling = None

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
        self._log(f"Mensaje del usuario: {user_message}", "input")

        # Construir mensajes con memoria conversacional
        messages = self._build_messages(user_message)

        # Detectar si el modelo soporta tool calling (primera vez)
        if self.supports_tool_calling is None:
            self.supports_tool_calling = self._detect_tool_calling_support()
            self._log(
                f"Tool calling nativo: {'SI' if self.supports_tool_calling else 'NO (usando JSON fallback)'}",
                "info"
            )

        # BUCLE ReAct
        for iteration in range(MAX_REACT_ITERATIONS):
            self._log(f"--- Iteracion {iteration + 1}/{MAX_REACT_ITERATIONS} ---", "react")

            if self.supports_tool_calling:
                action_result = self._react_with_tools(messages, iteration)
            else:
                action_result = self._react_with_json(messages, iteration)

            if action_result[0] == "respond":
                final_response = action_result[1]
                self._log("Respuesta final generada", "success")
                self._save_interaction(user_message, final_response)
                return final_response, self.thinking_log

            elif action_result[0] == "tool_calls":
                tool_calls = action_result[1]
                # Ejecutar TODAS las tool calls de esta iteracion
                results = self._execute_tool_calls(tool_calls, messages)
                self._feed_tool_results(tool_calls, results, messages)

            elif action_result[0] == "error":
                self._log(f"Error: {action_result[1]}", "error")
                if iteration >= MAX_REACT_ITERATIONS - 1:
                    return "Tuve problemas para procesar tu solicitud. Puedes reformularla?", self.thinking_log

        self._log("Alcanzado limite de iteraciones", "warning")
        return "Alcance el limite de iteraciones. Puede que necesites ser mas especifico.", self.thinking_log

    # ----------------------------------------------------------
    # RUN CON STREAMING
    # ----------------------------------------------------------
    def run_stream(self, user_message):
        """
        Bucle ReAct con streaming. Yields eventos para la UI.
        Eventos: {"type": "text"|"thinking"|"tool_start"|"tool_result"|"done", "data": ...}
        """
        self.thinking_log = []
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

            if self.supports_tool_calling:
                result_type, result_data = self._react_with_tools_stream(messages, iteration)
            else:
                result_type, result_data = self._react_with_json(messages, iteration)

            if result_type == "respond":
                final_response = result_data
                self._log("Respuesta final generada", "success")
                self._save_interaction(user_message, final_response)
                yield {"type": "done", "data": final_response, "thinking_log": self.thinking_log}
                return

            elif result_type == "tool_calls":
                tool_calls = result_data
                for tc in tool_calls:
                    yield {"type": "tool_start", "data": tc}
                results = self._execute_tool_calls(tool_calls, messages)
                for tc, res in zip(tool_calls, results):
                    yield {"type": "tool_result", "data": {"tool": tc, "result": res}}
                self._feed_tool_results(tool_calls, results, messages)

            elif result_type == "streaming":
                # result_data es un generador de texto
                full_text = ""
                for chunk in result_data:
                    if isinstance(chunk, str):
                        full_text += chunk
                        yield {"type": "text", "data": chunk}
                    elif isinstance(chunk, dict):
                        # El generador retorno un resultado final (tool_calls o texto)
                        if isinstance(chunk, str):
                            full_text += chunk
                            yield {"type": "text", "data": chunk}
                        elif isinstance(chunk, dict):
                            # Tiene tool_calls
                            msg = chunk.get("message", chunk)
                            tool_calls = msg.get("tool_calls", [])
                            if tool_calls:
                                for tc in tool_calls:
                                    yield {"type": "tool_start", "data": tc}
                                results = self._execute_tool_calls(tool_calls, messages)
                                for tc, res in zip(tool_calls, results):
                                    yield {"type": "tool_result", "data": {"tool": tc, "result": res}}
                                self._feed_tool_results(tool_calls, results, messages)
                                break
                        elif chunk is None:
                            continue

                if full_text and not isinstance(chunk, dict):
                    self._log("Respuesta final generada (streaming)", "success")
                    self._save_interaction(user_message, full_text)
                    yield {"type": "done", "data": full_text, "thinking_log": self.thinking_log}
                    return

            elif result_type == "error":
                self._log(f"Error: {result_data}", "error")
                if iteration >= MAX_REACT_ITERATIONS - 1:
                    yield {"type": "done", "data": "Tuve problemas para procesar tu solicitud. Puedes reformularla?", "thinking_log": self.thinking_log}
                    return

        yield {"type": "done", "data": "Alcance el limite de iteraciones. Puede que necesites ser mas especifico.", "thinking_log": self.thinking_log}

    # ----------------------------------------------------------
    # REACT CON TOOL CALLING (sin streaming)
    # ----------------------------------------------------------
    def _react_with_tools(self, messages, iteration):
        """ReAct usando function calling nativo. Soporta multiple tool calls."""
        try:
            response = ollama.generate(messages, tools=TOOL_SCHEMAS)

            if isinstance(response, str):
                return ("respond", response)

            message = response.get("message", response)
            tool_calls = message.get("tool_calls", [])

            if tool_calls:
                # Parsear TODAS las tool calls
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
    # REACT CON TOOL CALLING (streaming)
    # ----------------------------------------------------------
    def _react_with_tools_stream(self, messages, iteration):
        """ReAct con streaming. Retorna (type, data) donde data puede ser un generador."""
        try:
            # Intentar streaming
            stream_gen = ollama.generate_stream(messages, tools=TOOL_SCHEMAS)
            collected_chunks = ""
            collected_tool_calls = []
            final_result = None

            for chunk in stream_gen:
                if isinstance(chunk, str):
                    collected_chunks += chunk
                elif isinstance(chunk, dict):
                    final_result = chunk

            if final_result is not None:
                if isinstance(final_result, dict):
                    msg = final_result.get("message", final_result)
                    tool_calls = msg.get("tool_calls", [])
                    content = msg.get("content", "")
                    if tool_calls:
                        parsed_calls = []
                        for tc in tool_calls:
                            tool_name = tc.get("function", {}).get("name", "")
                            tool_params = tc.get("function", {}).get("arguments", {})
                            self._log(f"Tool call: {tool_name}({tool_params})", "thinking")
                            parsed_calls.append({"name": tool_name, "params": tool_params})
                        return ("tool_calls", parsed_calls)
                    if content:
                        return ("respond", content)
                elif isinstance(final_result, str) and final_result:
                    return ("respond", final_result)

            if collected_chunks:
                return ("respond", collected_chunks)

            return ("error", "Respuesta vacia del modelo")

        except Exception as e:
            self._log(f"Error en tool calling stream: {e}", "error")
            # Fallback a modo no-streaming
            return self._react_with_tools(messages, iteration)

    # ----------------------------------------------------------
    # REACT CON JSON FALLBACK
    # ----------------------------------------------------------
    def _react_with_json(self, messages, iteration):
        """ReAct usando JSON parsing (fallback)."""
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
                return ("respond", response)

            if parsed.get("respuesta_final"):
                return ("respond", parsed["respuesta_final"])

            accion = parsed.get("accion", "")
            params = parsed.get("params", {})
            pensamiento = parsed.get("pensamiento", "")

            if pensamiento:
                self._log(f"Pensamiento: {pensamiento}", "thinking")

            if accion and accion in TOOL_FUNCTIONS:
                return ("tool_calls", [{"name": accion, "params": params}])

            return ("respond", response)

        except Exception as e:
            return ("error", str(e))

    # ----------------------------------------------------------
    # EJECUCION DE TOOLS (multiple)
    # ----------------------------------------------------------
    def _execute_tool_calls(self, tool_calls, messages):
        """Ejecuta multiples tool calls y retorna lista de resultados."""
        results = []
        for tc in tool_calls:
            tool_name = tc["name"]
            tool_params = tc["params"]

            self._log(f"Ejecutando: {tool_name}({tool_params})", "execution")
            tool_result = self._execute_tool(tool_name, tool_params)
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

            results.append(tool_result)
        return results

    def _feed_tool_results(self, tool_calls, results, messages):
        """Alimenta resultados de tools de vuelta al agente."""
        if self.supports_tool_calling:
            # Formato tool calling: assistant con tool_calls + tool messages
            assistant_msg = {"role": "assistant", "content": "", "tool_calls": []}
            for tc in tool_calls:
                assistant_msg["tool_calls"].append({
                    "function": {"name": tc["name"], "arguments": tc["params"]}
                })
            messages.append(assistant_msg)
            for tc, result in zip(tool_calls, results):
                messages.append({"role": "tool", "content": result})
        else:
            # Formato JSON: simular con mensajes de usuario
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
    # CONSTRUCCION DE MENSAJES
    # ----------------------------------------------------------
    def _build_messages(self, new_message):
        """Construye la lista de mensajes con CONTEXTO ENRIQUECIDO."""
        models = ollama._fetch_available_models() or [ollama.model or "desconocido"]
        system_content = SYSTEM_PROMPT.format(
            so=os.name,
            repos_dir=REPOS_DIR,
            models=", ".join(models),
            corrections="Ver correcciones abajo"
        )

        # Contexto enriquecido desde Triple Memoria
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
            if "qwen3" in model_lower:
                return True
            if any(x in model_lower for x in ["qwen2.5:14b", "qwen2.5:32b"]):
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
        self.memory.remember(
            f"Usuario pregunto: {user_message[:100]} -> Respuesta: {final_response[:200]}",
            metadata={"type": "interaction", "user_msg": user_message[:50]}
        )
        self.memory.set_success(final_response[:100])
