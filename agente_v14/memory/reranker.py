"""
=============================================================
AGENTE v14 - Re-ranker Multi-Señal
=============================================================
Segunda fase de evaluacion que reordena candidatos usando
multiples señales de relevancia combinadas.

Multi-Signal Reranking:
    Cada candidato recibe un score compuesto por 5 señales
    normalizadas a [0, 1], ponderadas segun el tipo de consulta:

    1. Semantica (similitud coseno): Mide la similitud vectorial
       entre la query y el documento. Alta para consultas conceptuales.
    2. Lexica (BM25 / cobertura de terminos): Mide la coincidencia
       de terminos especificos. Alta para consultas exactas (IDs, codigos).
    3. Frescura (decaimiento temporal): Mide la recencia del documento.
       Usa half-life diferenciado por tipo de contenido:
       knowledge=365d, correction=180d, lesson=90d, experience=60d,
       task=14d, conversation=7d, note=30d.
    4. Cobertura de terminos: Fraccion de terminos de la query
       presentes en el documento (sin stemming).
    5. Bonus por tipo de contenido: Prioriza ciertos tipos de
       metadata (knowledge=1.0, correction=0.9, lesson=0.85, etc.).

    Pesos adaptativos segun tipo de consulta (detectado por
    QueryClassifier):
    - factual: semantica alta (0.40), lexica baja (0.20)
    - exact: lexica alta (0.40), cobertura alta (0.25)
    - temporal: frescura alta (0.35)
    - general: balanceado con sesgo semantico (0.35)

=============================================================
"""

from __future__ import annotations

import math
import logging
from datetime import datetime
from typing import Any

from config import logger
from memory.bm25 import tokenize, tokenize_minimal

# Half-life diferenciado por tipo de contenido (en dias)
# Debe coincidir con DECAY_HALF_LIFE_BY_TYPE de triple_memory.py
DECAY_HALF_LIFE_BY_TYPE: dict[str, int] = {
    "knowledge": 365,
    "correction": 180,
    "lesson": 90,
    "experience": 60,
    "task": 14,
    "conversation": 7,
    "note": 30,
}
DEFAULT_HALF_LIFE: int = 30  # Half-life por defecto


