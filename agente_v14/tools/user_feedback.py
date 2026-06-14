"""
=============================================================
AGENTE v14 - User Feedback System
=============================================================
Sistema de seguimiento de feedback de usuarios (thumbs up/down,
ratings) sobre las respuestas del agente para mejorar el
comportamiento futuro.

Flujo:
1. Usuario da feedback sobre una respuesta del agente
2. Se registra el feedback con tipo, detalles, herramienta, etc.
3. Se actualizan estadisticas en tiempo real
4. Se detectan patrones negativos recurrentes
5. Se genera un prompt de mejora que se inyecta en el sistema
6. Se sugieren ajustes de comportamiento cuando es necesario

v14: Aprendizaje continuo basado en feedback del usuario.
=============================================================
"""

import os
import json
import csv
import io
import threading
import uuid
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

from config import LEARN_DIR, logger

# ============================================================
# CONSTANTES
# ============================================================

MAX_FEEDBACK_ENTRIES = 1000  # FIFO: mantener solo las ultimas 1000 entradas

FEEDBACK_FILE = os.path.join(LEARN_DIR, "feedback.json")

VALID_FEEDBACK_TYPES = {"thumbs_up", "thumbs_down", "rating", "correction"}

# Mapeo de patrones negativos a sugerencias
NEGATIVE_PATTERN_SUGGESTIONS = {
    "codigo_incorrecto": "Mejorar verificacion de codigo antes de responder",
    "codigo_sin_ejecutar": "SIEMPRE ejecuta codigo despues de generarlo para verificar que funciona",
    "respuesta_lenta": "Usar modelo mas rapido o simplificar la respuesta",
    "respuesta_incompleta": "Proporcionar respuestas mas completas y detalladas",
    "respuesta_demasiado_larga": "Ser mas conciso y directo en las respuestas",
    "respuesta_demasiado_corta": "Ser mas detallado y explicativo en las respuestas",
    "busqueda_superficial": "Realizar busquedas mas profundas y verificar multiples fuentes",
    "error_en_comando": "Verificar comandos antes de ejecutarlos",
    "informacion_incorrecta": "Verificar la exactitud de la informacion antes de responder",
    "no_sigue_instrucciones": "Leer cuidadosamente las instrucciones del usuario antes de actuar",
    "formato_incorrecto": "Prestar atencion al formato solicitado por el usuario",
}


# ============================================================
# CLASE PRINCIPAL
# ============================================================

