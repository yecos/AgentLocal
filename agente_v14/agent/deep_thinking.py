"""
=============================================================
AGENTE v14.7 - Pensamiento Profundo (Deep Thinking) MEJORADO
=============================================================
Sistema de razonamiento extendido que permite al agente
"pensar en voz alta" antes de actuar.

v14.7 Mejoras:
1. Think nativo con tools: two-phase approach (think first, then act)
2. Razonamiento multi-vuelta: iterativo con auto-critica
3. Complejidad hibrida: heuristica + LLM para casos ambiguos
4. Budget de tokens: respeta DEEP_THINKING_MAX_THINKING_TOKENS
5. Deepening progresivo: 4 niveles de profundidad
6. Reflexion con contexto: acceso a resultados intermedios de tools
7. Persistencia: guarda pensamientos en memoria para futuro
8. Confianza basada en contenido: evalua calidad del plan

Estrategias:
1. NATIVA: Modelos con <think> nativo (qwen3, deepseek-r1)
   - Two-phase: think primero, luego act con tools
   - Ollama API param think=True en fase de razonamiento
2. COT (Chain-of-Thought): Para modelos sin think nativo
   - Fase previa de descomposicion y planificacion
   - Razonamiento multi-vuelta con auto-critica
3. REFLEXION: Post-evaluacion critica de la respuesta
   - Revisa su propia respuesta con contexto de ejecucion
   - Puede corregir errores o mejorar la calidad
4. FULL: Cot + native + reflection (recomendado)

Se integra como fase PREVIA al bucle ReAct y como
filtro POST de la respuesta final.
=============================================================
"""

import json
import logging
import time
from datetime import datetime

from config import (
    logger, DEEP_THINKING_MODE, DEEP_THINKING_MIN_COMPLEXITY,
    DEEP_THINKING_MAX_THINKING_TOKENS, DEEP_THINKING_REFLECT_ON_ERRORS,
    DEEP_THINKING_SHOW_THOUGHTS, LEARN_DIR
)
from llm import ollama

# ============================================================
# NIVELES DE PROFUNDIDAD DEL PENSAMIENTO
# ============================================================
THINK_DEPTH_NONE = 0       # Sin pensamiento (consultas simples)
THINK_DEPTH_QUICK = 1      # Analisis rapido (complejidad baja-media)
THINK_DEPTH_FULL = 2       # CoT completo + planificacion (complejidad alta)
THINK_DEPTH_DEEP = 3       # Razonamiento multi-vuelta + auto-critica (muy alta)


class DeepThinkingResult:
    """Resultado de una sesion de pensamiento profundo."""

    def __init__(self):
        self.reasoning = ""        # Texto del razonamiento
        self.plan = []             # Pasos planificados
        self.complexity = 0.0      # Complejidad detectada (0-1)
        self.query_type = ""       # Tipo de consulta
        self.confidence = 0.5      # Confianza en el plan
        self.should_deep_think = False  # Si se activo deep thinking
        self.thinking_tokens = 0   # Tokens de pensamiento generados
        self.duration_ms = 0       # Duracion en ms
        self.depth = THINK_DEPTH_NONE  # Nivel de profundidad alcanzado
        self.native_thinking = ""  # Thinking nativo del modelo (si aplica)
        self.critique_rounds = 0   # Numero de rondas de auto-critica
        self.reasoning_evolution = []  # Razonamiento en cada ronda (para debugging)

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
            "depth": self.depth,
            "critique_rounds": self.critique_rounds,
        }


