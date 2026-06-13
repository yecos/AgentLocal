"""
=============================================================
AGENTE v14 - Pensamiento Profundo (Deep Thinking)
=============================================================
Sistema de razonamiento extendido que permite al agente
"pensar en voz alta" antes de actuar.

Estrategias:
1. NATIVA: Modelos con <think> nativo (qwen3, deepseek-r1)
   - Ollama API param think=True
   - El modelo genera razonamiento interno automático
2. COT (Chain-of-Thought): Para modelos sin think nativo
   - Fase previa de descomposición y planificación
   - LLM genera plan de acción antes de ejecutar
3. REFLEXIÓN: Post-evaluación crítica de la respuesta
   - Revisa su propia respuesta antes de entregarla
   - Puede corregir errores o mejorar la calidad

Se integra como fase PREVIA al bucle ReAct y como
filtro POST de la respuesta final.
=============================================================
"""

import json
import logging
from datetime import datetime

from config import logger, DEEP_THINKING_MODE, DEEP_THINKING_MIN_COMPLEXITY
from llm import ollama


class DeepThinkingResult:
    """Resultado de una sesión de pensamiento profundo."""

    def __init__(self):
        self.reasoning = ""        # Texto del razonamiento
        self.plan = []             # Pasos planificados
        self.complexity = 0.0      # Complejidad detectada (0-1)
        self.query_type = ""       # Tipo de consulta
        self.confidence = 0.5      # Confianza en el plan
        self.should_deep_think = False  # Si se activó deep thinking
        self.thinking_tokens = 0   # Tokens de pensamiento generados
        self.duration_ms = 0       # Duración en ms

    def to_dict(self):
        return {
            "reasoning": self.reasoning[:500],
            "plan": self.plan,
            "complexity": self.complexity,
            "query_type": self.query_type,
            "confidence": self.confidence,
            "should_deep_think": self.should_deep_think,
            "thinking_tokens": self.thinking_tokens,
            "duration_ms": self.duration_ms,
        }


