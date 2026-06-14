"""
=============================================================
AGENTE v14 - Modulo de Metacognicion
=============================================================
El agente "piensa sobre su propio pensamiento":
1. Auto-evaluacion: Que tan seguro estoy de mi plan?
2. Revision de plan: Deberia cambiar de enfoque?
3. Deteccion de bucles: Estoy repitiendo lo mismo?
4. Reflexion post-accion: Lo logre? Que aprendi?

v14.8: Confidence calibration + strategy suggestion
=============================================================
"""

import json
import os
import logging
from datetime import datetime
from collections import Counter

from config import MAX_REACT_ITERATIONS, LEARN_DIR, logger


class Metacognition:
    """
    Motor de metacognicion que evalua y ajusta el comportamiento
    del agente durante el bucle ReAct.

    Conceptos clave:
    - confidence: 0.0-1.0, que tan seguro esta el agente de su camino
    - loop_detection: detecta cuando el agente esta en espiral
    - plan_revision: sugiere cambiar de estrategia si no avanza
    - reflection: post-evaluacion de resultados
    - calibration: adjusts confidence based on historical accuracy
    - strategy_suggestion: recommends strategies based on task type
    """

    # Umbrales de configuracion
    CONFIDENCE_HIGH = 0.8       # Por encima: seguir con confianza
    CONFIDENCE_LOW = 0.4        # Por debajo: considerar cambiar plan
    LOOP_THRESHOLD = 3          # Mismas acciones consecutivas = bucle
    STUCK_THRESHOLD = 4         # Iteraciones sin progreso = atascado
    MIN_IMPROVEMENT = 0.05      # Minima mejora esperada entre iteraciones

    # Strategy types for task classification
    STRATEGY_SEQUENTIAL = "sequential"   # Step-by-step tool execution
    STRATEGY_EXPLORATORY = "exploratory"  # Search and gather info first
    STRATEGY_DIRECT = "direct"           # Direct response, no tools
    STRATEGY_DECOMPOSE = "decompose"     # Break into sub-tasks

    # File path for persistent calibration data
    _CALIBRATION_FILE = os.path.join(LEARN_DIR, "confidence_calibration.json")
    _STRATEGY_FILE = os.path.join(LEARN_DIR, "strategy_performance.json")

    def __init__(self):
        self.confidence = 0.7  # Empezamos con confianza moderada
        self.iteration_history = []  # Historial de cada iteracion
        self.tool_history = []  # Herramientas ejecutadas
        self.error_count = 0   # Errores acumulados
        self.success_count = 0 # Exitos acumulados
        self.plan_changes = 0  # Veces que se cambio de plan
        self._last_evaluation = None
        
        # Confidence calibration: track how well our confidence predicts outcomes
        self._calibration_data = self._load_calibration_data()
        
        # Strategy performance tracking
        self._strategy_data = self._load_strategy_data()
        
        # Current task info for strategy suggestion
        self._current_task_type = None

    def record_iteration(self, iteration, action_type, tool_name=None,
                         result_summary=None, had_error=False,
                         error_type=None, result_quality=1.0):
        """
        Registra lo que paso en una iteracion del ReAct.
        Se llama DESPUES de cada paso Think->Act->Observe.

        M3.1: Granular confidence adjustments por tipo de error.

        Args:
            iteration: Numero de iteracion
            action_type: "tool_call", "respond", "error"
            tool_name: Nombre de la herramienta ejecutada (si aplica)
            result_summary: Resumen del resultado
            had_error: Si hubo error
            error_type: "critical" (tool no existe, error fatal) -> -0.25
                        "recoverable" (timeout, red) -> -0.05
                        "partial" (resultado incompleto) -> -0.10
                        None (error generico) -> -0.15
            result_quality: 0.0-1.0 calidad del resultado exitoso
        """
        record = {
            "iteration": iteration,
            "action_type": action_type,  # "tool_call", "respond", "error"
            "tool_name": tool_name,
            "result_summary": (result_summary or "")[:200],
            "had_error": had_error,
            "error_type": error_type,
            "result_quality": result_quality,
            "timestamp": datetime.now().isoformat(),
        }
        self.iteration_history.append(record)

        if tool_name:
            self.tool_history.append(tool_name)

        # M3.1: Granular confidence adjustment
        if had_error:
            self.error_count += 1
            if error_type == "critical":
                delta = -0.25
            elif error_type == "recoverable":
                delta = -0.05
            elif error_type == "partial":
                delta = -0.10
            else:
                delta = -0.15
            self.confidence = max(0.1, self.confidence + delta)
        else:
            self.success_count += 1
            delta = 0.05 * result_quality
            self.confidence = min(1.0, self.confidence + delta)

        # Guardar confianza en el record para _detect_progress
        record["confidence"] = round(self.confidence, 3)

        # Recalcular confianza basado en tendencia
        self._recalculate_confidence()

        logger.info(
            f"Meta: iter={iteration} action={action_type} "
            f"tool={tool_name} err={had_error} "
            f"err_type={error_type} quality={result_quality:.2f} "
            f"conf={self.confidence:.2f}"
        )

    def _recalculate_confidence(self):
        """Recalcula la confianza basado en las ultimas iteraciones."""
        if len(self.iteration_history) < 2:
            return

        # Mirar las ultimas 5 iteraciones
        recent = self.iteration_history[-5:]

        # Ratio de errores recientes
        recent_errors = sum(1 for r in recent if r["had_error"])
        error_ratio = recent_errors / len(recent)

        # Ajustar confianza por errores
        if error_ratio > 0.6:
            self.confidence = max(0.1, self.confidence - 0.1)
        elif error_ratio == 0:
            self.confidence = min(1.0, self.confidence + 0.03)

    def should_revise_plan(self, iteration):
        """
        Determina si el agente deberia reconsiderar su plan.
        Retorna: (should_revise: bool, reason: str, suggestion: str)
        """
        reasons = []

        # 1. Deteccion de bucle: misma herramienta repetida
        loop_detected, loop_tool = self._detect_loop()
        if loop_detected:
            reasons.append(
                f"Bucle detectado: '{loop_tool}' ejecutado {self.LOOP_THRESHOLD}+ veces seguidas. "
                f"Prueba un enfoque diferente o responde directamente al usuario."
            )

        # 2. Atascado: demasiadas iteraciones sin progreso
        if iteration >= self.STUCK_THRESHOLD:
            recent = self.iteration_history[-3:]
            all_errors = all(r["had_error"] for r in recent) if recent else False
            same_tool = len(set(r.get("tool_name") for r in recent if r.get("tool_name"))) == 1 if recent else False

            if all_errors or same_tool:
                reasons.append(
                    f"Estancado tras {iteration} iteraciones. "
                    f"Los ultimos intentos no avanzan. Considera reformular o pedir aclaracion."
                )

        # 3. Confianza muy baja
        if self.confidence < self.CONFIDENCE_LOW:
            reasons.append(
                f"Confianza baja ({self.confidence:.0%}). "
                f"Puede que el enfoque actual no sea el correcto. "
                f"Prueba una estrategia diferente o pide mas contexto al usuario."
            )

        # 4. Demasiados errores
        if self.error_count >= 3 and self.success_count == 0:
            reasons.append(
                f"{self.error_count} errores sin exitos. "
                f"El plan actual no esta funcionando. "
                f"Reformula completamente o pide ayuda al usuario."
            )

        # 5. Progreso lento cerca del limite
        remaining = MAX_REACT_ITERATIONS - iteration
        if remaining <= 2 and self.success_count < 2:
            reasons.append(
                f"Quedan {remaining} iteraciones y pocos exitos. "
                f"Responde con lo que tienes o pide aclaracion."
            )

        if reasons:
            combined_reason = " | ".join(reasons)
            suggestion = self._generate_suggestion(reasons)
            self.plan_changes += 1
            return True, combined_reason, suggestion

        return False, "", ""

    def _detect_loop(self):
        """Detecta si el agente esta en un bucle repitiendo la misma accion."""
        if len(self.tool_history) < self.LOOP_THRESHOLD:
            return False, None

        # Verificar las ultimas N herramientas
        recent_tools = self.tool_history[-self.LOOP_THRESHOLD:]
        if len(set(recent_tools)) == 1:
            return True, recent_tools[0]

        # Verificar patron AB-AB (alternancia sin progreso)
        if len(self.tool_history) >= 4:
            last_4 = self.tool_history[-4:]
            if last_4[0] == last_4[2] and last_4[1] == last_4[3]:
                return True, f"{last_4[0]}/{last_4[1]} (alternancia)"

        return False, None

    def _generate_suggestion(self, reasons):
        """Genera una sugerencia concreta basada en las razones para revisar."""
        reasons_text = " ".join(reasons).lower()

        if "bucle" in reasons_text:
            return (
                "CAMBIA de herramienta o estrategia. "
                "Si ejecutar_comando falla, prueba leer_archivo para entender el contexto. "
                "Si buscar_en_archivos no encuentra, prueba listar_archivos primero. "
                "Si no puedes resolver con herramientas, responde al usuario pidiendo aclaracion."
            )

        if "estancado" in reasons_text or "atascado" in reasons_text:
            return (
                "REPLANTEA el problema desde cero. "
                "1. Que quiere realmente el usuario? "
                "2. Hay una forma mas simple de resolverlo? "
                "3. Necesitas informacion adicional? Pidela."
            )

        if "confianza baja" in reasons_text:
            return (
                "SIMPLIFICA tu enfoque. En vez de pasos complejos, "
                "haz una accion directa o responde con lo que sabes. "
                "Si no estas seguro, dile al usuario que opciones ve."
            )

        if "errores" in reasons_text:
            return (
                "DIAGNOSTICA primero. Antes de intentar de nuevo, "
                "usa leer_archivo o listar_archivos para entender el estado actual. "
                "Luego ajusta tu comando basado en lo que encuentres."
            )

        return (
            "Considera cambiar de estrategia. Si el camino actual no funciona, "
            "intenta un enfoque mas simple o responde con informacion parcial."
        )

    def evaluate_result(self, user_message, final_response, iterations_used):
        """
        Post-evaluacion del resultado final del ReAct.
        Retorna un dict con la reflexion del agente sobre su propio desempeno.
        """
        reflection = {
            "iterations_used": iterations_used,
            "max_iterations": MAX_REACT_ITERATIONS,
            "efficiency": round(iterations_used / MAX_REACT_ITERATIONS, 2),
            "confidence_final": round(self.confidence, 2),
            "errors": self.error_count,
            "successes": self.success_count,
            "plan_changes": self.plan_changes,
            "tools_used": list(self.tool_history),
            "unique_tools": len(set(self.tool_history)),
            "assessment": "",
            "lessons": [],
        }

        # Auto-evaluacion cualitativa
        if iterations_used <= 2 and self.error_count == 0:
            reflection["assessment"] = "excelente"
            reflection["lessons"].append(
                "Resolucion directa y eficiente. Buen entendimiento de la peticion."
            )
        elif iterations_used <= 4 and self.error_count <= 1:
            reflection["assessment"] = "bueno"
            reflection["lessons"].append(
                "Pocos pasos necesarios. Buena seleccion de herramientas."
            )
        elif self.error_count >= 3:
            reflection["assessment"] = "problematico"
            reflection["lessons"].append(
                "Muchos errores. Verificar condiciones antes de ejecutar herramientas."
            )
        elif iterations_used >= MAX_REACT_ITERATIONS - 1:
            reflection["assessment"] = "limite_alcanzado"
            reflection["lessons"].append(
                "Se alcanzo el limite de iteraciones. Considerar descomponer la tarea."
            )
        else:
            reflection["assessment"] = "aceptable"
            if self.plan_changes > 0:
                reflection["lessons"].append(
                    "Se requirio cambio de plan. Considerar mejores estrategias iniciales."
                )

        # Leccion sobre herramientas mas usadas
        if self.tool_history:
            tool_counts = Counter(self.tool_history)
            most_used = tool_counts.most_common(1)[0]
            if most_used[1] >= 3:
                reflection["lessons"].append(
                    f"Herramienta '{most_used[0]}' usada {most_used[1]} veces. "
                    f"Considerar si hay una forma mas directa de lograr el resultado."
                )

        self._last_evaluation = reflection
        return reflection

    def get_metacognitive_prompt(self, iteration, max_iterations=None):
        """
        Genera un prompt de metacognicion para inyectar en el mensaje del sistema.
        Se agrega DENTRO del bucle ReAct cuando se detectan problemas.
        M3.3: Incorpora estrategia de escalada cuando el agente esta atascado.
        """
        should_revise, reason, suggestion = self.should_revise_plan(iteration)

        # M3.3: Verificar estrategia de escalada
        escalation = None
        if max_iterations is not None:
            escalation = self.get_escalation_strategy(iteration, max_iterations)

        if not should_revise and not escalation:
            return ""

        meta_prompt = f"""
=== ALERTA DE METACOGNICION (Iteracion {iteration + 1}) ===
Tu sistema de auto-evaluacion detecta que tu plan actual necesita ajustes.

PROBLEMA: {reason}

SUGERENCIA: {suggestion}

Confianza actual: {self.confidence:.0%}
Errores: {self.error_count} | Exitos: {self.success_count}
Herramientas usadas: {', '.join(self.tool_history[-5:]) if self.tool_history else 'ninguna'}
"""

        # M3.3: Agregar estrategia de escalada si existe
        if escalation:
            meta_prompt += f"""
ESCALADA ({escalation['strategy']}): {escalation['reason']}
ACCION: {escalation['action']}
"""

        meta_prompt += """
ACCION REQUERIDA: Cambia tu estrategia. No repitas lo mismo.
=== FIN ALERTA ===
"""
        return meta_prompt

    def get_final_reflection_prompt(self):
        """
        Genera un prompt para reflexion final (post-evaluacion).
        Se inyecta cuando el agente esta por dar su respuesta final.
        """
        if not self._last_evaluation:
            return ""

        eval_data = self._last_evaluation
        if eval_data["assessment"] in ("excelente", "bueno"):
            return ""

        lessons = "\n".join(f"- {l}" for l in eval_data["lessons"][:3])
        return f"""
NOTA INTERNA: Tu proceso tuvo problemas ({eval_data['assessment']}).
Errores: {eval_data['errors']}, Cambios de plan: {eval_data['plan_changes']}.
Lecciones: {lessons}
Si tu respuesta es incompleta, mencionalo y sugiere que puede hacer el usuario.
"""

    # ----------------------------------------------------------
    # M3.2: DETECCION DE PROGRESO REAL
    # ----------------------------------------------------------

    def _detect_progress(self, user_message: str = "") -> str:
        """
        M3.2: Detecta si el agente esta progresando, atascado o degradando.

        Returns:
            "progressing" - El agente avanza normalmente
            "stuck_same_tool" - Misma herramienta repetida 3+ veces sin exito
            "degrading" - Ultimas 3 iteraciones con errores
            "declining" - Confianza descendiendo consistentemente
        """
        # Mismo tool llamado 3 veces seguidas = stuck
        if len(self.tool_history) >= 3:
            last_3 = self.tool_history[-3:]
            if len(set(last_3)) == 1:
                return "stuck_same_tool"

        # Ultimas 3 iteraciones todas con error = degrading
        if len(self.iteration_history) >= 3:
            recent_errors = sum(
                1 for r in self.iteration_history[-3:] if r.get("had_error")
            )
            if recent_errors >= 3:
                return "degrading"

        # Confianza descendiendo consistentemente (4+ iteraciones)
        if len(self.iteration_history) >= 4:
            recent_confidences = [
                r.get("confidence", 1.0)
                for r in self.iteration_history[-4:]
            ]
            if all(
                recent_confidences[i] > recent_confidences[i + 1]
                for i in range(len(recent_confidences) - 1)
            ):
                return "declining"

        return "progressing"

    # ----------------------------------------------------------
    # M3.3: ESTRATEGIA DE ESCALADA
    # ----------------------------------------------------------

    def get_escalation_strategy(self, iteration: int, max_iterations: int) -> dict | None:
        """
        M3.3: Retorna estrategia de escalada cuando el agente esta atascado.

        4 niveles de escalada progresiva:
          NIVEL 1 (iteration ~3, stuck): Cambiar parametros de la misma herramienta
          NIVEL 2 (iteration ~4, stuck): Usar herramienta alternativa
          NIVEL 3 (iteration ~5, stuck): Dividir la tarea en subtareas
          NIVEL 4 (iteration ~6+, stuck): Pedir clarificacion al usuario

        Args:
            iteration: Iteracion actual
            max_iterations: Maximo de iteraciones permitidas

        Returns:
            dict con strategy/reason/action o None si esta progresando
        """
        progress = self._detect_progress()

        if progress == "progressing":
            return None

        # NIVEL 1: Cambiar parametros (stuck pero temprano)
        if progress == "stuck_same_tool" and iteration <= 3:
            return {
                "strategy": "change_params",
                "reason": "Misma herramienta repetida sin exito, variar parametros",
                "action": "Cambia los parametros de la herramienta actual (consulta, filtro, formato)"
            }

        # NIVEL 2: Usar herramienta alternativa (stuck despues de intento 1)
        if progress == "stuck_same_tool" and iteration > 3:
            return {
                "strategy": "alternative_tool",
                "reason": "Misma herramienta sigue fallando, cambiar a alternativa",
                "action": "Usa una herramienta diferente que cumpla la misma funcion"
            }

        # NIVEL 3: Descomponer tarea (errores acumulados, >60% de iteraciones)
        if progress in ("degrading", "declining") and iteration >= max_iterations * 0.6:
            return {
                "strategy": "decompose",
                "reason": "Errores acumulados, descomponer tarea en partes mas simples",
                "action": "Divide la tarea en subtareas mas simples y ejecutalas una por una"
            }

        # NIVEL 4: Pedir ayuda al usuario (ya intentaste todo, >80% de iteraciones)
        if progress in ("degrading", "declining", "stuck_same_tool") and iteration >= max_iterations * 0.8:
            return {
                "strategy": "ask_user",
                "reason": "No se puede progresar automaticamente despues de multiples intentos",
                "action": "Pide clarificacion o ayuda al usuario explicando que se intento"
            }

        return None

    def reset(self):
        """Resetea el estado para una nueva consulta."""
        self.confidence = 0.7
        self.iteration_history = []
        self.tool_history = []
        self.error_count = 0
        self.success_count = 0
        self.plan_changes = 0
        self._last_evaluation = None
        self._current_task_type = None

    def get_status(self):
        """Retorna el estado actual de la metacognicion (para debugging/UI)."""
        return {
            "confidence": round(self.confidence, 2),
            "calibrated_confidence": round(self.get_calibrated_confidence(), 2),
            "calibration_offset": round(self._calibration_data.get("offset", 0.0), 3),
            "errors": self.error_count,
            "successes": self.success_count,
            "plan_changes": self.plan_changes,
            "iterations": len(self.iteration_history),
            "tools_used": len(self.tool_history),
            "assessment": self._last_evaluation["assessment"] if self._last_evaluation else "pending",
            "suggested_strategy": self._current_task_type or "auto",
            "progress": self._detect_progress(),
        }

    # ----------------------------------------------------------
    # CONFIDENCE CALIBRATION
    # ----------------------------------------------------------
    def _load_calibration_data(self):
        """Load historical calibration data from persistent storage."""
        try:
            if os.path.exists(self._CALIBRATION_FILE):
                with open(self._CALIBRATION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Validate expected keys
                    if "records" in data and isinstance(data["records"], list):
                        return data
        except Exception as e:
            logger.debug(f"Error loading calibration data: {e}")
        return {"records": [], "offset": 0.0, "total_samples": 0}

    def _save_calibration_data(self):
        """Persist calibration data to disk."""
        try:
            with open(self._CALIBRATION_FILE, "w", encoding="utf-8") as f:
                json.dump(self._calibration_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Error saving calibration data: {e}")

    def record_calibration_sample(self, confidence_before, actual_success):
        """
        Record a calibration sample: confidence before action vs actual outcome.
        
        Args:
            confidence_before: Confidence score (0-1) before the action was taken
            actual_success: Whether the action actually succeeded (bool)
        """
        record = {
            "confidence": round(confidence_before, 2),
            "outcome": 1.0 if actual_success else 0.0,
            "timestamp": datetime.now().isoformat(),
        }
        
        # Keep last 200 samples for rolling calibration
        records = self._calibration_data["records"]
        records.append(record)
        if len(records) > 200:
            records[:] = records[-200:]
        
        # Recalculate calibration offset
        self._recalculate_calibration_offset()
        self._save_calibration_data()
        
        logger.info(
            f"Calibration sample: confidence={confidence_before:.2f} "
            f"outcome={'success' if actual_success else 'failure'} "
            f"offset={self._calibration_data['offset']:.3f}"
        )

    def _recalculate_calibration_offset(self):
        """
        Recalculate the calibration offset based on historical data.
        
        The offset is the difference between predicted confidence and actual
        success rate. If we're consistently overconfident (confidence > success),
        offset is negative. If underconfident, offset is positive.
        """
        records = self._calibration_data["records"]
        if not records:
            return
        
        # Calculate average predicted confidence vs actual success rate
        recent = records[-50:]  # Use last 50 samples
        avg_confidence = sum(r["confidence"] for r in recent) / len(recent)
        avg_outcome = sum(r["outcome"] for r in recent) / len(recent)
        
        # Offset to add to future confidence estimates
        # If overconfident (avg_confidence > avg_outcome), offset is negative
        offset = avg_outcome - avg_confidence
        
        # Weight new offset with existing (exponential moving average)
        alpha = 0.3  # Learning rate
        old_offset = self._calibration_data.get("offset", 0.0)
        self._calibration_data["offset"] = round(old_offset * (1 - alpha) + offset * alpha, 4)
        self._calibration_data["total_samples"] = len(records)

    def get_calibrated_confidence(self):
        """
        Get the confidence score adjusted by historical calibration.
        
        Returns:
            Calibrated confidence (0.0-1.0)
        """
        offset = self._calibration_data.get("offset", 0.0)
        total_samples = self._calibration_data.get("total_samples", 0)
        
        if total_samples < 5:
            # Not enough data for calibration - use raw confidence
            return self.confidence
        
        calibrated = self.confidence + offset
        return max(0.0, min(1.0, calibrated))

    # ----------------------------------------------------------
    # STRATEGY SUGGESTION
    # ----------------------------------------------------------
    def _load_strategy_data(self):
        """Load historical strategy performance data."""
        try:
            if os.path.exists(self._STRATEGY_FILE):
                with open(self._STRATEGY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "task_types" in data:
                        return data
        except Exception as e:
            logger.debug(f"Error loading strategy data: {e}")
        return {"task_types": {}}

    def _save_strategy_data(self):
        """Persist strategy performance data to disk."""
        try:
            with open(self._STRATEGY_FILE, "w", encoding="utf-8") as f:
                json.dump(self._strategy_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Error saving strategy data: {e}")

    def classify_task_type(self, user_message):
        """
        Classify the type of task based on the user message.
        
        Returns one of: "code", "search", "file_operation", "conversation", "system", "multi_step"
        """
        msg_lower = user_message.lower()
        
        # Code-related tasks
        code_indicators = [
            "codigo", "code", "programa", "script", "funcion", "function",
            "genera", "crea un", "desarrolla", "implementa", "python", "javascript",
            "html", "css", "api", "debug", "depura", "refactor", "compila"
        ]
        if any(ind in msg_lower for ind in code_indicators):
            self._current_task_type = "code"
            return "code"
        
        # Search/information tasks
        search_indicators = [
            "busca", "search", "encuentra", "informa", "que es", "what is",
            "quien", "donde", "cuando", "como se", "investiga", "wikipedia",
            "internet", "web"
        ]
        if any(ind in msg_lower for ind in search_indicators):
            self._current_task_type = "search"
            return "search"
        
        # File operations
        file_indicators = [
            "archivo", "file", "leer", "read", "escribir", "write",
            "listar", "directorio", "carpeta", "folder", "documento",
            "pdf", "docx", "xlsx", "csv"
        ]
        if any(ind in msg_lower for ind in file_indicators):
            self._current_task_type = "file_operation"
            return "file_operation"
        
        # System operations
        system_indicators = [
            "ejecuta", "command", "comando", "terminal", "consola",
            "instala", "install", "proceso", "docker", "git", "servidor"
        ]
        if any(ind in msg_lower for ind in system_indicators):
            self._current_task_type = "system"
            return "system"
        
        # Multi-step tasks (longer, more complex requests)
        if len(user_message) > 150 or "," in msg_lower and any(
            w in msg_lower for w in [" y ", " y luego ", " entonces ", " despues ", " and ", " then "]
        ):
            self._current_task_type = "multi_step"
            return "multi_step"
        
        # Default: conversation
        self._current_task_type = "conversation"
        return "conversation"

    def suggest_strategy(self, user_message):
        """
        Suggest the best strategy for the given task.
        
        Based on task type and past performance of strategies, returns
        the recommended approach.
        
        Args:
            user_message: The user's message/task
        
        Returns:
            dict with keys:
                - strategy: one of STRATEGY_SEQUENTIAL, STRATEGY_EXPLORATORY, etc.
                - reason: why this strategy is recommended
                - confidence: confidence in this recommendation
        """
        task_type = self.classify_task_type(user_message)
        
        # Strategy mapping by task type
        default_strategies = {
            "code": (self.STRATEGY_SEQUENTIAL, "Code tasks benefit from step-by-step execution"),
            "search": (self.STRATEGY_EXPLORATORY, "Search tasks need exploration before responding"),
            "file_operation": (self.STRATEGY_SEQUENTIAL, "File operations are sequential by nature"),
            "conversation": (self.STRATEGY_DIRECT, "Conversational tasks usually need direct responses"),
            "system": (self.STRATEGY_SEQUENTIAL, "System commands should be executed step by step"),
            "multi_step": (self.STRATEGY_DECOMPOSE, "Complex tasks benefit from decomposition"),
        }
        
        # Check if we have historical performance data for this task type
        task_perf = self._strategy_data["task_types"].get(task_type, {})
        best_strategy = None
        best_score = -1
        
        for strategy_name, perf in task_perf.items():
            if isinstance(perf, dict) and perf.get("count", 0) >= 3:
                # Only consider strategies with enough samples
                score = perf.get("success_rate", 0)
                if score > best_score:
                    best_score = score
                    best_strategy = strategy_name
        
        # Use historical best if available, otherwise use default
        if best_strategy and best_score > 0.5:
            reason = f"Historical data shows {best_strategy} works best for {task_type} tasks (success: {best_score:.0%})"
            confidence = min(0.9, best_score)
        else:
            strategy, reason = default_strategies.get(
                task_type, (self.STRATEGY_SEQUENTIAL, "Default sequential strategy")
            )
            best_strategy = strategy
            confidence = 0.5
        
        return {
            "strategy": best_strategy,
            "task_type": task_type,
            "reason": reason,
            "confidence": confidence,
        }

    def record_strategy_outcome(self, task_type, strategy, success, iterations_used):
        """
        Record the outcome of using a particular strategy for a task type.
        
        Args:
            task_type: The classified task type
            strategy: The strategy that was used
            success: Whether the task completed successfully
            iterations_used: Number of iterations used
        """
        if task_type not in self._strategy_data["task_types"]:
            self._strategy_data["task_types"][task_type] = {}
        
        task_strategies = self._strategy_data["task_types"][task_type]
        
        if strategy not in task_strategies:
            task_strategies[strategy] = {
                "count": 0,
                "successes": 0,
                "success_rate": 0.0,
                "avg_iterations": 0.0,
            }
        
        entry = task_strategies[strategy]
        entry["count"] += 1
        if success:
            entry["successes"] += 1
        
        # Update rolling success rate
        entry["success_rate"] = round(entry["successes"] / entry["count"], 3)
        
        # Update average iterations (exponential moving average)
        alpha = 0.3
        old_avg = entry.get("avg_iterations", iterations_used)
        entry["avg_iterations"] = round(old_avg * (1 - alpha) + iterations_used * alpha, 2)
        
        self._save_strategy_data()
        
        logger.info(
            f"Strategy outcome: task_type={task_type} strategy={strategy} "
            f"success={success} iterations={iterations_used} "
            f"success_rate={entry['success_rate']:.2f}"
        )