class UserFeedbackTracker:
    """
    Registra y analiza el feedback del usuario sobre las respuestas
    del agente para mejorar el comportamiento futuro.

    Thread-safe: todas las operaciones de escritura estan protegidas
    con un lock para evitar corrupcion de datos.
    """

    def __init__(self):
        """Inicializa el tracker, carga historial y contadores."""
        self._lock = threading.RLock()
        self._feedback_file = FEEDBACK_FILE

        # Asegurar que el directorio existe
        os.makedirs(os.path.dirname(self._feedback_file), exist_ok=True)

        # Historial de feedback (lista de dicts)
        self._history: list[dict] = []

        # Contadores rapidos (derivados del historial)
        self._counters = {
            "total_feedback": 0,
            "thumbs_up": 0,
            "thumbs_down": 0,
            "rating_sum": 0.0,
            "rating_count": 0,
            "by_tool": defaultdict(lambda: {"positive": 0, "negative": 0}),
            "by_category": defaultdict(lambda: {"positive": 0, "negative": 0}),
        }

        # Cargar historial existente
        self._load_history()
        # Recalcular contadores desde el historial cargado
        self._recompute_counters()

        logger.info(f"[FeedbackTracker] Inicializado con {len(self._history)} entradas de feedback")

    # ============================================================
    # METODOS PUBLICOS
    # ============================================================

    def record_feedback(self, message_id: str, feedback_type: str, details: Optional[dict] = None) -> dict:
        """
        Registra feedback para un mensaje especifico.

        Args:
            message_id: Identificador del mensaje evaluado
            feedback_type: Tipo de feedback ("thumbs_up", "thumbs_down", "rating", "correction")
            details: Dict opcional con:
                - "rating" (1-5): puntuacion numerica
                - "comment": comentario del usuario
                - "correction": texto de correccion del usuario
                - "tool_name": nombre de la herramienta usada
                - "category": categoria de la respuesta
                - "response_length": longitud de la respuesta en caracteres

        Returns:
            {"success": True, "feedback_id": "..."} o {"success": False, "error": "..."}
        """
        # Validar tipo de feedback
        if feedback_type not in VALID_FEEDBACK_TYPES:
            error_msg = f"Tipo de feedback invalido: {feedback_type}. Validos: {VALID_FEEDBACK_TYPES}"
            logger.warning(f"[FeedbackTracker] {error_msg}")
            return {"success": False, "error": error_msg}

        # Validar rating si viene
        details = details or {}
        if feedback_type == "rating":
            rating = details.get("rating")
            if rating is None or not (1 <= rating <= 5):
                error_msg = f"Rating debe estar entre 1 y 5, recibido: {rating}"
                logger.warning(f"[FeedbackTracker] {error_msg}")
                return {"success": False, "error": error_msg}

        # Crear entrada de feedback
        feedback_id = str(uuid.uuid4())[:8]
        entry = {
            "feedback_id": feedback_id,
            "message_id": message_id,
            "feedback_type": feedback_type,
            "details": details,
            "timestamp": datetime.now().isoformat(),
        }

        with self._lock:
            self._history.append(entry)

            # FIFO: mantener solo las ultimas MAX_FEEDBACK_ENTRIES
            if len(self._history) > MAX_FEEDBACK_ENTRIES:
                removed = self._history[: len(self._history) - MAX_FEEDBACK_ENTRIES]
                self._history = self._history[-MAX_FEEDBACK_ENTRIES:]
                # Necesitamos recalcular porque eliminamos entradas
                self._recompute_counters()
            else:
                # Actualizacion incremental de contadores
                self._update_counters_incremental(entry)

            # Auto-guardar
            self._save_history()

        logger.info(
            f"[FeedbackTracker] Feedback registrado: id={feedback_id}, "
            f"type={feedback_type}, message={message_id}"
        )

        return {"success": True, "feedback_id": feedback_id}

    def get_feedback_stats(self) -> dict:
        """
        Retorna estadisticas generales del feedback.

        Returns:
            Dict con:
                - total_feedback: int
                - thumbs_up: int
                - thumbs_down: int
                - avg_rating: float
                - recent_trend: "improving" | "declining" | "stable"
                - by_tool: dict de tool_name -> {positive, negative}
                - by_category: dict de category -> {positive, negative}
        """
        with self._lock:
            # Copia profunda de contadores para evitar mutaciones externas
            by_tool = {k: dict(v) for k, v in self._counters["by_tool"].items()}
            by_category = {k: dict(v) for k, v in self._counters["by_category"].items()}

            avg_rating = 0.0
            if self._counters["rating_count"] > 0:
                avg_rating = round(
                    self._counters["rating_sum"] / self._counters["rating_count"], 2
                )

            recent_trend = self._compute_recent_trend()

            return {
                "total_feedback": self._counters["total_feedback"],
                "thumbs_up": self._counters["thumbs_up"],
                "thumbs_down": self._counters["thumbs_down"],
                "avg_rating": avg_rating,
                "recent_trend": recent_trend,
                "by_tool": by_tool,
                "by_category": by_category,
            }

    def get_negative_patterns(self) -> list[dict]:
        """
        Analiza el feedback negativo para encontrar patrones recurrentes.

        Detecta:
        - Herramientas con alto porcentaje de feedback negativo
        - Tipos de error frecuentes (codigo incorrecto, respuestas lentas, etc.)
        - Caracteristicas de respuestas que generan insatisfaccion

        Returns:
            Lista de patrones detectados, cada uno con:
                - pattern: nombre del patron
                - count: ocurrencias
                - tools: herramientas asociadas
                - suggestion: sugerencia de mejora
        """
        with self._lock:
            if not self._history:
                return []

            patterns_found: list[dict] = []

            # 1. Patrones por herramienta con alto feedback negativo
            tool_negatives: dict[str, list[dict]] = defaultdict(list)
            for entry in self._history:
                if self._is_negative_entry(entry):
                    tool_name = entry.get("details", {}).get("tool_name")
                    if tool_name:
                        tool_negatives[tool_name].append(entry)

            for tool_name, neg_entries in tool_negatives.items():
                # Contar total de feedback para esta herramienta
                tool_total = sum(
                    1 for e in self._history
                    if e.get("details", {}).get("tool_name") == tool_name
                )
                if tool_total == 0:
                    continue
                neg_ratio = len(neg_entries) / tool_total

                if neg_ratio > 0.4 and len(neg_entries) >= 2:
                    # Determinar sub-patron basado en la herramienta
                    pattern_name = self._infer_tool_pattern(tool_name, neg_entries)
                    patterns_found.append({
                        "pattern": pattern_name,
                        "count": len(neg_entries),
                        "tools": [tool_name],
                        "suggestion": NEGATIVE_PATTERN_SUGGESTIONS.get(
                            pattern_name, f"Revisar uso de {tool_name}"
                        ),
                    })

            # 2. Patrones por tipo de correccion
            correction_patterns: dict[str, list[dict]] = defaultdict(list)
            for entry in self._history:
                if entry.get("feedback_type") == "correction":
                    correction = entry.get("details", {}).get("correction", "")
                    pattern = self._classify_correction(correction)
                    if pattern:
                        tool_name = entry.get("details", {}).get("tool_name")
                        correction_patterns[pattern].append({
                            "entry": entry,
                            "tool": tool_name,
                        })

            for pattern_name, items in correction_patterns.items():
                if len(items) >= 2:
                    tools = list(set(it["tool"] for it in items if it["tool"]))
                    patterns_found.append({
                        "pattern": pattern_name,
                        "count": len(items),
                        "tools": tools,
                        "suggestion": NEGATIVE_PATTERN_SUGGESTIONS.get(
                            pattern_name, f"Mejorar manejo de {pattern_name}"
                        ),
                    })

            # 3. Patrones por longitud de respuesta
            length_pattern = self._detect_length_pattern()
            if length_pattern:
                patterns_found.append(length_pattern)

            # 4. Patrones por rating bajo
            low_rating_pattern = self._detect_low_rating_pattern()
            if low_rating_pattern:
                # Evitar duplicado si ya hay un patron similar
                existing_patterns = {p["pattern"] for p in patterns_found}
                if low_rating_pattern["pattern"] not in existing_patterns:
                    patterns_found.append(low_rating_pattern)

            # Ordenar por count descendente
            patterns_found.sort(key=lambda p: p["count"], reverse=True)

            return patterns_found

    def get_improvement_prompt(self) -> str:
        """
        Genera un fragmento de prompt basado en los patrones de feedback
        que se inyecta en el system prompt del agente para mejorar su
        comportamiento.

        Este es el METODO CLAVE: traduce feedback crudo en instrucciones
        accionables para el agente.

        Returns:
            String con instrucciones de mejora, o cadena vacia si no hay
            patrones significativos.
        """
        patterns = self.get_negative_patterns()
        stats = self.get_feedback_stats()

        if not patterns and stats["total_feedback"] < 5:
            # No hay suficiente data para generar mejoras
            return ""

        instructions: list[str] = []

        # Encabezado contextual
        total = stats["total_feedback"]
        thumbs_down = stats["thumbs_down"]
        if total > 0 and thumbs_down > 0:
            neg_pct = round(thumbs_down / total * 100, 1)
            instructions.append(
                f"Historial de feedback: {neg_pct}% de respuestas negativas "
                f"({thumbs_down} de {total})."
            )

        # Generar instrucciones por cada patron detectado
        for pattern in patterns:
            instruction = self._pattern_to_instruction(pattern)
            if instruction:
                instructions.append(instruction)

        # Ajustes basados en tendencia reciente
        trend = stats["recent_trend"]
        if trend == "declining":
            instructions.append(
                "Tu calidad de respuesta esta disminuyendo recientemente. "
                "Toma mas tiempo para analizar las peticiones y verificar tus respuestas "
                "antes de enviarlas."
            )
        elif trend == "improving":
            instructions.append(
                "Tu calidad de respuesta esta mejorando. Continua con el enfoque actual."
            )

        # Ajuste basado en rating promedio
        avg_rating = stats["avg_rating"]
        if avg_rating > 0 and avg_rating < 3.0:
            instructions.append(
                "Tu rating promedio es bajo. Enfocate en dar respuestas mas precisas, "
                "verificar la informacion y seguir las instrucciones del usuario al pie de la letra."
            )

        if not instructions:
            return ""

        # Construir prompt final
        prompt = "\n\n[INSTRUCCIONES DE MEJORA BASADAS EN FEEDBACK]\n"
        prompt += "Los usuarios han dado feedback sobre tus respuestas. Ajusta tu comportamiento:\n\n"
        for i, instruction in enumerate(instructions, 1):
            prompt += f"{i}. {instruction}\n"
        prompt += "\nEstas instrucciones son PRIORIDAD. Inclinalas en cada respuesta."

        return prompt

    def should_adjust_behavior(self, tool_name: Optional[str] = None) -> dict:
        """
        Determina si el agente deberia ajustar su comportamiento basandose
        en el feedback reciente.

        Criterios:
        - Si una herramienta tiene >60% feedback negativo: sugerir alternativas
        - Si la calidad esta declinando: sugerir enfoque mas cuidadoso
        - Si un patron es muy frecuente: sugerir cambio especifico

        Args:
            tool_name: Nombre de herramienta opcional para evaluar especificamente

        Returns:
            {"adjust": True/False, "suggestions": [...], "confidence": 0.0-1.0}
        """
        with self._lock:
            suggestions: list[str] = []
            confidence_factors: list[float] = []

            stats = self.get_feedback_stats()

            # 1. Evaluar herramienta especifica
            if tool_name:
                tool_stats = stats["by_tool"].get(tool_name)
                if tool_stats:
                    total_tool = tool_stats["positive"] + tool_stats["negative"]
                    if total_tool >= 3:
                        neg_ratio = tool_stats["negative"] / total_tool
                        if neg_ratio > 0.6:
                            suggestions.append(
                                f"La herramienta '{tool_name}' tiene {round(neg_ratio*100)}% "
                                f"de feedback negativo. Considera usar una herramienta alternativa "
                                f"o cambiar el enfoque."
                            )
                            confidence_factors.append(min(neg_ratio, 0.95))

            # 2. Evaluar tendencia general
            if stats["recent_trend"] == "declining":
                suggestions.append(
                    "La calidad de las respuestas esta disminuyendo. "
                    "Adopta un enfoque mas cuidadoso: analiza mas antes de actuar, "
                    "verifica resultados y proporciona respuestas mas detalladas."
                )
                confidence_factors.append(0.7)

            # 3. Evaluar patrones negativos frecuentes
            patterns = self.get_negative_patterns()
            for pattern in patterns[:3]:  # Top 3 patrones
                if pattern["count"] >= 3:
                    suggestions.append(
                        f"Patron detectado: '{pattern['pattern']}' ({pattern['count']} veces). "
                        f"Sugerencia: {pattern['suggestion']}"
                    )
                    confidence_factors.append(min(pattern["count"] / 10, 0.85))

            # 4. Evaluar rating promedio
            avg_rating = stats["avg_rating"]
            if avg_rating > 0 and avg_rating < 2.5:
                suggestions.append(
                    "El rating promedio es muy bajo. Prioriza la calidad sobre la velocidad."
                )
                confidence_factors.append(0.8)

            # Calcular confianza global
            if confidence_factors:
                confidence = round(
                    sum(confidence_factors) / len(confidence_factors), 2
                )
            else:
                confidence = 0.0

            adjust = len(suggestions) > 0

            return {
                "adjust": adjust,
                "suggestions": suggestions,
                "confidence": confidence,
            }

    def export_feedback(self, format: str = "json") -> str:
        """
        Exporta todos los datos de feedback para analisis externo.

        Args:
            format: "json" o "csv"

        Returns:
            String con los datos en el formato solicitado
        """
        with self._lock:
            if format == "json":
                export_data = {
                    "exported_at": datetime.now().isoformat(),
                    "total_entries": len(self._history),
                    "stats": self.get_feedback_stats(),
                    "entries": self._history,
                }
                return json.dumps(export_data, indent=2, ensure_ascii=False)

            elif format == "csv":
                output = io.StringIO()
                if not self._history:
                    return ""

                # Determinar columnas a partir de la primera entrada
                fieldnames = [
                    "feedback_id", "message_id", "feedback_type", "timestamp",
                    "rating", "comment", "correction", "tool_name", "category",
                    "response_length",
                ]
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()

                for entry in self._history:
                    details = entry.get("details", {})
                    row = {
                        "feedback_id": entry.get("feedback_id", ""),
                        "message_id": entry.get("message_id", ""),
                        "feedback_type": entry.get("feedback_type", ""),
                        "timestamp": entry.get("timestamp", ""),
                        "rating": details.get("rating", ""),
                        "comment": details.get("comment", ""),
                        "correction": details.get("correction", ""),
                        "tool_name": details.get("tool_name", ""),
                        "category": details.get("category", ""),
                        "response_length": details.get("response_length", ""),
                    }
                    writer.writerow(row)

                return output.getvalue()

            else:
                logger.warning(f"[FeedbackTracker] Formato de exportacion no soportado: {format}")
                return json.dumps(
                    {"error": f"Formato no soportado: {format}. Use 'json' o 'csv'."},
                    ensure_ascii=False,
                )

    # ============================================================
    # METODOS PRIVADOS - PERSISTENCIA
    # ============================================================

    def _load_history(self):
        """Carga el historial de feedback desde el archivo JSON."""
        try:
            if os.path.exists(self._feedback_file):
                with open(self._feedback_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._history = data[-MAX_FEEDBACK_ENTRIES:]
                    elif isinstance(data, dict) and "entries" in data:
                        self._history = data["entries"][-MAX_FEEDBACK_ENTRIES:]
                    else:
                        self._history = []
                logger.info(f"[FeedbackTracker] Cargadas {len(self._history)} entradas de feedback")
            else:
                self._history = []
                logger.info("[FeedbackTracker] No hay historial de feedback previo")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"[FeedbackTracker] Error cargando feedback: {e}")
            self._history = []

    def _save_history(self):
        """Guarda el historial de feedback al archivo JSON. Debe llamarse dentro del lock."""
        try:
            with open(self._feedback_file, "w", encoding="utf-8") as f:
                json.dump(self._history, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"[FeedbackTracker] Error guardando feedback: {e}")

    # ============================================================
    # METODOS PRIVADOS - CONTADORES
    # ============================================================

    def _recompute_counters(self):
        """Recomputa todos los contadores desde el historial. Debe llamarse dentro del lock."""
        self._counters = {
            "total_feedback": 0,
            "thumbs_up": 0,
            "thumbs_down": 0,
            "rating_sum": 0.0,
            "rating_count": 0,
            "by_tool": defaultdict(lambda: {"positive": 0, "negative": 0}),
            "by_category": defaultdict(lambda: {"positive": 0, "negative": 0}),
        }

        for entry in self._history:
            self._update_counters_incremental(entry)

    def _update_counters_incremental(self, entry: dict):
        """Actualiza contadores con una sola entrada. Debe llamarse dentro del lock."""
        self._counters["total_feedback"] += 1

        feedback_type = entry.get("feedback_type", "")
        details = entry.get("details", {})

        # Contadores de tipo
        if feedback_type == "thumbs_up":
            self._counters["thumbs_up"] += 1
        elif feedback_type == "thumbs_down":
            self._counters["thumbs_down"] += 1
        elif feedback_type == "rating":
            rating = details.get("rating")
            if rating is not None:
                self._counters["rating_sum"] += rating
                self._counters["rating_count"] += 1

        # Contadores por herramienta
        tool_name = details.get("tool_name")
        if tool_name:
            if self._is_negative_entry(entry):
                self._counters["by_tool"][tool_name]["negative"] += 1
            else:
                self._counters["by_tool"][tool_name]["positive"] += 1

        # Contadores por categoria
        category = details.get("category")
        if category:
            if self._is_negative_entry(entry):
                self._counters["by_category"][category]["negative"] += 1
            else:
                self._counters["by_category"][category]["positive"] += 1

    # ============================================================
    # METODOS PRIVADOS - ANALISIS
    # ============================================================

    @staticmethod
    def _is_negative_entry(entry: dict) -> bool:
        """Determina si una entrada de feedback es negativa."""
        feedback_type = entry.get("feedback_type", "")
        details = entry.get("details", {})

        if feedback_type == "thumbs_down":
            return True
        if feedback_type == "rating" and details.get("rating", 5) <= 2:
            return True
        if feedback_type == "correction":
            return True

        return False

    def _compute_recent_trend(self) -> str:
        """
        Calcula la tendencia reciente del feedback comparando
        la ventana reciente vs la ventana anterior.

        Debe llamarse dentro del lock.
        """
        if len(self._history) < 10:
            return "stable"

        # Dividir en dos mitades temporales
        mid = len(self._history) // 2
        older = self._history[:mid]
        recent = self._history[mid:]

        # Calcular ratio negativo para cada mitad
        older_neg_ratio = self._neg_ratio(older)
        recent_neg_ratio = self._neg_ratio(recent)

        # Umbral de cambio significativo
        diff = older_neg_ratio - recent_neg_ratio
        threshold = 0.1

        if diff > threshold:
            return "improving"  # Menos negativo recientemente
        elif diff < -threshold:
            return "declining"  # Mas negativo recientemente
        else:
            return "stable"

    @staticmethod
    def _neg_ratio(entries: list[dict]) -> float:
        """Calcula el ratio de feedback negativo en una lista de entradas."""
        if not entries:
            return 0.0
        neg = sum(1 for e in entries if UserFeedbackTracker._is_negative_entry(e))
        return neg / len(entries)

    def _infer_tool_pattern(self, tool_name: str, neg_entries: list[dict]) -> str:
        """
        Infiere el patron de error basandose en el nombre de la herramienta
        y los detalles del feedback negativo.
        """
        tool_lower = tool_name.lower()

        # Patrones basados en herramienta
        code_tools = {"generar_codigo", "code_executor", "codigo", "ejecutar_codigo",
                       "file_editor", "escribir_archivo"}
        search_tools = {"buscar_web", "leer_web", "buscar_web_profundo", "web",
                         "buscar_youtube"}
        command_tools = {"ejecutar_comando", "sistema", "docker_sandbox"}

        if tool_lower in code_tools:
            # Verificar si las correcciones mencionan codigo no ejecutado
            for entry in neg_entries:
                correction = entry.get("details", {}).get("correction", "")
                comment = entry.get("details", {}).get("comment", "")
                combined = (correction + " " + comment).lower()
                if any(w in combined for w in ["ejecut", "correr", "run", "probar", "test"]):
                    return "codigo_sin_ejecutar"
            return "codigo_incorrecto"

        if tool_lower in search_tools:
            return "busqueda_superficial"

        if tool_lower in command_tools:
            return "error_en_comando"

        # Default: basado en comentarios
        for entry in neg_entries:
            comment = entry.get("details", {}).get("comment", "").lower()
            if any(w in comment for w in ["lento", "rapido", "tarda", "slow"]):
                return "respuesta_lenta"
            if any(w in comment for w in ["incorrecto", "mal", "error", "wrong"]):
                return "informacion_incorrecta"

        return "no_sigue_instrucciones"

    @staticmethod
    def _classify_correction(correction_text: str) -> Optional[str]:
        """Clasifica el texto de una correccion en un patron de error."""
        if not correction_text:
            return None

        text = correction_text.lower()

        # Palabras clave para cada patron
        classification_rules = [
            (["codigo", "code", "funcion", "variable", "bug", "error", "sintaxis"], "codigo_incorrecto"),
            (["ejecut", "correr", "run", "probar", "test", "verificar"], "codigo_sin_ejecutar"),
            (["lento", "tarda", "demora", "slow", "rapido"], "respuesta_lenta"),
            (["incompleto", "falta", "parcial", "mitad"], "respuesta_incompleta"),
            (["largo", "verboso", "demasiado texto", "extenso"], "respuesta_demasiado_larga"),
            (["corto", "breve", "superficial", "poco detalle"], "respuesta_demasiado_corta"),
            (["buscar", "busqueda", "encontrar", "profundiz"], "busqueda_superficial"),
            (["comando", "terminal", "shell", "consola"], "error_en_comando"),
            (["incorrecto", "mal", "equivocad", "wrong", "falso"], "informacion_incorrecta"),
            (["instruccion", "no hiciste", "pedi", "ignoraste"], "no_sigue_instrucciones"),
            (["formato", "forma", "estructura", "markdown"], "formato_incorrecto"),
        ]

        for keywords, pattern_name in classification_rules:
            if any(kw in text for kw in keywords):
                return pattern_name

        return "no_sigue_instrucciones"

    def _detect_length_pattern(self) -> Optional[dict]:
        """
        Detecta si hay patron de feedback negativo asociado a la
        longitud de las respuestas.

        Debe llamarse dentro del lock.
        """
        short_neg = 0
        long_neg = 0
        short_total = 0
        long_total = 0

        SHORT_THRESHOLD = 200   # caracteres
        LONG_THRESHOLD = 3000   # caracteres

        for entry in self._history:
            resp_len = entry.get("details", {}).get("response_length")
            if resp_len is None:
                continue

            is_neg = self._is_negative_entry(entry)

            if resp_len < SHORT_THRESHOLD:
                short_total += 1
                if is_neg:
                    short_neg += 1
            elif resp_len > LONG_THRESHOLD:
                long_total += 1
                if is_neg:
                    long_neg += 1

        # Evaluar patron de respuestas cortas con feedback negativo
        if short_total >= 3 and short_neg / short_total > 0.5:
            return {
                "pattern": "respuesta_demasiado_corta",
                "count": short_neg,
                "tools": [],
                "suggestion": NEGATIVE_PATTERN_SUGGESTIONS["respuesta_demasiado_corta"],
            }

        # Evaluar patron de respuestas largas con feedback negativo
        if long_total >= 3 and long_neg / long_total > 0.5:
            return {
                "pattern": "respuesta_demasiado_larga",
                "count": long_neg,
                "tools": [],
                "suggestion": NEGATIVE_PATTERN_SUGGESTIONS["respuesta_demasiado_larga"],
            }

        return None

    def _detect_low_rating_pattern(self) -> Optional[dict]:
        """
        Detecta si hay un patron de ratings bajos recurrentes.

        Debe llamarse dentro del lock.
        """
        low_ratings = [
            e for e in self._history
            if e.get("feedback_type") == "rating"
            and e.get("details", {}).get("rating", 5) <= 2
        ]

        if len(low_ratings) >= 3:
            tools = list(set(
                e.get("details", {}).get("tool_name")
                for e in low_ratings
                if e.get("details", {}).get("tool_name")
            ))
            return {
                "pattern": "informacion_incorrecta",
                "count": len(low_ratings),
                "tools": tools,
                "suggestion": NEGATIVE_PATTERN_SUGGESTIONS["informacion_incorrecta"],
            }

        return None

    def _pattern_to_instruction(self, pattern: dict) -> Optional[str]:
        """
        Convierte un patron detectado en una instruccion accionable
        para el prompt del agente.
        """
        name = pattern.get("pattern", "")
        count = pattern.get("count", 0)
        tools = pattern.get("tools", [])

        instruction_map = {
            "codigo_incorrecto": (
                f"Los usuarios frecuentemente dan thumbs down cuando generas codigo incorrecto "
                f"({count} veces). SIEMPRE verifica la logica del codigo antes de presentarlo."
            ),
            "codigo_sin_ejecutar": (
                f"Los usuarios frecuentemente dan thumbs down cuando generas codigo sin ejecutarlo "
                f"({count} veces). SIEMPRE ejecuta codigo despues de generarlo para verificar que funciona."
            ),
            "respuesta_lenta": (
                f"Los usuarios reportan que tus respuestas son lentas ({count} veces). "
                f"Usa el modelo mas rapido disponible y simplifica cuando sea posible."
            ),
            "respuesta_incompleta": (
                f"Los usuarios indican que tus respuestas estan incompletas ({count} veces). "
                f"PROPORCIONA respuestas completas y detalladas, no dejes partes sin cubrir."
            ),
            "respuesta_demasiado_larga": (
                f"Los usuarios indican que tus respuestas son demasiado largas ({count} veces). "
                f"SE MAS conciso y directo, evita explicaciones innecesarias."
            ),
            "respuesta_demasiado_corta": (
                f"Los usuarios indican que tus respuestas son demasiado cortas ({count} veces). "
                f"SE MAS detallado, incluye explicaciones y contexto adicional."
            ),
            "busqueda_superficial": (
                f"Los usuarios dan feedback negativo cuando las busquedas son superficiales ({count} veces). "
                f"SIEMPRE realiza busquedas mas profundas y verifica multiples fuentes."
            ),
            "error_en_comando": (
                f"Los usuarios reportan errores en comandos ({count} veces). "
                f"VERIFICA los comandos antes de ejecutarlos y maneja los errores apropiadamente."
            ),
            "informacion_incorrecta": (
                f"Los usuarios reportan informacion incorrecta ({count} veces). "
                f"VERIFICA la exactitud de la informacion antes de responder. Si no estas seguro, "
                f"indicalo claramente."
            ),
            "no_sigue_instrucciones": (
                f"Los usuarios indican que no sigues sus instrucciones ({count} veces). "
                f"LEE cuidadosamente las instrucciones completas antes de actuar y "
                f"verifica que cumples todos los requisitos."
            ),
            "formato_incorrecto": (
                f"Los usuarios reportan formato incorrecto ({count} veces). "
                f"PRESTA atencion al formato solicitado y asegurate de cumplirlo exactamente."
            ),
        }

        instruction = instruction_map.get(name)
        if instruction and tools:
            instruction += f" Herramientas afectadas: {', '.join(tools)}."

        return instruction


# ============================================================
# INSTANCIA GLOBAL (SINGLETON)
# ============================================================

# Se crea una unica instancia compartida del tracker
# Los modulos que necesiten feedback pueden importar esta instancia:
#   from tools.user_feedback import feedback_tracker
feedback_tracker = UserFeedbackTracker()