# ============================================================
# CLASIFICADOR DE TIPO DE CONSULTA
# ============================================================
class QueryClassifier:
    """Clasifica consultas por tipo para ajustar pesos del re-ranker.

    Usa patrones heuristicos en español e inglés para determinar
    si una consulta es de tipo factual, exact, temporal, o general.
    La clasificación afecta los pesos de las señales en el re-ranker.
    """

    # Patrones heuristicos para clasificacion
    FACTUAL_PATTERNS: list[str] = [
        "que es", "que son", "que significa", "definicion", "concepto",
        "como funciona", "como se usa", "explica", "describe",
        "what is", "how does", "explain", "describe",
        "diferencia entre", "comparar", "ventaja",
    ]
    EXACT_PATTERNS: list[str] = [
        "donde dice", "busca", "encuentra", "archivo",
        "error", "codigo", "funcion", "clase", "variable",
        "where is", "find", "grep", "search for",
        "linea", "implementacion", "definicion de",
    ]
    TEMPORAL_PATTERNS: list[str] = [
        "ayer", "antes", "anterior", "ultimo", "reciente",
        "hace", "semana pasada", "mes pasado",
        "yesterday", "last time", "recently", "before",
        "antes de", "despues de",
    ]

    @staticmethod
    def classify(query: str) -> tuple[str, float]:
        """Clasifica una consulta en: factual, exact, temporal, o general.

        Aplica normalización de acentos y caracteres especiales antes
        del matching para soportar consultas en español con o sin
        acentos.

        Args:
            query: Texto de la consulta del usuario.

        Returns:
            Tupla ``(tipo, confianza)`` donde tipo es uno de
            ``"factual"``, ``"exact"``, ``"temporal"`` o ``"general"``,
            y confianza es un valor entre 0.0 y 1.0.
        """
        query_lower = query.lower()

        # Scoring por tipo
        scores: dict[str, int] = {"factual": 0, "exact": 0, "temporal": 0}

        # Normalizar: remover ¿¡ y acentos para mejor matching en español
        query_normalized = query_lower.replace("¿", "").replace("¡", "")
        # Normalizar acentos comunes en patrones de búsqueda
        accent_map = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ü": "u", "ñ": "ñ"}
        query_normalized = "".join(accent_map.get(c, c) for c in query_normalized)

        for pattern in QueryClassifier.FACTUAL_PATTERNS:
            if pattern in query_normalized:
                scores["factual"] += 1

        for pattern in QueryClassifier.EXACT_PATTERNS:
            if pattern in query_normalized:
                scores["exact"] += 1

        for pattern in QueryClassifier.TEMPORAL_PATTERNS:
            if pattern in query_normalized:
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
QUERY_TYPE_WEIGHTS: dict[str, dict[str, float]] = {
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
METADATA_TYPE_BONUS: dict[str, float] = {
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

    El re-ranking funciona en 3 pasos:
    1. Clasificar la consulta (factual/exact/temporal/general)
    2. Calcular 5 señales normalizadas [0,1] para cada candidato
    3. Combinar señales con pesos adaptativos segun tipo de consulta

    Si la confianza de la clasificacion es baja (<0.5), se interpolan
    los pesos del tipo detectado con los pesos generales.

    Args:
        use_adaptive_weights: Si True, ajusta los pesos de las señales
            segun el tipo de consulta detectado. Si False, usa siempre
            los pesos generales. Default: True.
    """

    # Pesos por defecto (general)
    DEFAULT_WEIGHTS: dict[str, float] = QUERY_TYPE_WEIGHTS["general"]

    def __init__(self, use_adaptive_weights: bool = True) -> None:
        self.use_adaptive = use_adaptive_weights
        self.classifier = QueryClassifier()
        self._stats: dict[str, Any] = {"reranked": 0, "query_types": {}}

    def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Re-rankear candidatos usando multi-señal.

        Args:
            query: Texto de la consulta original.
            candidates: Lista de resultados candidatos (dicts con keys
                como ``score``, ``text``, ``metadata``, ``bm25_score``,
                ``decay``, ``created``, ``raw_similarity``, etc.).
            limit: Numero maximo de resultados a retornar. Default: 5.

        Returns:
            Lista de candidatos re-rankeados (ordenados por
            ``rerank_score`` descendente) con las keys adicionales:
            ``rerank_score``, ``signals`` (dict de señal → valor),
            y ``query_type``.
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
        scored: list[dict[str, Any]] = []
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

    def _compute_signals(
        self,
        query: str,
        candidate: dict[str, Any],
        weights: dict[str, float],
    ) -> dict[str, float]:
        """Computa las 5 señales de relevancia para un candidato.

        Cada señal se normaliza a [0, 1]:

        1. **semantic**: Similitud coseno del embedding (``raw_similarity``
           o ``score`` del candidato).
        2. **lexical**: Score BM25 normalizado (dividido por 10), o
           estimación por cobertura de stems si no hay BM25 score.
        3. **freshness**: 1 - decaimiento temporal, con half-life
           diferenciado por tipo de contenido.
        4. **coverage**: Fracción de términos de la query (sin stemming)
           presentes en el documento.
        5. **type_bonus**: Bonus según tipo de metadata (knowledge=1.0,
           correction=0.9, etc.).

        Args:
            query: Texto de la consulta original.
            candidate: Diccionario del candidato con sus datos.
            weights: Diccionario de pesos por señal (usado para
                determinar qué señales calcular).

        Returns:
            Diccionario con keys ``semantic``, ``lexical``,
            ``freshness``, ``coverage``, ``type_bonus``, cada una
            con un valor float en [0, 1].
        """
        signals: dict[str, float] = {}

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
            except Exception as e:
                logger.debug(f"Error calculando señal lexica con tokenización: {e}")
                signals["lexical"] = 0.0

        # 3. Señal de frescura (1 - decaimiento temporal diferenciado)
        decay = candidate.get("decay", None)
        if decay is not None:
            signals["freshness"] = 1.0 - decay  # Decay alto = frescura baja
        else:
            # Calcular decaimiento diferenciado si tenemos fecha
            created = candidate.get("created", "")
            metadata = candidate.get("metadata", {})
            if not created and metadata:
                created = metadata.get("created", "")
            signals["freshness"] = self._compute_freshness(created, metadata=metadata)

        # 4. Cobertura de terminos
        try:
            query_stems = set(tokenize_minimal(query))
            doc_stems = set(tokenize_minimal(candidate.get("text", "")))
            if query_stems:
                signals["coverage"] = len(query_stems & doc_stems) / len(query_stems)
            else:
                signals["coverage"] = 0.0
        except Exception as e:
            logger.debug(f"Error calculando cobertura de términos: {e}")
            signals["coverage"] = 0.0

        # 5. Bonus por tipo de contenido
        signals["type_bonus"] = self._compute_type_bonus(candidate.get("metadata", {}))

        return signals

    def _compute_freshness(
        self,
        created_at: str,
        metadata: dict[str, Any] | None = None,
    ) -> float:
        """Computa frescura basada en fecha de creacion y tipo de contenido.

        Usa half-life diferenciado: conocimiento factual decae lento
        (365 dias), tareas decaen rapido (14 dias), conversacion muy
        rapido (7 dias). La fórmula es::

            freshness = 1 - exp(-0.693 * days_old / half_life)

        Args:
            created_at: Fecha de creacion en formato ISO 8601.
            metadata: Metadatos del documento, pueden contener la
                key ``"type"`` para determinar el half-life.

        Returns:
            Valor entre 0.0 y 1.0. 0.5 si no hay fecha disponible
            (neutral), 1.0 si es muy reciente, cercano a 0.0 si
            es muy antiguo.
        """
        if not created_at:
            return 0.5  # Neutral si no hay fecha
        try:
            created = datetime.fromisoformat(created_at)
            days_old = (datetime.now() - created).total_seconds() / 86400

            # Determinar half-life segun tipo de contenido
            half_life = DEFAULT_HALF_LIFE
            if metadata:
                content_type = metadata.get("type", "").lower()
                if content_type in DECAY_HALF_LIFE_BY_TYPE:
                    half_life = DECAY_HALF_LIFE_BY_TYPE[content_type]

            # Decaimiento exponencial con half-life diferenciado
            freshness = 1.0 - math.exp(-0.693 * days_old / half_life)
            return max(0, min(1, freshness))
        except Exception as e:
            logger.debug(f"Error calculando frescura: {e}")
            return 0.5

    def _compute_type_bonus(self, metadata: dict[str, Any] | None) -> float:
        """Computa bonus segun tipo de contenido.

        Revisa el ``type`` y ``source`` en los metadatos del documento
        y retorna un bonus normalizado según ``METADATA_TYPE_BONUS``.

        Args:
            metadata: Metadatos del documento, pueden contener keys
                ``"type"`` y ``"source"``.

        Returns:
            Valor entre 0.0 y 1.0. 0.3 si no hay metadatos o no
            se reconoce el tipo (neutral).
        """
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

    def stats(self) -> dict[str, Any]:
        """Retorna estadisticas del re-ranker.

        Returns:
            Diccionario con keys ``reranked`` (contador total) y
            ``query_types`` (dict de tipo → contador).
        """
        return self._stats.copy()
