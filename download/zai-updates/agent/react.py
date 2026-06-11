"""
react.py — Agente ReAct para ZAI
Cambio: fix del orden de metacognición — ahora se ejecuta ANTES de
decidir la acción, no después. Esto permite que el agente evalúe
si necesita más información antes de comprometerse con una herramienta.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional, List, Dict, Any, Callable

from memory.triple_memory import TripleMemory
from utils.security import sanitize_input, is_safe_command

logger = logging.getLogger(__name__)


class ReActAgent:
    """
    Agente basado en el patrón ReAct (Reason + Act).

    Ciclo:
        1. **Observar**    — contexto de la conversación + memoria.
        2. **Metacognición** — evaluar si se tiene suficiente información.
        3. **Pensar**      — razonar sobre el siguiente paso.
        4. **Actuar**      — ejecutar una herramienta.
        5. **Observar**    — procesar el resultado.

    El fix de metacognición cambia el orden: antes se evaluaba
    *después* de actuar (paso 4→5→2), ahora se evalúa *antes*
    (paso 2→3→4), permitiendo que el agente decida si necesita
    consultar memoria o pedir aclaración antes de ejecutar.
    """

    MAX_ITERATIONS = 8

    def __init__(
        self,
        memory: Optional[TripleMemory] = None,
        tools: Optional[Dict[str, Callable]] = None,
        llm_fn: Optional[Callable] = None,
    ):
        self.memory = memory
        self.tools = tools or {}
        self.llm_fn = llm_fn
        self.history: List[Dict[str, str]] = []

    # ------------------------------------------------------------------ #
    #  run() — ciclo principal                                            #
    # ------------------------------------------------------------------ #
    def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Ejecuta el ciclo ReAct completo.

        Parámetros
        ----------
        user_input : str
            Entrada del usuario.
        context : dict, opcional
            Contexto adicional (p.ej. metadatos de sesión).

        Retorna
        -------
        str
            Respuesta final del agente.
        """
        # Sanitizar entrada del usuario
        user_input = sanitize_input(user_input)

        # Registrar en historia
        self.history.append({"role": "user", "content": user_input})

        # ── PASO 1: Observar ──
        observation = self._observe(user_input)

        for iteration in range(self.MAX_ITERATIONS):
            # ── PASO 2: Metacognición (ANTES de decidir) ──
            # *** FIX: Este paso antes estaba DESPUÉS de actuar ***
            meta_result = self._metacognize(user_input, observation)
            if meta_result.get("needs_clarification"):
                clarification = meta_result.get("clarification", "")
                logger.info("Metacognición: solicitando aclaración — %s", clarification)
                return clarification

            if meta_result.get("needs_more_context"):
                # Intentar recuperar contexto de la memoria
                extra = self._recall_from_memory(user_input)
                if extra:
                    observation += "\n\n[Contexto adicional de memoria]:\n" + extra

            # ── PASO 3: Pensar ──
            thought = self._think(user_input, observation)

            # ── PASO 4: Actuar ──
            action = self._extract_action(thought)

            if action is None:
                # No se requiere acción — responder directamente
                final = self._generate_response(user_input, observation, thought)
                self._store_in_memory(user_input, final)
                return final

            # Ejecutar la herramienta
            tool_result = self._execute_tool(action)

            # ── PASO 5: Observar resultado ──
            observation = self._observe_tool_result(tool_result)

            # Verificar si la observación responde la pregunta
            if self._is_final(observation, user_input):
                final = self._generate_response(user_input, observation, thought)
                self._store_in_memory(user_input, final)
                return final

        # Si se agotan las iteraciones
        logger.warning("ReAct: alcanzadas %d iteraciones sin respuesta final", self.MAX_ITERATIONS)
        return self._generate_response(user_input, observation, "Se alcanzó el límite de iteraciones.")

    # ------------------------------------------------------------------ #
    #  _observe() — recopilar contexto                                    #
    # ------------------------------------------------------------------ #
    def _observe(self, user_input: str) -> str:
        """Recopila contexto de la historia y memoria."""
        parts: List[str] = []

        # Historia reciente (últimos 6 turnos)
        recent = self.history[-6:]
        for msg in recent:
            role = msg["role"].upper()
            parts.append(f"{role}: {msg['content']}")

        # Memoria relevante
        if self.memory:
            try:
                memories = self.memory.recall(query=user_input, n_results=3)
                if memories:
                    mem_texts = [f"- {m['text']}" for m in memories[:3]]
                    parts.append("\n[Memoria relevante]:\n" + "\n".join(mem_texts))
            except Exception as exc:
                logger.warning("Error accediendo memoria en observe: %s", exc)

        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    #  _metacognize() — evaluación ANTES de actuar (FIX)                  #
    # ------------------------------------------------------------------ #
    def _metacognize(self, user_input: str, observation: str) -> Dict[str, Any]:
        """
        Evalúa si el agente tiene suficiente información para proceder.

        *** FIX CLAVE: Antes este paso se ejecutaba DESPUÉS de la acción,
        lo que causaba que el agente actuara sin información suficiente y
        luego se diera cuenta de que necesitaba más contexto. Ahora se
        ejecuta ANTES, permitiendo una mejor toma de decisiones. ***

        Retorna
        -------
        dict con claves:
            - needs_clarification (bool): si el input es ambiguo
            - needs_more_context (bool): si falta información
            - clarification (str): pregunta de aclaración si aplica
        """
        if self.llm_fn is None:
            return {"needs_clarification": False, "needs_more_context": False}

        prompt = (
            "Eres un módulo de metacognición. Evalúa si la siguiente "
            "consulta del usuario tiene suficiente contexto para responderla "
            "o si se necesita aclaración.\n\n"
            f"Historial y contexto:\n{observation}\n\n"
            f"Consulta: {user_input}\n\n"
            "Responde SOLO en JSON:\n"
            '{"needs_clarification": bool, "needs_more_context": bool, '
            '"clarification": "string o vacío"}'
        )

        try:
            raw = self.llm_fn([{"role": "user", "content": prompt}])
            # Intentar parsear JSON de la respuesta
            json_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as exc:
            logger.warning("Error en metacognición: %s", exc)

        return {"needs_clarification": False, "needs_more_context": False}

    # ------------------------------------------------------------------ #
    #  _think() — razonamiento                                            #
    # ------------------------------------------------------------------ #
    def _think(self, user_input: str, observation: str) -> str:
        """Genera un pensamiento sobre el siguiente paso."""
        if self.llm_fn is None:
            return f"Pensamiento: necesito responder a '{user_input[:50]}...'"

        prompt = (
            "Eres un asistente que sigue el patrón ReAct. "
            "Dado el contexto y la consulta, piensa paso a paso.\n\n"
            f"Contexto:\n{observation}\n\n"
            f"Consulta: {user_input}\n\n"
            "Si necesitas usar una herramienta, responde con:\n"
            "Action: <nombre_herramienta>\n"
            "Action Input: <parámetros>\n\n"
            "Si no necesitas herramientas, solo escribe tu razonamiento."
        )

        return self.llm_fn([{"role": "user", "content": prompt}])

    # ------------------------------------------------------------------ #
    #  _extract_action() — parsear acción del pensamiento                 #
    # ------------------------------------------------------------------ #
    def _extract_action(self, thought: str) -> Optional[Dict[str, str]]:
        """Extrae la acción y sus parámetros del pensamiento."""
        action_match = re.search(r'Action:\s*(\w+)', thought)
        input_match = re.search(r'Action Input:\s*(.+?)(?:\n|$)', thought)

        if action_match:
            tool_name = action_match.group(1)
            tool_input = input_match.group(1).strip() if input_match else ""
            return {"tool": tool_name, "input": tool_input}
        return None

    # ------------------------------------------------------------------ #
    #  _execute_tool()                                                    #
    # ------------------------------------------------------------------ #
    def _execute_tool(self, action: Dict[str, str]) -> str:
        """Ejecuta una herramienta registrada."""
        tool_name = action["tool"]
        tool_input = action.get("input", "")

        if tool_name not in self.tools:
            return f"Error: herramienta '{tool_name}' no encontrada."

        tool_fn = self.tools[tool_name]

        try:
            # Sanitizar input de la herramienta
            tool_input = sanitize_input(tool_input)

            # Verificar seguridad si es un comando del sistema
            if tool_name in ("sistema", "shell", "exec") and not is_safe_command(tool_input):
                return f"Error: comando bloqueado por políticas de seguridad: '{tool_input}'"

            result = tool_fn(tool_input)
            self.history.append({
                "role": "assistant",
                "content": f"[Action: {tool_name}] {tool_input} → {result}",
            })
            return str(result)
        except Exception as exc:
            logger.error("Error ejecutando herramienta %s: %s", tool_name, exc)
            return f"Error ejecutando {tool_name}: {exc}"

    # ------------------------------------------------------------------ #
    #  _observe_tool_result()                                             #
    # ------------------------------------------------------------------ #
    def _observe_tool_result(self, tool_result: str) -> str:
        """Transforma el resultado de una herramienta en observación."""
        return f"[Resultado de herramienta]: {tool_result}"

    # ------------------------------------------------------------------ #
    #  _is_final()                                                        #
    # ------------------------------------------------------------------ #
    def _is_final(self, observation: str, original_query: str) -> bool:
        """Determina si la observación responde la consulta original."""
        # Heurística simple: si la observación tiene contenido sustancial
        # y no contiene "Error:", considerar como respuesta potencial
        if "Error:" in observation:
            return False
        if len(observation) > 50:
            return True
        return False

    # ------------------------------------------------------------------ #
    #  _generate_response()                                               #
    # ------------------------------------------------------------------ #
    def _generate_response(
        self, user_input: str, observation: str, thought: str
    ) -> str:
        """Genera la respuesta final al usuario."""
        if self.llm_fn is None:
            return observation

        prompt = (
            "Eres ZAI, un asistente inteligente. Con base en la siguiente "
            "información, responde de forma clara y útil.\n\n"
            f"Consulta: {user_input}\n"
            f"Contexto: {observation}\n"
            f"Pensamiento: {thought}\n\n"
            "Respuesta:"
        )

        response = self.llm_fn([{"role": "user", "content": prompt}])
        self.history.append({"role": "assistant", "content": response})
        return response

    # ------------------------------------------------------------------ #
    #  _recall_from_memory()                                              #
    # ------------------------------------------------------------------ #
    def _recall_from_memory(self, query: str) -> Optional[str]:
        """Recupera contexto adicional de la memoria."""
        if self.memory is None:
            return None
        try:
            results = self.memory.recall(query=query, n_results=3)
            if results:
                return "\n".join(r["text"] for r in results[:3])
        except Exception as exc:
            logger.warning("Error en recall de memoria: %s", exc)
        return None

    # ------------------------------------------------------------------ #
    #  _store_in_memory()                                                 #
    # ------------------------------------------------------------------ #
    def _store_in_memory(self, user_input: str, response: str) -> None:
        """Almacena la interacción en la memoria de corto plazo."""
        if self.memory is None:
            return
        try:
            interaction = f"Usuario: {user_input}\nAsistente: {response}"
            self.memory.add(text=interaction, layer="short")
        except Exception as exc:
            logger.warning("Error almacenando en memoria: %s", exc)

    # ------------------------------------------------------------------ #
    #  reset()                                                            #
    # ------------------------------------------------------------------ #
    def reset(self) -> None:
        """Limpia la historia de la conversación."""
        self.history.clear()
