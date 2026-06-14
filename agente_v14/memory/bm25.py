"""
=============================================================
AGENTE v14 - Motor BM25 para Búsqueda Híbrida
=============================================================
Implementación de BM25 (Okapi BM25) con soporte para
stemming español y eliminación de stopwords.
Se integra con el vector store para búsqueda híbrida.

BM25 Parameters:
    K1 (term frequency saturation):
        Controls how quickly additional occurrences of a term
        contribute less to the score. Range 1.2-2.0; higher values
        privilege documents with many term matches. Default: 1.5.

    B (document length normalization):
        Controls how much document length affects scoring. Range 0-1;
        0 means no length normalization, 1 means full normalization.
        Standard value: 0.75 (penalizes long documents moderately).
=============================================================
"""

from __future__ import annotations

import math
import logging
from collections import Counter, defaultdict
from typing import Any

from config import logger

# Stemmer español (lazy import para no romper si NLTK no está)
_stemmer: Any = None
_stopwords: set[str] | None = None


def _get_stemmer() -> Any | None:
    """Lazy init del stemmer Snowball Spanish.

    Returns:
        Una instancia de SnowballStemmer("spanish"), o None si NLTK
        no está disponible. Usa ``False`` como marcador interno para
        no reintentar la importación.
    """
    global _stemmer
    if _stemmer is None:
        try:
            from nltk.stem.snowball import SnowballStemmer
            _stemmer = SnowballStemmer("spanish")
        except ImportError:
            logger.debug("NLTK no disponible, stemming deshabilitado")
            _stemmer = False  # Marcador para no reintentar
    return _stemmer if _stemmer is not False else None


def _get_stopwords() -> set[str]:
    """Lazy init de stopwords en español.

    Returns:
        Conjunto de stopwords en español. Incluye las stopwords
        de NLTK (si disponibles) más un conjunto extendido de
        palabras comunes en español.
    """
    global _stopwords
    if _stopwords is None:
        try:
            from nltk.corpus import stopwords as sw_module
            _stopwords = set(sw_module.words("spanish"))
        except Exception as e:
            logger.debug(f"NLTK stopwords no disponibles: {e}")
            _stopwords = set()
        # Añadir stopwords comunes adicionales
        _stopwords.update({
            "que", "del", "los", "las", "por", "con", "para", "una",
            "uno", "como", "pero", "sus", "han", "este", "esta",
            "eso", "esa", "hay", "puede", "todos", "asi", "mas",
            "eso", "muy", "ya", "si", "no", "ni", "tu", "te",
            "se", "le", "lo", "la", "el", "en", "es", "al",
            "de", "un", "me", "mi", "ha", "he", "soy", "son",
            "fue", "ser", "era", "hay", "puede", "sido", "tener",
            "tiene", "tenia", "hacer", "hace", "hacia", "hecho",
        })
    return _stopwords


def tokenize(text: str) -> list[str]:
    """Tokeniza, elimina stopwords y aplica stemming español.

    Pipeline: lowercase → split por espacios → limpieza de caracteres
    no alfanuméricos (preserva acentos) → filtrado de stopwords →
    stemming con SnowballStemmer("spanish").

    Args:
        text: Texto a tokenizar.

    Returns:
        Lista de stems normalizados (strings).
    """
    if not text:
        return []

    # Tokenización simple: split por espacios y limpieza
    tokens: list[str] = []
    for word in text.lower().split():
        # Limpiar caracteres no alfanuméricos (mantener acentos)
        cleaned = "".join(c for c in word if c.isalnum() or c in "áéíóúñü")
        if not cleaned:
            continue
        # Filtrar stopwords (antes de stemming para mejor match)
        sw = _get_stopwords()
        if sw and cleaned in sw:
            continue
        # Aplicar stemming
        stemmer = _get_stemmer()
        if stemmer:
            try:
                cleaned = stemmer.stem(cleaned)
            except Exception as e:
                logger.debug(f"Stemming falló para '{cleaned}': {e}")
        tokens.append(cleaned)

    return tokens


def tokenize_minimal(text: str) -> list[str]:
    """Tokenización mínima sin stemming (para búsquedas exactas rápidas).

    Pipeline: lowercase → split por espacios → limpieza de caracteres
    no alfanuméricos (preserva acentos) → filtrado de stopwords.
    No aplica stemming, por lo que preserva la forma original de las
    palabras (útil para coincidencias exactas).

    Args:
        text: Texto a tokenizar.

    Returns:
        Lista de tokens normalizados sin stemming (strings).
    """
    if not text:
        return []

    tokens: list[str] = []
    sw = _get_stopwords()
    for word in text.lower().split():
        cleaned = "".join(c for c in word if c.isalnum() or c in "áéíóúñü")
        if cleaned and (not sw or cleaned not in sw):
            tokens.append(cleaned)
    return tokens