class DeepThinking:
    """
    Motor de pensamiento profundo.

    Se inserta ANTES del bucle ReAct para:
    1. Evaluar la complejidad de la consulta
    2. Generar razonamiento extendido si es necesario
    3. Descomponer tareas complejas en pasos
    4. Planificar la secuencia de herramientas

    Y DESPUÉS del bucle para:
    5. Criticar y mejorar la respuesta final
    """

    # Indicadores de complejidad que justifican pensamiento profundo
    COMPLEXITY_INDICATORS = {
        # Indicadores de alta complejidad (+0.3 cada uno)
        "high": [
            "analiza", "analizar", "compara", "comparar", "diferencia",
            "explica", "explicar", "resume", "resumir", "evalua",
            "evaluar", "diseña", "diseñar", "implementar", "implementa",
            "arquitectura", "optimiza", "optimizar", "refactoriza",
            "debug", "depurar", "diagnostica", "diagnosticar",
            "planifica", "planificar", "crea", "crear", "desarrolla",
            "desarrollar", "construye", "construir", "migra",
            "integra", "integrar", "configura", "configurar",
        ],
        # Indicadores de complejidad media (+0.15 cada uno)
        "medium": [
            "como", "cómo", "por que", "por qué", "cuando", "cuándo",
            "donde", "dónde", "cual", "cuál", "cuales", "cuáles",
            "mejor", "peor", "problema", "error", "fallo", "bug",
            "instalar", "configurar", "actualizar", "mover",
            "buscar", "encontrar", "reemplazar",
        ],
        # Indicadores de baja complejidad (no necesitan deep thinking)
        "simple": [
            "hola", "hey", "gracias", "si", "no", "ok",
            "abre", "cierra", "mata", "lista",
        ],
    }

    # Tipos de consulta y su tratamiento
    QUERY_TYPES = {
        "analytical": "Requiere análisis profundo y razonamiento",
        "creative": "Requiere generación original y diseño",
        "procedural": "Requiere secuencia de pasos técnicos",
        "factual": "Requiere búsqueda y presentación de información",
        "conversational": "Conversación casual, sin deep thinking",
    }

    def __init__(self, mode=None):
        """
        Args:
            mode: "native", "cot", "reflection", "full", "off"
                  None = usar DEEP_THINKING_MODE de config
        """
        self.mode = mode or DEEP_THINKING_MODE
        self._stats = {
            "total_queries": 0,
            "deep_think_activated": 0,
            "reflections_triggered": 0,
            "responses_improved": 0,
            "avg_complexity": 0.0,
        }

    def should_think_deep(self, user_message):
        """
        Evalúa si una consulta merece pensamiento profundo.

        Retorna: (should_think: bool, complexity: float, query_type: str)
        """
        if self.mode == "off":
            return False, 0.0, "conversational"

        msg_lower = user_message.lower()

        # Calcular score de complejidad
        complexity = 0.0
        high_matches = sum(1 for w in self.COMPLEXITY_INDICATORS["high"] if w in msg_lower)
        medium_matches = sum(1 for w in self.COMPLEXITY_INDICATORS["medium"] if w in msg_lower)
        simple_matches = sum(1 for w in self.COMPLEXITY_INDICATORS["simple"] if w in msg_lower)

        complexity += min(high_matches * 0.25, 0.6)
        complexity += min(medium_matches * 0.1, 0.3)
        complexity -= min(simple_matches * 0.3, 0.5)
        complexity = max(0.0, min(1.0, complexity))

        # Bonus por longitud (consultas largas suelen ser más complejas)
        if len(user_message) > 200:
            complexity += 0.15
        elif len(user_message) > 100:
            complexity += 0.08

        # Bonus por múltiples preguntas
        question_marks = msg_lower.count("?") + msg_lower.count("¿")
        if question_marks >= 3:
            complexity += 0.15
        elif question_marks >= 2:
            complexity += 0.08

        # Determinar tipo de consulta
        if high_matches >= 2:
            query_type = "analytical"
        elif any(w in msg_lower for w in ["crea", "diseña", "genera", "construye"]):
            query_type = "creative"
        elif any(w in msg_lower for w in ["instalar", "configurar", "ejecutar", "mover"]):
            query_type = "procedural"
        elif any(w in msg_lower for w in ["que es", "qué es", "busca", "encuentra"]):
            query_type = "factual"
        else:
            query_type = "conversational"

        # Decidir si activar deep thinking
        should = complexity >= DEEP_THINKING_MIN_COMPLEXITY

        self._stats["total_queries"] += 1
        if should:
            self._stats["deep_think_activated"] += 1

        # Actualizar avg complexity
        total = self._stats["total_queries"]
        self._stats["avg_complexity"] = (
            self._stats["avg_complexity"] * (total - 1) + complexity
        ) / total

        return should, complexity, query_type

    def think(self, user_message, context=""):
        """
        Genera pensamiento profundo antes de actuar.

        Fase 1: Análisis de la consulta
        Fase 2: Descomposición en sub-tareas
        Fase 3: Planificación de herramientas

        Args:
            user_message: Mensaje del usuario
            context: Contexto adicional (de memoria, etc.)

        Returns:
            DeepThinkingResult con el razonamiento y plan
        """
        import time
        start = time.time()

        result = DeepThinkingResult()

        should, complexity, query_type = self.should_think_deep(user_message)
        result.complexity = complexity
        result.query_type = query_type
        result.should_deep_think = should

        if not should or self.mode == "off":
            return result

        self._log(f"Deep thinking activado (complejidad={complexity:.2f}, tipo={query_type})")

        # ---- FASE 1: Razonamiento extendido (Chain-of-Thought) ----
        reasoning = self._generate_reasoning(user_message, context, query_type)
        if reasoning:
            result.reasoning = reasoning
            result.thinking_tokens = len(reasoning.split())

        # ---- FASE 2: Descomposición y planificación ----
        plan = self._generate_plan(user_message, reasoning, query_type)
        if plan:
            result.plan = plan
            result.confidence = self._estimate_plan_confidence(plan)

        result.duration_ms = int((time.time() - start) * 1000)
        self._log(
            f"Deep thinking completado: {result.thinking_tokens} tokens, "
            f"{len(result.plan)} pasos, {result.duration_ms}ms"
        )

        return result

    def reflect(self, user_message, response, had_errors=False):
        """
        Post-reflexión: evalúa y potencialmente mejora la respuesta final.

        Se ejecuta DESPUÉS del bucle ReAct, antes de entregar la respuesta.

        Args:
            user_message: Consulta original
            response: Respuesta generada
            had_errors: Si hubo errores durante la ejecución

        Returns:
            (improved_response: str, was_improved: bool)
        """
        if self.mode in ("off", "native"):
            # En modo native, el modelo ya piensa internamente
            return response, False

        # No reflejar respuestas cortas o casuales
        if len(response) < 50:
            return response, False

        # Solo reflejar si la complejidad lo justifica o hubo errores
        should, complexity, _ = self.should_think_deep(user_message)
        if not should and not had_errors:
            return response, False

        self._stats["reflections_triggered"] += 1
        self._log("Post-reflexión activada")

        reflection_prompt = f"""Eres un crítico interno. Evalúa esta respuesta y mejórala si es necesario.

CONSULTA ORIGINAL: {user_message}

RESPUESTA GENERADA:
{response}

HUBO ERRORES DURANTE LA EJECUCIÓN: {"Sí" if had_errors else "No"}

EVALÚA:
1. ¿La respuesta es completa y precisa?
2. ¿Hay información incorrecta o ambigua?
3. ¿Se puede mejorar la claridad o estructura?

Si la respuesta es buena, retorna "APROBADA" seguido de la respuesta original.
Si necesita mejoras, retorna la versión mejorada directamente.

RESPUESTA MEJORADA:"""

        try:
            improved = ollama.generate_chat([
                {"role": "system", "content": "Eres un crítico interno que mejora respuestas. Responde en español. Sé conciso."},
                {"role": "user", "content": reflection_prompt}
            ])

            if improved and improved.strip():
                # Si el modelo aprobó la respuesta original
                if improved.strip().startswith("APROBADA"):
                    approved = improved.replace("APROBADA", "", 1).strip()
                    return approved if approved else response, False

                # Si la mejora es significativamente mejor
                if len(improved) > len(response) * 0.7:
                    self._stats["responses_improved"] += 1
                    self._log("Respuesta mejorada via reflexión")
                    return improved, True

        except Exception as e:
            logger.debug(f"Post-reflexión falló (no crítico): {e}")

        return response, False

    def _generate_reasoning(self, user_message, context, query_type):
        """Genera razonamiento extendido (Chain-of-Thought) antes de actuar."""
        reasoning_prompt = f"""Analiza esta consulta paso a paso antes de actuar.

CONSULTA: {user_message}
TIPO: {query_type}
{f"CONTEXTO DISPONIBLE: {context[:500]}" if context else ""}

PIENSA EN VOZ ALTA:
1. ¿Qué quiere realmente el usuario? (intención profunda)
2. ¿Qué información necesito? (datos, archivos, estado del sistema)
3. ¿Cuáles son los posibles obstáculos? (errores comunes, dependencias)
4. ¿Cuál es la secuencia óptima de acciones? (pasos ordenados)
5. ¿Hay alternativas si el plan A falla? (plan B)

RAZONAMIENTO:"""

        try:
            reasoning = ollama.generate_chat([
                {"role": "system", "content": (
                    "Eres un sistema de razonamiento interno. "
                    "Genera análisis profundo antes de actuar. "
                    "Responde en español. Sé estructurado y conciso."
                )},
                {"role": "user", "content": reasoning_prompt}
            ])
            return reasoning or ""
        except Exception as e:
            logger.debug(f"Generación de razonamiento falló: {e}")
            return ""

    def _generate_plan(self, user_message, reasoning, query_type):
        """Genera un plan de acción estructurado."""
        plan_prompt = f"""Basándote en este análisis, genera un plan de acción concreto.

CONSULTA: {user_message}
RAZONAMIENTO: {reasoning[:600] if reasoning else "Sin razonamiento previo"}

Genera un plan en formato JSON con esta estructura exacta:
{{
    "steps": [
        {{"action": "descripción de la acción", "tool": "herramienta a usar o 'responder'", "purpose": "por qué este paso"}},
        ...
    ],
    "estimated_iterations": 2,
    "fallback": "qué hacer si el plan falla"
}}

PLAN:"""

        try:
            plan_text = ollama.generate_chat([
                {"role": "system", "content": (
                    "Generas planes de acción concretos. "
                    "Responde SOLO con JSON válido. "
                    "Máximo 5 pasos. Sé práctico."
                )},
                {"role": "user", "content": plan_prompt}
            ])

            if plan_text:
                # Intentar parsear JSON
                # Buscar JSON en la respuesta (puede estar en code block)
                json_str = plan_text
                if "```json" in json_str:
                    json_str = json_str.split("```json")[1].split("```")[0]
                elif "```" in json_str:
                    json_str = json_str.split("```")[1].split("```")[0]

                try:
                    plan_data = json.loads(json_str.strip())
                    return plan_data.get("steps", [])
                except json.JSONDecodeError:
                    # Fallback: parsear como lista numerada
                    steps = []
                    for line in plan_text.strip().split("\n"):
                        line = line.strip()
                        if line and (line[0].isdigit() or line.startswith("-")):
                            action = line.lstrip("0123456789.-) ").strip()
                            if action:
                                steps.append({
                                    "action": action,
                                    "tool": "infer",
                                    "purpose": "auto"
                                })
                    return steps[:5]

        except Exception as e:
            logger.debug(f"Generación de plan falló: {e}")

        return []

    def _estimate_plan_confidence(self, plan):
        """Estima la confianza en el plan generado."""
        if not plan:
            return 0.3
        # Más pasos = más estructura = más confianza (hasta un punto)
        n_steps = len(plan)
        if n_steps == 1:
            return 0.5
        elif n_steps <= 3:
            return 0.7
        elif n_steps <= 5:
            return 0.8
        else:
            return 0.6  # Demasiados pasos = incertidumbre

    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        logger.info(f"[{timestamp}] [DEEP_THINK] {message}")

    def get_thinking_prompt(self, deep_result):
        """
        Genera el prompt de pensamiento profundo para inyectar en el ReAct.

        Se inyecta como contexto adicional antes de la primera iteración.
        """
        if not deep_result or not deep_result.should_deep_think:
            return ""

        parts = ["=== PENSAMIENTO PROFUNDO (análisis previo) ==="]

        if deep_result.reasoning:
            parts.append(f"RAZONAMIENTO:\n{deep_result.reasoning[:400]}")

        if deep_result.plan:
            parts.append("PLAN DE ACCIÓN:")
            for i, step in enumerate(deep_result.plan[:5], 1):
                action = step.get("action", step.get("accion", ""))
                tool = step.get("tool", step.get("herramienta", ""))
                purpose = step.get("purpose", step.get("proposito", ""))
                parts.append(f"  {i}. [{tool}] {action}")
                if purpose and purpose != "auto":
                    parts.append(f"     → {purpose}")

        if deep_result.confidence < 0.5:
            parts.append("⚠️ Baja confianza en el plan. Considera pedir aclaración al usuario.")

        parts.append("=== FIN PENSAMIENTO PROFUNDO ===")
        parts.append("Usa este análisis como guía, pero adapta según lo que descubras al ejecutar.")

        return "\n".join(parts)

    def stats(self):
        """Retorna estadísticas del módulo de pensamiento profundo."""
        return self._stats.copy()


def detect_native_thinking_support(model_name):
    """
    Detecta si un modelo soporta pensamiento nativo (think tags).

    Modelos con soporte nativo:
    - qwen3 (cualquier variante)
    - deepseek-r1
    - qwq
    - Phi-4-reasoning

    Returns:
        bool: Si el modelo soporta think nativo
    """
    if not model_name:
        return False

    model_lower = model_name.lower()

    # Modelos conocidos con soporte nativo de think
    native_think_models = [
        "qwen3",          # Qwen3 con think nativo
        "deepseek-r1",    # DeepSeek R1
        "qwq",            # QwQ reasoning model
        "phi-4-reason",   # Phi-4 reasoning
        "marco-o1",       # Marco O1
    ]

    return any(m in model_lower for m in native_think_models)
