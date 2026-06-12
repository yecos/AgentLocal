"""
=============================================================
AGENTE v14 - Modulo de Metacognicion
=============================================================
El agente "piensa sobre su propio pensamiento":
1. Auto-evaluacion: Que tan seguro estoy de mi plan?
2. Revision de plan: Deberia cambiar de enfoque?
3. Deteccion de bucles: Estoy repitiendo lo mismo?
4. Reflexion post-accion: Lo logre? Que aprendi?

Se integra en el bucle ReAct como un "check" entre iteraciones.
=============================================================
"""

import json
import logging
from datetime import datetime
from collections import Counter

from config import MAX_REACT_ITERATIONS, logger, UNLIMITED_TOOLS, KNOWLEDGE_CONFIDENCE_THRESHOLD


class Metacognition:
    """
    Motor de metacognicion que evalua y ajusta el comportamiento
    del agente durante el bucle ReAct.

    Conceptos clave:
    - confidence: 0.0-1.0, que tan seguro esta el agente de su camino
    - loop_detection: detecta cuando el agente esta en espiral
    - plan_revision: sugiere cambiar de estrategia si no avanza
    - reflection: post-evaluacion de resultados
    """

    # v20: Umbrales de configuracion separados
    CONFIDENCE_HIGH = 0.8       # Por encima: seguir con confianza
    KNOWLEDGE_LOW = KNOWLEDGE_CONFIDENCE_THRESHOLD  # v20: 0.4, bajo esto buscar web
    LOOP_THRESHOLD = 3          # Mismas acciones consecutivas = bucle
    STUCK_THRESHOLD = 4         # Iteraciones sin progreso = atascado
    MIN_IMPROVEMENT = 0.05      # Minima mejora esperada entre iteraciones
    SEARCH_TRIGGERED = False     # Se activo busqueda web por confianza baja?

    def __init__(self):
        self.confidence = 0.7  # Empezamos con confianza moderada (legacy compat)
        # v20: Separar execution_confidence de knowledge_confidence
        self.execution_confidence = 1.0   # Confianza en la ejecucion de herramientas
        self.knowledge_confidence = 0.7  # Confianza en el conocimiento del agente
        self.iteration_history = []  # Historial de cada iteracion
        self.tool_history = []  # Herramientas ejecutadas
        self.error_count = 0   # Errores acumulados
        self.success_count = 0 # Exitos acumulados
        self.plan_changes = 0  # Veces que se cambio de plan
        self._last_evaluation = None

    def record_iteration(self, iteration, action_type, tool_name=None,
                         result_summary=None, had_error=False,
                         error_is_knowledge=False):
        """
        Registra lo que paso en una iteracion del ReAct.
        Se llama DESPUES de cada paso Think->Act->Observe.
        
        v20: Agrega error_is_knowledge para diferenciar errores de
        ejecucion (permisos, timeout) de errores de conocimiento
        (no encontro info, resultado irrelevante).
        """
        record = {
            "iteration": iteration,
            "action_type": action_type,  # "tool_call", "respond", "error"
            "tool_name": tool_name,
            "result_summary": (result_summary or "")[:200],
            "had_error": had_error,
            "error_is_knowledge": error_is_knowledge,
            "timestamp": datetime.now().isoformat(),
        }
        self.iteration_history.append(record)

        if tool_name:
            self.tool_history.append(tool_name)

        if had_error:
            self.error_count += 1
            # v20: Bajar execution_confidence SIEMPRE, pero knowledge_confidence
            # solo si el error es de conocimiento (no info, resultado irrelevante)
            self.execution_confidence = max(0.1, self.execution_confidence - 0.15)
            if error_is_knowledge:
                self.knowledge_confidence = max(0.1, self.knowledge_confidence - 0.15)
            # Legacy compat: confidence es el minimo de ambas
            self.confidence = min(self.execution_confidence, self.knowledge_confidence)
        else:
            self.success_count += 1
            self.execution_confidence = min(1.0, self.execution_confidence + 0.05)
            self.knowledge_confidence = min(1.0, self.knowledge_confidence + 0.03)
            self.confidence = min(self.execution_confidence, self.knowledge_confidence)

        # Recalcular confianza basado en tendencia
        self._recalculate_confidence()

        logger.info(
            f"Meta: iter={iteration} action={action_type} "
            f"tool={tool_name} err={had_error} exec={self.execution_confidence:.2f} "
            f"know={self.knowledge_confidence:.2f}"
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
        v20: Retorna UNA sola razon con prioridad (no multiples contradictorias).
        Retorna: (should_revise: bool, reason: str, suggestion: str)
        """
        # v20: Prioridad 1 - Bucle detectado: cambiar enfoque
        loop_detected, loop_tool = self._detect_loop()
        if loop_detected:
            # Herramientas en UNLIMITED_TOOLS no cuentan como bucle
            if loop_tool not in UNLIMITED_TOOLS:
                reason = (
                    f"Bucle detectado: '{loop_tool}' ejecutado {self.LOOP_THRESHOLD}+ veces seguidas. "
                    f"Prueba un enfoque diferente o responde directamente al usuario."
                )
                suggestion = self._generate_suggestion(["bucle"])
                self.plan_changes += 1
                return True, reason, suggestion

        # v20: Prioridad 2 - Confianza de CONOCIMIENTO baja -> buscar web
        if self.knowledge_confidence < self.KNOWLEDGE_LOW:
            web_tools = ["buscar_web", "buscar_web_profundo", "leer_web"]
            already_searched = any(t in self.tool_history for t in web_tools)
            
            if not already_searched:
                reason = (
                    f"Confianza de conocimiento baja ({self.knowledge_confidence:.0%}). "
                    f"NO sabes suficiente para responder bien. "
                    f"DEBES usar buscar_web o buscar_web_profundo ANTES de responder. "
                    f"NUNCA respondas 'no se' sin haber buscado primero."
                )
                self.SEARCH_TRIGGERED = True
                suggestion = self._generate_suggestion(["confianza baja"])
                self.plan_changes += 1
                return True, reason, suggestion
            else:
                used_deep = "buscar_web_profundo" in self.tool_history
                if not used_deep:
                    reason = (
                        f"Confianza de conocimiento baja ({self.knowledge_confidence:.0%}) incluso despues de buscar. "
                        f"Usa buscar_web_profundo para obtener informacion mas detallada, "
                        f"o leer_web para leer una de las URLs encontradas."
                    )
                    suggestion = self._generate_suggestion(["confianza baja"])
                    self.plan_changes += 1
                    return True, reason, suggestion

        # v20: Prioridad 3 - Estancado: muchas iteraciones sin progreso
        if iteration >= self.STUCK_THRESHOLD:
            recent = self.iteration_history[-3:]
            all_errors = all(r["had_error"] for r in recent) if recent else False
            same_tool = len(set(r.get("tool_name") for r in recent if r.get("tool_name"))) == 1 if recent else False

            if all_errors or same_tool:
                reason = (
                    f"Estancado tras {iteration} iteraciones. "
                    f"Los ultimos intentos no avanzan. Considera reformular o pedir aclaracion."
                )
                suggestion = self._generate_suggestion(["estancado"])
                self.plan_changes += 1
                return True, reason, suggestion

        # v20: Prioridad 4 - Demasiados errores sin exitos
        if self.error_count >= 3 and self.success_count == 0:
            reason = (
                f"{self.error_count} errores sin exitos. "
                f"El plan actual no esta funcionando. "
                f"Reformula completamente o pide ayuda al usuario."
            )
            suggestion = self._generate_suggestion(["errores"])
            self.plan_changes += 1
            return True, reason, suggestion

        # v20: Prioridad 5 - Progreso lento cerca del limite
        remaining = MAX_REACT_ITERATIONS - iteration
        if remaining <= 2 and self.success_count < 2:
            reason = (
                f"Quedan {remaining} iteraciones y pocos exitos. "
                f"Responde con lo que tienes o pide aclaracion."
            )
            suggestion = "Responde con la informacion que tienes, aunque sea incompleta."
            self.plan_changes += 1
            return True, reason, suggestion

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
                "Si no puedes resolver con herramientas locales, BUSCA EN INTERNET con buscar_web. "
                "NUNCA te quedes atascado sin intentar buscar la solucion online."
            )

        if "estancado" in reasons_text or "atascado" in reasons_text:
            return (
                "REPLANTEA el problema desde cero. "
                "1. Que quiere realmente el usuario? "
                "2. Hay una forma mas simple de resolverlo? "
                "3. Busca en internet como hacerlo: usar buscar_web o buscar_web_profundo. "
                "4. Si ya buscaste pero no funciona, prueba leer_web con las URLs encontradas."
            )

        if "confianza baja" in reasons_text:
            # Verificar si ya se hizo busqueda web
            web_tools = ["buscar_web", "buscar_web_profundo", "leer_web"]
            already_searched = any(t in self.tool_history for t in web_tools)
            if already_searched:
                return (
                    "Ya buscaste en internet. Responde con la informacion que encontraste, "
                    "menciona las fuentes. Si aun falta informacion, usa buscar_web_profundo "
                    "o leer_web con URLs especificas."
                )
            return (
                "NO SABES lo suficiente. DEBES buscar en internet AHORA. "
                "Usa buscar_web para encontrar informacion. "
                "Si los resultados no son suficientes, usa buscar_web_profundo. "
                "NUNCA respondas sin informacion cuando puedes buscarla."
            )

        if "errores" in reasons_text:
            return (
                "DIAGNOSTICA primero. Antes de intentar de nuevo, "
                "usa leer_archivo o listar_archivos para entender el estado actual. "
                "Si no sabes como solucionar el error, BUSCA EN INTERNET: "
                "buscar_web o buscar_web_profundo para encontrar la solucion. "
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

    def get_metacognitive_prompt(self, iteration):
        """
        Genera un prompt de metacognicion para inyectar en el mensaje del sistema.
        Se agrega DENTRO del bucle ReAct cuando se detectan problemas.
        """
        should_revise, reason, suggestion = self.should_revise_plan(iteration)

        if not should_revise:
            return ""

        meta_prompt = f"""
=== ALERTA DE METACOGNICION (Iteracion {iteration + 1}) ===
Tu sistema de auto-evaluacion detecta que tu plan actual necesita ajustes.

PROBLEMA: {reason}

SUGERENCIA: {suggestion}

Confianza actual: {self.confidence:.0%}
Errores: {self.error_count} | Exitos: {self.success_count}
Herramientas usadas: {', '.join(self.tool_history[-5:]) if self.tool_history else 'ninguna'}

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

    def reset(self):
        """Resetea el estado para una nueva consulta."""
        self.confidence = 0.7
        self.execution_confidence = 1.0
        self.knowledge_confidence = 0.7
        self.iteration_history = []
        self.tool_history = []
        self.error_count = 0
        self.success_count = 0
        self.plan_changes = 0
        self._last_evaluation = None
        self.SEARCH_TRIGGERED = False

    def get_status(self):
        """Retorna el estado actual de la metacognicion (para debugging/UI)."""
        return {
            "confidence": round(self.confidence, 2),
            "errors": self.error_count,
            "successes": self.success_count,
            "plan_changes": self.plan_changes,
            "iterations": len(self.iteration_history),
            "tools_used": len(self.tool_history),
            "assessment": self._last_evaluation["assessment"] if self._last_evaluation else "pending",
        }
