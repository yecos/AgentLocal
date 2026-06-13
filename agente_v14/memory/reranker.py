"""
=============================================================
AGENTE v14 - Re-ranker Multi-Señal
=============================================================
Segunda fase de evaluacion que reordena candidatos usando
multiples señales de relevancia combinadas.

Señales:
1. Semantica (similitud coseno)
2. Lexica (BM25 / cobertura de terminos)
3. Frescura (decaimiento temporal)
4. Cobertura de terminos
5. Bonus por tipo de contenido

Pesos adaptativos segun tipo de consulta detectado.
=============================================================
"""

import logging
from datetime import datetime

from config import logger
from memory.bm25 import tokenize, tokenize_minimal


# ============================================================
# CLASIFICADOR DE TIPO DE CONSULTA
# ============================================================
class QueryClassifier:
    """Clasifica consultas por tipo para ajustar pesos del re-ranker."""

    # Patrones heuristicos para clasificacion
    FACTUAL_PATTERNS = [
        "que es", "que son", "que significa", "definicion", "concepto",
        "como funciona", "como se usa", "explica", "describe",
        "what is", "how does", "explain", "describe",
        "diferencia entre", "comparar", "ventaja",
    ]
    EXACT_PATTERNS = [
        "donde dice", "busca", "encuentra", "archivo",
        "error", "codigo", "funcion", "clase", "variable",
        "where is", "find", "grep", "search for",
        "linea", "implementacion", "definicion de",
    ]
    TEMPORAL_PATTERNS = [
        "ayer", "antes", "anterior", "ultimo", "reciente",
        "hace", "semana pasada", "mes pasado",
        "yesterday", "last time", "recently", "before",
        "antes de", "despues de",
    ]

    @staticmethod
    def classify(query):
        """Clasifica una consulta en: factual, exact, temporal, o general.

        Retorna: (tipo, confianza) donde tipo es uno de los anteriores
        y confianza es 0.0-1.0.
        """
        query_lower = query.lower()

        # Scoring por tipo
        scores = {"factual": 0, "exact": 0, "temporal": 0}

        for pattern in QueryClassifier.FACTUAL_PATTERNS:
            if pattern in query_lower:
                scores["factual"] += 1

        for pattern in QueryClassifier.EXACT_PATTERNS:
            if pattern in query_lower:
                scores["exact"] += 1

        for pattern in QueryClassifier.TEMPORAL_PATTERNS:
            if pattern in query_lower:
                scores["temporal"] += 1

        # Tipo con mayor score
        max_type = max(scores, key=scores.get)
        max_score = scores[max_type]

        if max_score == 0:
            return "general", 0.3

        confidence = min(max_score / 3.0, 1.0)
        return max_type, confidence


# ============================================================
# PESOS ADAPTATIVOS POR TIPO DE CONSULTA
# ============================================================
QUERY_TYPE_WEIGHTS = {
    "factual": {
        "semantic": 0.40,   # Alta importancia semantica para consultas conceptuales
        "lexical": 0.20,    # BM25 menos importante para conceptos
        "freshness": 0.10,  # Conocimiento factual no decae rapido
        "coverage": 0.15,
        "type_bonus": 0.15, # Bonus alto para tipo "knowledge"
    },
    "exact": {
        "semantic": 0.20,   # Menos importancia semantica
        "lexical": 0.40,    # BM25 muy importante para busquedas exactas
        "freshness": 0.10,
        "coverage": 0.25,   # Cobertura de terminos crucial
        "type_bonus": 0.05,
    },
    "temporal": {
        "semantic": 0.25,
        "lexical": 0.15,
        "freshness": 0.35,  # Frescura muy importante para consultas temporales
        "coverage": 0.10,
        "type_bonus": 0.15,
    },
    "general": {
        "semantic": 0.35,
        "lexical": 0.25,
        "freshness": 0.15,
        "coverage": 0.15,
        "type_bonus": 0.10,
    },
}

# Bonus por tipo de metadata
METADATA_TYPE_BONUS = {
    "knowledge": 1.0,      # Conocimiento factual: maxima prioridad
    "correction": 0.9,     # Correcciones del usuario: alta prioridad
    "lesson": 0.85,        # Lecciones aprendidas
    "experience": 0.7,     # Experiencia personal
    "conversation": 0.3,   # Conversacion casual: baja prioridad
    "task": 0.5,           # Tareas
    "note": 0.6,           # Notas
}