class DeepThinking:
    """
    Motor de pensamiento profundo v14.7.

    Se inserta ANTES del bucle ReAct para:
    1. Evaluar la complejidad de la consulta (heuristica + LLM)
    2. Generar razonamiento extendido si es necesario
    3. Descomponer tareas complejas en pasos
    4. Planificar la secuencia de herramientas
    5. Auto-criticar y refinar el razonamiento

    Y DESPUES del bucle para:
    6. Criticar y mejorar la respuesta final (con contexto de tools)
    7. Persistir aprendizajes del pensamiento en memoria
    """

    # Indicadores de complejidad que justifican pensamiento profundo
    COMPLEXITY_INDICATORS = {
        # Indicadores de alta complejidad (+0.3 cada uno)
        "high": [
            "analiza", "analizar", "compara", "comparar", "diferencia",
            "explica", "explicar", "resume", "resumir", "evalua",
            "evaluar", "disena", "disenar", "implementar", "implementa",
            "arquitectura", "optimiza", "optimizar", "refactoriza",
            "debug", "depurar", "diagnostica", "diagnosticar",
            "planifica", "planificar", "crea", "crear", "desarrolla",
            "desarrollar", "construye", "construir", "migra",
            "integra", "integrar", "configura", "configurar",
        ],
        # Indicadores de complejidad media (+0.15 cada uno)
        "medium": [
            "como", "como", "por que", "por que", "cuando", "cuando",
            "donde", "donde", "cual", "cual", "cuales", "cuales",
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
        "analytical": "Requiere analisis profundo y razonamiento",
        "creative": "Requiere generacion original y diseno",
        "procedural": "Requiere secuencia de pasos tecnicos",
        "factual": "Requiere busqueda y presentacion de informacion",
        "conversational": "Conversacion casual, sin deep thinking",
    }

    # Rangos de complejidad para cada nivel de profundidad
    DEPTH_THRESHOLDS = {
        THINK_DEPTH_QUICK: 0.3,   # >= 0.3: analisis rapido
        THINK_DEPTH_FULL: 0.5,    # >= 0.5: CoT completo + plan
        THINK_DEPTH_DEEP: 0.75,   # >= 0.75: razonamiento multi-vuelta
    }

    # Max rondas de auto-critica en nivel DEEP
    MAX_CRITIQUE_ROUNDS = 2

    # Rango de complejidad donde se usa LLM para desempatar
    LLM_AMBIGUITY_RANGE = (0.2, 0.5)

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
            "by_depth": {0: 0, 1: 0, 2: 0, 3: 0},
            "llm_complexity_calls": 0,
            "native_think_used": 0,
            "persisted_thoughts": 0,
        }

    # ----------------------------------------------------------
    # EVALUACION DE COMPLEJIDAD
    # ----------------------------------------------------------

    def should_think_deep(self, user_message):
        """
        Evalua si una consulta merece pensamiento profundo.

        Usa evaluacion hibrida: heuristica rapida + LLM para casos ambiguos.

        Retorna: (should_think: bool, complexity: float, query_type: str)
        """
        if self.mode == "off":
            return False, 0.0, "conversational"

        msg_lower = user_message.lower()

        # ---- FASE 1: Evaluacion heuristica (rapida, sin LLM) ----
        complexity = self._heuristic_complexity(msg_lower, user_message)

        # ---- FASE 2: Evaluacion LLM para casos ambiguos ----
        # Si la heuristica da un resultado en zona ambigua, consultar al LLM
        low, high = self.LLM_AMBIGUITY_RANGE
        if low <= complexity <= high and len(user_message) > 30:
            llm_complexity = self._llm_complexity(user_message)
            if llm_complexity is not None:
                # Promedio ponderado: 60% LLM, 40% heuristica (LLM es mas preciso)
                complexity = 0.4 * complexity + 0.6 * llm_complexity
                self._stats["llm_complexity_calls"] += 1

        # ---- Determinar tipo de consulta ----
        query_type = self._classify_query(msg_lower)

        # ---- Decidir si activar deep thinking ----
        should = complexity >= DEEP_THINKING_MIN_COMPLEXITY

        # ---- Actualizar estadisticas ----
        self._stats["total_queries"] += 1
        if should:
            self._stats["deep_think_activated"] += 1

        total = self._stats["total_queries"]
        self._stats["avg_complexity"] = (
            self._stats["avg_complexity"] * (total - 1) + complexity
        ) / total

        return should, complexity, query_type

    def _heuristic_complexity(self, msg_lower, user_message):
        """Evaluacion heuristica rapida de complejidad (sin LLM)."""
        complexity = 0.0
        high_matches = sum(1 for w in self.COMPLEXITY_INDICATORS["high"] if w in msg_lower)
        medium_matches = sum(1 for w in self.COMPLEXITY_INDICATORS["medium"] if w in msg_lower)
        simple_matches = sum(1 for w in self.COMPLEXITY_INDICATORS["simple"] if w in msg_lower)

        complexity += min(high_matches * 0.25, 0.6)
        complexity += min(medium_matches * 0.1, 0.3)
        complexity -= min(simple_matches * 0.3, 0.5)
        complexity = max(0.0, min(1.0, complexity))

        # Bonus por longitud (consultas largas suelen ser mas complejas)
        if len(user_message) > 200:
            complexity += 0.15
        elif len(user_message) > 100:
            complexity += 0.08

        # Bonus por multiples preguntas
        question_marks = msg_lower.count("?") + msg_lower.count("\u00bf")
        if question_marks >= 3:
            complexity += 0.15
        elif question_marks >= 2:
            complexity += 0.08

        # Bonus por presencia de codigo o rutas de archivo
        code_indicators = sum(1 for p in [".py", ".js", ".html", ".css", ".json", "def ", "class ", "import ", "function "] if p in msg_lower)
        if code_indicators >= 2:
            complexity += 0.15

        return max(0.0, min(1.0, complexity))

    def _llm_complexity(self, user_message):
        """
        Evaluacion de complejidad via LLM para casos ambiguos.
        Retorna un float 0-1 o None si falla.
        """
        try:
            prompt = f"""Evalua la complejidad de esta consulta del usuario en una escala de 0 a 1.
0 = consulta trivial (saludo, pregunta simple, comando directo)
0.3 = consulta moderada (una pregunta, instruccion simple)
0.5 = consulta compleja (analisis, comparacion, multiples pasos)
0.7 = consulta muy compleja (diseno, debugging, integracion)
1.0 = consulta extremadamente compleja (arquitectura, migracion, multi-sistema)

CONSULTA: {user_message}

Responde SOLO con un numero entre 0 y 1, sin explicacion."""

            response = ollama.generate_chat([
                {"role": "system", "content": "Evalua complejidad. Responde SOLO con un numero 0-1."},
                {"role": "user", "content": prompt}
            ])

            if response:
                # Extraer numero de la respuesta
                import re
                numbers = re.findall(r'[0-9]*\.?[0-9]+', response.strip())
                if numbers:
                    val = float(numbers[0])
                    return max(0.0, min(1.0, val))
        except Exception as e:
            logger.debug(f"Evaluacion LLM de complejidad fallo: {e}")
        return None

    def _classify_query(self, msg_lower):
        """Clasifica el tipo de consulta basandose en indicadores."""
        high_matches = sum(1 for w in self.COMPLEXITY_INDICATORS["high"] if w in msg_lower)
        if high_matches >= 2:
            return "analytical"
        if any(w in msg_lower for w in ["crea", "disena", "genera", "construye"]):
            return "creative"
        if any(w in msg_lower for w in ["instalar", "configurar", "ejecutar", "mover"]):
            return "procedural"
        if any(w in msg_lower for w in ["que es", "que es", "busca", "encuentra"]):
            return "factual"
        return "conversational"

    def _determine_depth(self, complexity):
        """Determina el nivel de profundidad segun la complejidad."""
        if complexity < self.DEPTH_THRESHOLDS[THINK_DEPTH_QUICK]:
            return THINK_DEPTH_NONE
        elif complexity < self.DEPTH_THRESHOLDS[THINK_DEPTH_FULL]:
            return THINK_DEPTH_QUICK
        elif complexity < self.DEPTH_THRESHOLDS[THINK_DEPTH_DEEP]:
            return THINK_DEPTH_FULL
        else:
            return THINK_DEPTH_DEEP

    # ----------------------------------------------------------
    # FASE PRINCIPAL: THINK (PRE-ReAct)
    # ----------------------------------------------------------

    def think(self, user_message, context=""):
        """
        Genera pensamiento profundo antes de actuar.

        v14.7: Soporta niveles progresivos de profundidad y
        razonamiento multi-vuelta con auto-critica.

        Args:
            user_message: Mensaje del usuario
            context: Contexto adicional (de memoria, etc.)

        Returns:
            DeepThinkingResult con el razonamiento y plan
        """
        start = time.time()

        result = DeepThinkingResult()

        should, complexity, query_type = self.should_think_deep(user_message)
        result.complexity = complexity
        result.query_type = query_type
        result.should_deep_think = should

        if not should or self.mode == "off":
            result.depth = THINK_DEPTH_NONE
            self._stats["by_depth"][THINK_DEPTH_NONE] += 1
            return result

        # Determinar nivel de profundidad
        depth = self._determine_depth(complexity)
        result.depth = depth
        self._stats["by_depth"][depth] += 1

        self._log(
            f"Deep thinking activado (complejidad={complexity:.2f}, "
            f"tipo={query_type}, profundidad={depth})"
        )

        # ---- FASE 1: Razonamiento extendido ----
        reasoning = self._generate_reasoning(user_message, context, query_type, depth)
        if reasoning:
            result.reasoning = reasoning
            result.thinking_tokens = len(reasoning.split())

        # ---- FASE 1.5: Razonamiento multi-vuelta (solo DEPTH_DEEP) ----
        if depth >= THINK_DEPTH_DEEP and self.mode in ("cot", "full"):
            reasoning, rounds = self._iterative_reasoning(
                user_message, context, reasoning, query_type
            )
            result.reasoning = reasoning
            result.thinking_tokens = len(reasoning.split())
            result.critique_rounds = rounds

        # ---- FASE 2: Think nativo del modelo (si aplica) ----
        if self.mode in ("native", "full"):
            native_thinking = self._get_native_thinking(user_message, context)
            if native_thinking:
                result.native_thinking = native_thinking
                result.thinking_tokens += len(native_thinking.split())
                self._stats["native_think_used"] += 1
                # Combinar razonamiento nativo con CoT
                if result.reasoning:
                    result.reasoning = (
                        f"{result.reasoning}\n\n"
                        f"=== RAZONAMIENTO NATIVO DEL MODELO ===\n"
                        f"{native_thinking[:DEEP_THINKING_MAX_THINKING_TOKENS]}"
                    )
                else:
                    result.reasoning = native_thinking[:DEEP_THINKING_MAX_THINKING_TOKENS]

        # ---- FASE 3: Planificacion ----
        # Generar plan para niveles FULL y DEEP
        if depth >= THINK_DEPTH_FULL:
            plan = self._generate_plan(user_message, result.reasoning, query_type)
            if plan:
                result.plan = plan
                result.confidence = self._estimate_plan_confidence(plan, user_message)
        elif depth == THINK_DEPTH_QUICK:
            # Plan simplificado para consultas moderadas
            plan = self._generate_quick_plan(user_message, result.reasoning)
            if plan:
                result.plan = plan
                result.confidence = 0.6  # Confianza fija para planes rapidos

        # ---- Respetar budget de tokens ----
        if result.thinking_tokens > DEEP_THINKING_MAX_THINKING_TOKENS:
            # Truncar razonamiento al budget
            words = result.reasoning.split()
            if len(words) > DEEP_THINKING_MAX_THINKING_TOKENS:
                result.reasoning = " ".join(words[:DEEP_THINKING_MAX_THINKING_TOKENS])
                result.thinking_tokens = DEEP_THINKING_MAX_THINKING_TOKENS
                self._log(f"Razonamiento truncado a {DEEP_THINKING_MAX_THINKING_TOKENS} tokens (budget)")

        result.duration_ms = int((time.time() - start) * 1000)
        self._log(
            f"Deep thinking completado: {result.thinking_tokens} tokens, "
            f"{len(result.plan)} pasos, profundidad={depth}, {result.duration_ms}ms"
        )

        # ---- Persistir pensamiento en memoria ----
        self._persist_thought(user_message, result)

        return result

    # ----------------------------------------------------------
    # RAZONAMIENTO
    # ----------------------------------------------------------

    def _generate_reasoning(self, user_message, context, query_type, depth):
        """
        Genera razonamiento extendido (Chain-of-Thought) antes de actuar.
        Profundidad variable segun depth.
        """
        # Ajustar prompt segun nivel de profundidad
        if depth == THINK_DEPTH_QUICK:
            analysis_steps = """1. Que quiere realmente el usuario? (intencion)
2. Que informacion necesito?"""
        elif depth == THINK_DEPTH_FULL:
            analysis_steps = """1. Que quiere realmente el usuario? (intencion profunda)
2. Que informacion necesito? (datos, archivos, estado del sistema)
3. Cuales son los posibles obstaculos? (errores comunes, dependencias)
4. Cual es la secuencia optima de acciones? (pasos ordenados)
5. Hay alternativas si el plan A falla? (plan B)"""
        else:  # THINK_DEPTH_DEEP
            analysis_steps = """1. Que quiere realmente el usuario? (intencion profunda, implicita)
2. Que informacion necesito? (datos, archivos, estado del sistema, contexto)
3. Cuales son los posibles obstaculos? (errores comunes, dependencias, edge cases)
4. Cual es la secuencia optima de acciones? (pasos ordenados con dependencias)
5. Hay alternativas si el plan A falla? (plan B y plan C)
6. Que supuestos estoy haciendo que podrian ser incorrectos? (supuestos ocultos)
7. Como puedo verificar que mi analisis es correcto? (criterios de validacion)"""

        context_part = f"\nCONTEXTO DISPONIBLE: {context[:500]}" if context else ""

        reasoning_prompt = f"""Analiza esta consulta paso a paso antes de actuar.

CONSULTA: {user_message}
TIPO: {query_type}{context_part}

PIENSA EN VOZ ALTA:
{analysis_steps}

RAZONAMIENTO:"""

        max_tokens_hint = ""
        if DEEP_THINKING_MAX_THINKING_TOKENS > 0:
            max_tokens_hint = f" Limite tu respuesta a ~{DEEP_THINKING_MAX_THINKING_TOKENS} palabras."

        try:
            reasoning = ollama.generate_chat([
                {"role": "system", "content": (
                    "Eres un sistema de razonamiento interno. "
                    "Genera analisis profundo antes de actuar. "
                    "Responde en espanol. Se estructurado y conciso."
                    f"{max_tokens_hint}"
                )},
                {"role": "user", "content": reasoning_prompt}
            ])
            return reasoning or ""
        except Exception as e:
            logger.debug(f"Generacion de razonamiento fallo: {e}")
            return ""

    def _iterative_reasoning(self, user_message, context, initial_reasoning, query_type):
        """
        Razonamiento multi-vuelta: el modelo critica y refina su propio analisis.

        Returns: (refined_reasoning: str, rounds_completed: int)
        """
        current_reasoning = initial_reasoning
        evolution = [initial_reasoning[:200]]  # Guardar evolucion para debugging

        for round_num in range(self.MAX_CRITIQUE_ROUNDS):
            critique_prompt = f"""Eres un critico interno. Analiza este razonamiento y mejoralo.

CONSULTA ORIGINAL: {user_message}
RAZONAMIENTO ACTUAL:
{current_reasoning[:800]}

CRITICA TU PROPIO ANALISIS:
1. Hay algo que no considere? (puntos ciegos)
2. Hay supuestos incorrectos? (errores de razonamiento)
3. Puedo descomponer mas algun paso? (granularidad)
4. Hay dependencias entre pasos que no vi? (orden critico)

Si el razonamiento es ya completo y correcto, responde "APROBADO".
Si necesita mejoras, proporciona el razonamiento mejorado completo.

RAZONAMIENTO MEJORADO:"""

            try:
                critique_result = ollama.generate_chat([
                    {"role": "system", "content": (
                        "Critica y mejora razonamientos. "
                        "Responde en espanol. Se riguroso."
                    )},
                    {"role": "user", "content": critique_prompt}
                ])

                if not critique_result or not critique_result.strip():
                    break

                # Si aprobo el razonamiento actual, no mejorar mas
                if critique_result.strip().startswith("APROBADO"):
                    self._log(f"Auto-critica ronda {round_num + 1}: razonamiento aprobado")
                    break

                # Si la critica es significativamente mas larga, probablemente mejoro
                if len(critique_result) > len(current_reasoning) * 0.6:
                    current_reasoning = critique_result
                    evolution.append(critique_result[:200])
                    self._log(f"Auto-critica ronda {round_num + 1}: razonamiento refinado")
                else:
                    # La critica no agrego valor suficiente, parar
                    break

            except Exception as e:
                logger.debug(f"Auto-critica ronda {round_num + 1} fallo: {e}")
                break

        return current_reasoning, len(evolution) - 1

    # ----------------------------------------------------------
    # THINK NATIVO DEL MODELO
    # ----------------------------------------------------------

    def _get_native_thinking(self, user_message, context):
        """
        Obtiene pensamiento nativo del modelo (think tags).

        WORKAROUND v14.7: Como Ollama no soporta think=True con tools,
        hacemos una llamada separada SIN tools para obtener el thinking,
        y luego inyectamos ese thinking como contexto en la llamada con tools.
        """
        try:
            # Verificar si el modelo actual soporta think nativo
            current_model = ollama.model
            if not detect_native_thinking_support(current_model):
                return ""

            # Llamada de solo razonamiento (sin tools, con think=True)
            # El thinking se genera internamente y se captura via _last_thinking
            context_part = f"\nContexto disponible: {context[:300]}" if context else ""
            think_prompt = f"""Analiza en profundidad antes de responder:
{user_message}{context_part}"""

            # Usar generate_chat con think implicito via _try_method
            # El think nativo se activa automaticamente en _try_method
            # cuando detecta un modelo compatible y NO hay tools
            response = ollama.generate_chat([
                {"role": "system", "content": (
                    "Eres un asistente que piensa profundamente antes de responder. "
                    "Responde en espanol."
                )},
                {"role": "user", "content": think_prompt}
            ])

            # El thinking nativo se guarda en ollama._last_thinking
            native_think = getattr(ollama, '_last_thinking', '')
            if native_think:
                self._log(f"Think nativo capturado: {len(native_think)} chars")
                return native_think[:DEEP_THINKING_MAX_THINKING_TOKENS]

        except Exception as e:
            logger.debug(f"Think nativo fallo: {e}")

        return ""

    # ----------------------------------------------------------
    # PLANIFICACION
    # ----------------------------------------------------------

    def _generate_plan(self, user_message, reasoning, query_type):
        """Genera un plan de accion estructurado."""
        plan_prompt = f"""Basandote en este analisis, genera un plan de accion concreto.

CONSULTA: {user_message}
RAZONAMIENTO: {reasoning[:600] if reasoning else "Sin razonamiento previo"}

Genera un plan en formato JSON con esta estructura exacta:
{{
    "steps": [
        {{"action": "descripcion de la accion", "tool": "herramienta a usar o 'responder'", "purpose": "por que este paso", "confidence": 0.8}},
        ...
    ],
    "estimated_iterations": 2,
    "fallback": "que hacer si el plan falla",
    "risks": ["posibles problemas"]
}}

PLAN:"""

        try:
            plan_text = ollama.generate_chat([
                {"role": "system", "content": (
                    "Generas planes de accion concretos. "
                    "Responde SOLO con JSON valido. "
                    "Maximo 5 pasos. Se practico."
                )},
                {"role": "user", "content": plan_prompt}
            ])

            if plan_text:
                return self._parse_plan(plan_text)

        except Exception as e:
            logger.debug(f"Generacion de plan fallo: {e}")

        return []

    def _generate_quick_plan(self, user_message, reasoning):
        """Genera un plan rapido simplificado para consultas moderadas."""
        quick_prompt = f"""Genera un plan muy breve (2-3 pasos maximo) para esta consulta.

CONSULTA: {user_message}
{f"ANALISIS: {reasoning[:200]}" if reasoning else ""}

Responde SOLO con JSON: {{"steps": [{{"action": "...", "tool": "..."}}]}}

PLAN:"""

        try:
            plan_text = ollama.generate_chat([
                {"role": "system", "content": "Generas planes breves. SOLO JSON valido. Max 3 pasos."},
                {"role": "user", "content": quick_prompt}
            ])
            if plan_text:
                return self._parse_plan(plan_text)
        except Exception as e:
            logger.debug(f"Plan rapido fallo: {e}")
        return []

    def _parse_plan(self, plan_text):
        """Parsea texto de plan a lista de pasos, con fallback robusto."""
        if not plan_text:
            return []

        # Buscar JSON en la respuesta (puede estar en code block)
        json_str = plan_text
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0]
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0]

        try:
            plan_data = json.loads(json_str.strip())
            steps = plan_data.get("steps", [])
            # Normalizar campos de cada paso
            for step in steps:
                if "confidence" not in step:
                    step["confidence"] = None
                if "purpose" not in step:
                    step["purpose"] = step.get("proposito", "auto")
            return steps[:5]
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
                            "purpose": "auto",
                            "confidence": None,
                        })
            return steps[:5]

    # ----------------------------------------------------------
    # ESTIMACION DE CONFIANZA BASADA EN CONTENIDO (Mejora 8)
    # ----------------------------------------------------------

    def _estimate_plan_confidence(self, plan, user_message=""):
        """
        Estima la confianza en el plan generado basandose en contenido,
        no solo en numero de pasos.

        Criterios:
        - Herramientas especificas mencionadas (+)
        - Propositos concretos (+)
        - Plan tiene fallback (+)
        - Pasos con confianza explicita (+)
        - Herramienta 'infer' o 'auto' (-)
        - Sin proposito (-)
        - Demasiados pasos (>5) (-)
        """
        if not plan:
            return 0.3

        score = 0.5  # Base
        n_steps = len(plan)

        # Bonus por herramientas especificas mencionadas
        specific_tools = sum(
            1 for s in plan
            if s.get("tool", "infer") not in ("infer", "auto", "responder", "")
        )
        if specific_tools >= 2:
            score += 0.15
        elif specific_tools >= 1:
            score += 0.08

        # Bonus por propositos concretos (no 'auto')
        concrete_purposes = sum(
            1 for s in plan
            if s.get("purpose", "auto") not in ("auto", "") and len(s.get("purpose", "")) > 10
        )
        if concrete_purposes >= 2:
            score += 0.1

        # Bonus por confianza explicita en pasos
        with_confidence = sum(1 for s in plan if s.get("confidence") is not None)
        if with_confidence >= n_steps * 0.5:
            avg_step_conf = sum(
                s["confidence"] for s in plan if s.get("confidence") is not None
            ) / max(with_confidence, 1)
            score += 0.1 * avg_step_conf

        # Penalizacion por herramientas inferidas
        inferred_tools = sum(1 for s in plan if s.get("tool", "") == "infer")
        if inferred_tools > n_steps * 0.5:
            score -= 0.1

        # Penalizacion por demasiados pasos
        if n_steps > 5:
            score -= 0.15
        elif n_steps == 1:
            score -= 0.05

        return max(0.1, min(1.0, score))

    # ----------------------------------------------------------
    # POST-REFLEXION (Mejora 6: con contexto de tools)
    # ----------------------------------------------------------

    def reflect(self, user_message, response, had_errors=False, tool_results=None):
        """
        Post-reflexion: evalua y potencialmente mejora la respuesta final.

        v14.7: Ahora recibe tool_results para evaluar si las herramientas
        se usaron correctamente y la informacion es adecuada.

        Args:
            user_message: Consulta original
            response: Respuesta generada
            had_errors: Si hubo errores durante la ejecucion
            tool_results: Lista de (tool_name, result_summary) de la ejecucion

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
        if not should and not had_errors and not DEEP_THINKING_REFLECT_ON_ERRORS:
            return response, False

        self._stats["reflections_triggered"] += 1
        self._log("Post-reflexion activada")

        # Construir seccion de resultados de tools (Mejora 6)
        tools_section = ""
        if tool_results:
            tools_lines = []
            for name, summary in tool_results[:5]:  # Max 5 resultados
                tools_lines.append(f"  - {name}: {summary[:150]}")
            tools_section = f"""
