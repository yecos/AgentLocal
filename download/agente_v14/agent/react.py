"""
=============================================================
AGENTE v14 - Motor ReAct
=============================================================
Piensa -> Actua -> Observa -> Piensa de nuevo -> Repite.
v14: Usa TripleMemory como unica fuente de historial.
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
                # Guardar en Triple Memoria
                self.memory.add_conversation("user", user_message)
                self.memory.add_conversation("assistant", final_response)
                # Aprender de la interaccion
                self.memory.remember(
                    f"Usuario pregunto: {user_message[:100]} -> Respuesta: {final_response[:200]}",
                    metadata={"type": "interaction", "user_msg": user_message[:50]}
                )
                self.memory.set_success(final_response[:100])
                return final_response, self.thinking_log

            elif action_result[0] == "tool_call":
                tool_name = action_result[1]
                tool_params = action_result[2]

                self._log(f"Ejecutando: {tool_name}({tool_params})", "execution")
                tool_result = self._execute_tool(tool_name, tool_params)
                self._log(f"Resultado: {tool_result[:150]}...", "observation")

                # Alimentar memoria de trabajo
                self.memory.add_step(f"{tool_name}({tool_params})", tool_result[:200])
                if "ERROR" in tool_result:
                    self.memory.set_error(f"{tool_name}: {tool_result[:100]}")
                if len(tool_result) > 50 and "ERROR" not in tool_result:
                    self.memory.remember(
                        f"Resultado de {tool_name}: {tool_result[:300]}",
                        metadata={"type": "tool_result", "tool": tool_name}
                    )

                # Alimentar resultado de vuelta al agente
                if self.supports_tool_calling:
                    messages.append({"role": "assistant", "content": "",
                                     "tool_calls": [{
                                         "function": {"name": tool_name, "arguments": tool_params}
                                     }]})
                    messages.append({"role": "tool", "content": tool_result})
                else:
                    messages.append({"role": "assistant",
                                     "content": json.dumps({
                                         "pensamiento": f"Ejecute {tool_name}",
                                         "accion": tool_name,
                                         "params": tool_params
                                     })})
                    messages.append({"role": "user",
                                     "content": f"Resultado de {tool_name}: {tool_result}\n\nQue hago ahora? Responde con JSON."})

            elif action_result[0] == "error":
                self._log(f"Error: {action_result[1]}", "error")
                if iteration >= MAX_REACT_ITERATIONS - 1:
                    return "Tuve problemas para procesar tu solicitud. Puedes reformularla?", self.thinking_log

        self._log("Alcanzado limite de iteraciones", "warning")
        return "Alcance el limite de iteraciones. Puede que necesites ser mas especifico.", self.thinking_log

    def _react_with_tools(self, messages, iteration):
        """ReAct usando function calling nativo."""
        try:
            response = ollama.generate(messages, tools=TOOL_SCHEMAS)

            if isinstance(response, str):
                return ("respond", response)

            message = response.get("message", response)
            tool_calls = message.get("tool_calls", [])

            if tool_calls:
                tc = tool_calls[0]
                tool_name = tc.get("function", {}).get("name", "")
                tool_params = tc.get("function", {}).get("arguments", {})
                self._log(f"Tool call: {tool_name}({tool_params})", "thinking")
                return ("tool_call", tool_name, tool_params)

            content = message.get("content", "")
            if content:
                return ("respond", content)

            return ("error", "Respuesta vacia del modelo")

        except Exception as e:
            self._log(f"Error en tool calling: {e}", "error")
            self.supports_tool_calling = False
            return ("error", str(e))

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
                return ("tool_call", accion, params)

            return ("respond", response)

        except Exception as e:
            return ("error", str(e))

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

    def _execute_tool(self, tool_name, params):
        """Ejecuta una herramienta por nombre."""
        if tool_name in TOOL_FUNCTIONS:
            try:
                params = self._resolve_params(params)
                return TOOL_FUNCTIONS[tool_name](**params)
            except Exception as e:
                return f"ERROR ejecutando {tool_name}: {e}"
        return f"Herramienta no encontrada: {tool_name}"

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