# ============================================================
# RE-RANKER MULTI-SEÑAL
# ============================================================
class MultiSignalReranker:
    """Re-ranker que combina multiples señales de relevancia.

    Se inserta entre la fase de recuperacion y la construccion
    de contexto para mejorar la calidad de los resultados top-k.
    """

    # Pesos por defecto (general)
    DEFAULT_WEIGHTS = QUERY_TYPE_WEIGHTS["general"]

    def __init__(self, use_adaptive_weights=True):
        self.use_adaptive = use_adaptive_weights
        self.classifier = QueryClassifier()
        self._stats = {"reranked": 0, "query_types": {}}

    def rerank(self, query, candidates, limit=5):
        """Re-rankear candidatos usando multi-señal.

        Args:
            query: Texto de la consulta original
            candidates: Lista de resultados candidatos (dicts con score, text, metadata)
            limit: Numero maximo de resultados a retornar

        Returns:
            Lista de candidatos re-rankeados con rerank_score y signals.
        """
        if not candidates:
            return []

        # Clasificar tipo de consulta
        if self.use_adaptive:
            query_type, confidence = self.classifier.classify(query)
            weights = QUERY_TYPE_WEIGHTS.get(query_type, self.DEFAULT_WEIGHTS)
            # Interpolar con pesos default si baja confianza
            if confidence < 0.5:
                blend = confidence * 2  # 0-1 range
                weights = {
                    k: weights[k] * blend + self.DEFAULT_WEIGHTS[k] * (1 - blend)
                    for k in self.DEFAULT_WEIGHTS
                }
        else:
            query_type = "general"
            weights = self.DEFAULT_WEIGHTS

        # Actualizar stats
        self._stats["reranked"] += 1
        self._stats["query_types"][query_type] = self._stats["query_types"].get(query_type, 0) + 1

        # Calcular señales para cada candidato
        scored = []
        for candidate in candidates:
            signals = self._compute_signals(query, candidate, weights)
            final_score = sum(signals[k] * weights[k] for k in weights)

            scored.append({
                **candidate,
                "rerank_score": round(final_score, 4),
                "signals": {k: round(v, 3) for k, v in signals.items()},
                "query_type": query_type,
            })

        scored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored[:limit]

    def _compute_signals(self, query, candidate, weights):
        """Computa las 5 señales de relevancia para un candidato.

        Cada señal se normaliza a [0, 1].
        """
        signals = {}

        # 1. Señal semantica (similitud coseno)
        raw_sim = candidate.get("raw_similarity", candidate.get("score", 0))
        signals["semantic"] = max(0, min(1, raw_sim))

        # 2. Señal lexica (BM25 score normalizado)
        bm25_score = candidate.get("bm25_score", 0)
        signals["lexical"] = min(1, bm25_score / 10.0) if bm25_score > 0 else 0.0

        # Si no hay BM25 score, estimar con cobertura de terminos simple
        if signals["lexical"] == 0:
            try:
                query_stems = set(tokenize(query))
                doc_stems = set(tokenize(candidate.get("text", "")))
                if query_stems and doc_stems:
                    signals["lexical"] = len(query_stems & doc_stems) / len(query_stems)
            except Exception:
                signals["lexical"] = 0.0

        # 3. Señal de frescura (1 - decaimiento temporal)
        decay = candidate.get("decay", None)
        if decay is not None:
            signals["freshness"] = 1.0 - decay  # Decay alto = frescura baja
        else:
            # Calcular decaimiento si tenemos fecha
            created = candidate.get("created", "")
            if not created and candidate.get("metadata"):
                created = candidate["metadata"].get("created", "")
            signals["freshness"] = self._compute_freshness(created)

        # 4. Cobertura de terminos
        try:
            query_stems = set(tokenize_minimal(query))
            doc_stems = set(tokenize_minimal(candidate.get("text", "")))
            if query_stems:
                signals["coverage"] = len(query_stems & doc_stems) / len(query_stems)
            else:
                signals["coverage"] = 0.0
        except Exception:
            signals["coverage"] = 0.0

        # 5. Bonus por tipo de contenido
        signals["type_bonus"] = self._compute_type_bonus(candidate.get("metadata", {}))

        return signals

    def _compute_freshness(self, created_at):
        """Computa frescura basada en fecha de creacion (0-1)."""
        if not created_at:
            return 0.5  # Neutral si no hay fecha
        try:
            created = datetime.fromisoformat(created_at)
            days_old = (datetime.now() - created).total_seconds() / 86400
            # Decaimiento exponencial con half-life de 30 dias
            import math
            freshness = 1.0 - math.exp(-0.693 * days_old / 30)
            return max(0, min(1, freshness))
        except Exception:
            return 0.5

    def _compute_type_bonus(self, metadata):
        """Computa bonus segun tipo de contenido (0-1)."""
        if not metadata:
            return 0.3  # Neutral

        content_type = metadata.get("type", "").lower()
        source = metadata.get("source", "").lower()

        # Bonus por tipo
        for key, bonus in METADATA_TYPE_BONUS.items():
            if key in content_type or key in source:
                return bonus

        # Si es correccion del usuario
        if metadata.get("source") == "user_correction":
            return 0.9

        return 0.3  # Default neutral

    def stats(self):
        """Retorna estadisticas del re-ranker."""
        return self._stats.copy()