class BM25:
    """Okapi BM25 con soporte para español.

    BM25 es un modelo de ranking basado en el modelo probabilístico
    de recuperación de información. La fórmula de scoring para un
    término t en un documento d es::

        score(t, d) = IDF(t) * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avgdl))

    donde:
        - IDF(t) = log((N - df + 0.5) / (df + 0.5) + 1)  (con suavizado)
        - tf = frecuencia del término en el documento
        - dl = longitud del documento en tokens
        - avgdl = longitud promedio de documentos en tokens

    Args:
        documents: Lista de documentos para indexar. Cada documento puede
            ser un dict con keys ``"id"`` y ``"text"``, o una tupla/lista
            ``(doc_id, text)``. Si es None, se crea un índice vacío.
        k1: Controla la saturación de frecuencia de término (1.2-2.0).
            Valores altos privilegian documentos con muchos matches.
            Default: 1.5.
        b: Controla la normalización por longitud de documento (0-1).
            Valores altos penalizan documentos largos. Default: 0.75.
        use_stemming: Si True, aplica stemming español durante la
            tokenización. Si False, usa tokenización mínima sin stemming.
            Default: True.
    """

    def __init__(
        self,
        documents: list[dict | tuple | list] | None = None,
        k1: float = 1.5,
        b: float = 0.75,
        use_stemming: bool = True,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.use_stemming = use_stemming
        self.tokenize_fn = tokenize if use_stemming else tokenize_minimal

        # Índice invertido
        self.doc_count: int = 0
        self.avgdl: float = 0  # Longitud promedio de documento
        self.doc_lengths: list[int] = []  # Longitud de cada documento en tokens
        self.doc_freqs: list[Counter] = []  # Frecuencias de término por documento
        self.idf: dict[str, float] = {}  # IDF por término
        self.inverted_index: dict[str, list[tuple[int, int]]] = defaultdict(list)  # term -> [(doc_idx, tf)]
        self.doc_ids: list[str] = []  # IDs externos mapeados a índices internos
        self._doc_texts: list[str] = []  # Textos originales (para reconstruir si se necesita)

        if documents:
            self._build_index(documents)

    def _build_index(self, documents: list[dict | tuple | list]) -> None:
        """Construye el índice BM25 a partir de una lista de documentos.

        Args:
            documents: Lista de documentos. Cada documento puede ser:
                - dict con keys ``"id"`` y ``"text"``
                - tuple/list ``(doc_id, text)`` con al menos 2 elementos
        """
        self.doc_count = 0
        self.doc_lengths = []
        self.doc_freqs = []
        self.idf = {}
        self.inverted_index = defaultdict(list)
        self.doc_ids = []
        self._doc_texts = []

        corpus_freq: Counter[str] = Counter()  # Cuántos docs contienen cada término

        for doc in documents:
            if isinstance(doc, dict):
                doc_id = doc.get("id", str(self.doc_count))
                text = doc.get("text", "")
            elif isinstance(doc, (list, tuple)) and len(doc) >= 2:
                doc_id, text = doc[0], doc[1]
            else:
                continue

            tokens = self.tokenize_fn(text)
            freq = Counter(tokens)
            dl = len(tokens)

            idx = self.doc_count
            self.doc_ids.append(doc_id)
            self._doc_texts.append(text)
            self.doc_lengths.append(dl)
            self.doc_freqs.append(freq)

            # Índice invertido
            for term, tf in freq.items():
                self.inverted_index[term].append((idx, tf))
                corpus_freq[term] += 1

            self.doc_count += 1

        # Longitud promedio
        self.avgdl = sum(self.doc_lengths) / max(self.doc_count, 1)

        # Calcular IDF para cada término
        for term, df in corpus_freq.items():
            # Fórmula BM25 IDF (con suavizado para evitar negativos)
            self.idf[term] = math.log((self.doc_count - df + 0.5) / (df + 0.5) + 1)

        logger.info(
            f"BM25 indexado: {self.doc_count} docs, {len(self.idf)} términos únicos, "
            f"avgdl={self.avgdl:.1f}"
        )

    def add_document(self, doc_id: str, text: str) -> None:
        """Añade un documento al índice existente (incremental).

        Más eficiente que reconstruir todo el índice. Actualiza el
        promedio de longitud de documentos y recalcula los valores IDF
        de los términos afectados.

        Args:
            doc_id: Identificador único del documento.
            text: Contenido textual del documento.
        """
        tokens = self.tokenize_fn(text)
        freq = Counter(tokens)
        dl = len(tokens)

        # Actualizar avgdl
        old_total = self.avgdl * self.doc_count
        self.doc_count += 1
        self.avgdl = (old_total + dl) / self.doc_count

        idx = len(self.doc_ids)
        self.doc_ids.append(doc_id)
        self._doc_texts.append(text)
        self.doc_lengths.append(dl)
        self.doc_freqs.append(freq)

        # Actualizar índice invertido e IDF
        for term, tf in freq.items():
            self.inverted_index[term].append((idx, tf))

            if term in self.idf:
                # Recalcular IDF (incremental)
                df = len(self.inverted_index[term])
                self.idf[term] = math.log(
                    (self.doc_count - df + 0.5) / (df + 0.5) + 1
                )
            else:
                self.idf[term] = math.log(
                    (self.doc_count - 1 + 0.5) / (1 + 0.5) + 1
                )

    def search(
        self,
        query: str,
        limit: int = 10,
        min_score: float = 0.0,
    ) -> list[tuple[str, float]]:
        """Busca documentos relevantes usando BM25.

        Usa el índice invertido para eficiencia: solo evalúa documentos
        que contienen al menos un término de la query (skip documentos
        sin matches).

        Args:
            query: Texto de la consulta.
            limit: Número máximo de resultados a retornar. Default: 10.
            min_score: Puntuación mínima para incluir un resultado.
                Default: 0.0 (incluye todos los que tienen match).

        Returns:
            Lista de tuplas ``(doc_id, score)`` ordenada por score
            descendente. Los scores están redondeados a 4 decimales.
        """
        if not self.idf or self.doc_count == 0:
            return []

        query_tokens = self.tokenize_fn(query)
        if not query_tokens:
            return []

        # Recolectar docs candidatos del índice invertido
        candidate_scores: dict[int, float] = defaultdict(float)

        for term in query_tokens:
            if term not in self.idf:
                continue

            idf = self.idf[term]
            postings = self.inverted_index.get(term, [])

            for doc_idx, tf in postings:
                dl = self.doc_lengths[doc_idx]
                # Fórmula BM25
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1))
                score = idf * numerator / denominator
                candidate_scores[doc_idx] += score

        # Ordenar por score
        results: list[tuple[str, float]] = []
        for doc_idx, score in candidate_scores.items():
            if score >= min_score:
                doc_id = self.doc_ids[doc_idx]
                results.append((doc_id, round(score, 4)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def get_term_coverage(self, query: str, doc_text: str) -> float:
        """Calcula qué porcentaje de términos de la query aparecen en el documento.

        Útil como señal adicional de relevancia en re-ranking.

        Args:
            query: Texto de la consulta.
            doc_text: Texto del documento candidato.

        Returns:
            Valor entre 0.0 y 1.0 representando la fracción de términos
            de la query que aparecen en el documento. 0.0 si la query
            o el documento no tienen tokens.
        """
        query_tokens = set(self.tokenize_fn(query))
        if not query_tokens:
            return 0.0
        doc_tokens = set(self.tokenize_fn(doc_text))
        if not doc_tokens:
            return 0.0
        matches = len(query_tokens & doc_tokens)
        return matches / len(query_tokens)

    def rebuild(self, documents: list[dict | tuple | list]) -> None:
        """Reconstruye el índice completamente desde una lista de documentos.

        Args:
            documents: Lista de documentos (mismo formato que ``__init__``).
        """
        self._build_index(documents)

    def stats(self) -> dict[str, int | float]:
        """Retorna estadísticas del índice BM25.

        Returns:
            Diccionario con keys:
                - ``doc_count``: número de documentos indexados
                - ``unique_terms``: número de términos únicos
                - ``avg_doc_length``: longitud promedio de documentos
                - ``index_size_entries``: total de entradas en el índice invertido
        """
        return {
            "doc_count": self.doc_count,
            "unique_terms": len(self.idf),
            "avg_doc_length": round(self.avgdl, 1),
            "index_size_entries": sum(len(v) for v in self.inverted_index.values()),
        }


def reciprocal_rank_fusion(
    rankings: list[list[str]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fusiona múltiples rankings usando Reciprocal Rank Fusion (RRF).

    RRF es un método simple y efectivo para combinar rankings de
    múltiples sistemas de recuperación. La fórmula para cada documento
    es::

        RRF_score(d) = Σ  1 / (k + rank_i(d))

    donde rank_i(d) es la posición del documento d en el ranking i
    (empezando desde 1).

    Ventajas de RRF:
    - No requiere normalización de scores entre sistemas
    - Insensible a distribuciones de score diferentes
    - Funciona bien incluso con rankings parciales

    Args:
        rankings: Lista de listas de doc_ids, cada una ordenada por
            relevancia (más relevante primero).
        k: Constante de suavizado. Valores altos reducen el impacto
            de la posición en el ranking. Estándar: 60. Default: 60.

    Returns:
        Lista de tuplas ``(doc_id, rrf_score)`` ordenada por score
        descendente.
    """
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)

    result = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return result