RESULTADOS DE HERRAMIENTAS UTILIZADAS:
{chr(10).join(tools_lines)}

Evaluacion adicional:
4. Las herramientas usadas fueron las correctas?
5. La informacion obtenida es suficiente y relevante?"""

        reflection_prompt = f"""Eres un critico interno. Evalua esta respuesta y mejorala si es necesario.

CONSULTA ORIGINAL: {user_message}

RESPUESTA GENERADA:
{response}

HUBO ERRORES DURANTE LA EJECUCION: {"Si" if had_errors else "No"}{tools_section}

EVALUA:
1. La respuesta es completa y precisa?
2. Hay informacion incorrecta o ambigua?
3. Se puede mejorar la claridad o estructura?

Si la respuesta es buena, retorna "APROBADA" seguido de la respuesta original.
Si necesita mejoras, retorna la version mejorada directamente.

RESPUESTA MEJORADA:"""

        try:
            improved = ollama.generate_chat([
                {"role": "system", "content": (
                    "Eres un critico interno que mejora respuestas. "
                    "Responde en espanol. Se conciso."
                )},
                {"role": "user", "content": reflection_prompt}
            ])

            if improved and improved.strip():
                # Si el modelo aprobo la respuesta original
                if improved.strip().startswith("APROBADA"):
                    approved = improved.replace("APROBADA", "", 1).strip()
                    return approved if approved else response, False

                # Si la mejora es significativamente mejor
                if len(improved) > len(response) * 0.7:
                    self._stats["responses_improved"] += 1
                    self._log("Respuesta mejorada via reflexion")
                    return improved, True

        except Exception as e:
            logger.debug(f"Post-reflexion fallo (no critico): {e}")

        return response, False

    # ----------------------------------------------------------
    # PERSISTENCIA DE PENSAMIENTOS (Mejora 7)
    # ----------------------------------------------------------

    def _persist_thought(self, user_message, result):
        """
        Guarda el resultado del pensamiento profundo en archivo JSON
        para que futuras consultas similares puedan beneficiarse.

        Los pensamientos se guardan en ~/.ia-local/learning/deep_thoughts.json
        """
        if not result.should_deep_think or not result.reasoning:
            return

        try:
            import os
            thoughts_file = os.path.join(LEARN_DIR, "deep_thoughts.json")

            # Cargar pensamientos existentes
            thoughts = []
            if os.path.exists(thoughts_file):
                try:
                    with open(thoughts_file, "r", encoding="utf-8") as f:
                        thoughts = json.load(f)
                except (json.JSONDecodeError, IOError):
                    thoughts = []

            # Agregar nuevo pensamiento
            thought_entry = {
                "timestamp": datetime.now().isoformat(),
                "query_preview": user_message[:100],
                "query_type": result.query_type,
                "complexity": result.complexity,
                "depth": result.depth,
                "reasoning_preview": result.reasoning[:200],
                "plan_steps": len(result.plan),
                "confidence": result.confidence,
                "duration_ms": result.duration_ms,
            }

            thoughts.append(thought_entry)

            # Mantener solo los ultimos 100 pensamientos (evitar archivo infinito)
            if len(thoughts) > 100:
                thoughts = thoughts[-100:]

            with open(thoughts_file, "w", encoding="utf-8") as f:
                json.dump(thoughts, f, ensure_ascii=False, indent=2)

            self._stats["persisted_thoughts"] += 1

        except Exception as e:
            logger.debug(f"Persistencia de pensamiento fallo: {e}")

    def get_similar_thoughts(self, user_message, limit=3):
        """
        Busca pensamientos previos similares a la consulta actual.
        Retorna lista de pensamientos relevantes.

        Usa busqueda por palabras clave (sin embeddings para velocidad).
        """
        try:
            import os
            thoughts_file = os.path.join(LEARN_DIR, "deep_thoughts.json")

            if not os.path.exists(thoughts_file):
                return []

            with open(thoughts_file, "r", encoding="utf-8") as f:
                thoughts = json.load(f)

            # Busqueda simple por palabras clave
            msg_words = set(user_message.lower().split())
            scored = []
            for thought in thoughts[-50:]:  # Solo buscar en los ultimos 50
                query_words = set(thought.get("query_preview", "").lower().split())
                overlap = len(msg_words & query_words)
                if overlap >= 2:  # Al menos 2 palabras en comun
                    scored.append((overlap, thought))

            scored.sort(key=lambda x: x[0], reverse=True)
            return [t for _, t in scored[:limit]]

        except Exception as e:
            logger.debug(f"Busqueda de pensamientos similares fallo: {e}")
            return []

    # ----------------------------------------------------------
    # PROMPT DE INYECCION
    # ----------------------------------------------------------

    def get_thinking_prompt(self, deep_result):
        """
        Genera el prompt de pensamiento profundo para inyectar en el ReAct.

        Se inyecta como contexto adicional antes de la primera iteracion.
        v14.7: Incluye nivel de profundidad y pensamientos previos similares.
        """
        if not deep_result or not deep_result.should_deep_think:
            return ""

        depth_labels = {0: "ninguno", 1: "rapido", 2: "completo", 3: "profundo"}
        depth_label = depth_labels.get(deep_result.depth, "desconocido")

        parts = [f"=== PENSAMIENTO PROFUNDO (analisis previo, nivel: {depth_label}) ==="]

        if deep_result.reasoning:
            # Truncar razonamiento segun budget
            max_chars = DEEP_THINKING_MAX_THINKING_TOKENS * 5  # ~5 chars por palabra
            parts.append(f"RAZONAMIENTO:\n{deep_result.reasoning[:max_chars]}")

        if deep_result.native_thinking and self.mode in ("native", "full"):
            parts.append(f"PENSAMIENTO INTERNO DEL MODELO:\n{deep_result.native_thinking[:300]}")

        if deep_result.plan:
            parts.append("PLAN DE ACCION:")
            for i, step in enumerate(deep_result.plan[:5], 1):
                action = step.get("action", step.get("accion", ""))
                tool = step.get("tool", step.get("herramienta", ""))
                purpose = step.get("purpose", step.get("proposito", ""))
                parts.append(f"  {i}. [{tool}] {action}")
                if purpose and purpose != "auto":
                    parts.append(f"     -> {purpose}")

        if deep_result.confidence < 0.5:
            parts.append("Baja confianza en el plan. Considera pedir aclaracion al usuario.")

        if deep_result.critique_rounds > 0:
            parts.append(f"(Razonamiento refinado via {deep_result.critique_rounds} rondas de auto-critica)")

        parts.append("=== FIN PENSAMIENTO PROFUNDO ===")
        parts.append("Usa este analisis como guia, pero adapta segun lo que descubras al ejecutar.")

        return "\n".join(parts)

    # ----------------------------------------------------------
    # UTILIDADES
    # ----------------------------------------------------------

    def _log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        logger.info(f"[{timestamp}] [DEEP_THINK] {message}")

    def stats(self):
        """Retorna estadisticas del modulo de pensamiento profundo."""
        return self._stats.copy()


# ============================================================
# FUNCIONES UTILITARIAS
# ============================================================

def detect_native_thinking_support(model_name):
    """
    Detecta si un modelo soporta pensamiento nativo (think tags).

    Modelos con soporte nativo:
    - qwen3 (cualquier variante)
    - deepseek-r1
    - qwq
    - Phi-4-reasoning
    - marco-o1

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
