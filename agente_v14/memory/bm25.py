"""
=============================================================
AGENTE v14 - Motor BM25 para Búsqueda Híbrida
=============================================================
Implementación de BM25 (Okapi BM25) con soporte para
stemming español y eliminación de stopwords.
Se integra con el vector store para búsqueda híbrida.
=============================================================
"""

import math
import logging
from collections import Counter, defaultdict

from config import logger

# Stemmer español (lazy import para no romper si NLTK no está)
_stemmer = None
_stopwords = None


def _get_stemmer():
    """Lazy init del stemmer Snowball Spanish."""
    global _stemmer
    if _stemmer is None:
        try:
            from nltk.stem.snowball import SnowballStemmer
            _stemmer = SnowballStemmer("spanish")
        except ImportError:
            logger.debug("NLTK no disponible, stemming deshabilitado")
            _stemmer = False  # Marcador para no reintentar
    return _stemmer if _stemmer is not False else None


def _get_stopwords():
    """Lazy init de stopwords en español."""
    global _stopwords
    if _stopwords is None:
        try:
            from nltk.corpus import stopwords as sw_module
            _stopwords = set(sw_module.words("spanish"))
        except Exception:
            logger.debug("NLTK stopwords no disponibles")
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


def tokenize(text):
    """Tokeniza, elimina stopwords y aplica stemming español.

    Retorna lista de stems normalizados.
    """
    if not text:
        return []

    # Tokenización simple: split por espacios y limpieza
    tokens = []
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
            except Exception:
                pass  # Mantener original si stemming falla
        tokens.append(cleaned)

    return tokens


def tokenize_minimal(text):
    """Tokenización mínima sin stemming (para búsquedas exactas rápidas).

    Solo lowercase, limpieza básica y stopwords.
    """
    if not text:
        return []

    tokens = []
    sw = _get_stopwords()
    for word in text.lower().split():
        cleaned = "".join(c for c in word if c.isalnum() or c in "áéíóúñü")
        if cleaned and (not sw or cleaned not in sw):
            tokens.append(cleaned)
    return tokens


class BM25:
    """
    Okapi BM25 con soporte para español.

    Parámetros:
        k1: Controla la saturación de frecuencia de término (1.2-2.0).
            Valores altos privilegian documentos con muchos matches.
        b: Controla la normalización por longitud (0.75 estándar).
            Valores altos penalizan documentos largos.
        use_stemming: Si True, aplica stemming español.
    """

    def __init__(self, documents=None, k1=1.5, b=0.75, use_stemming=True):
        self.k1 = k1
        self.b = b
        self.use_stemming = use_stemming
        self.tokenize_fn = tokenize if use_stemming else tokenize_minimal

        # Índice invertido
        self.doc_count = 0
        self.avgdl = 0  # Longitud promedio de documento
        self.doc_lengths = []  # Longitud de cada documento en tokens
        self.doc_freqs = []  # Frecuencias de término por documento
        self.idf = {}  # IDF por término
        self.inverted_index = defaultdict(list)  # term -> [(doc_idx, tf)]
        self.doc_ids = []  # IDs externos mapeados a índices internos
        self._doc_texts = []  # Textos originales (para reconstruir si se necesita)

        if documents:
            self._build_index(documents)

    def _build_index(self, documents):
        """Construye el índice BM25 a partir de una lista de documentos.

        documents: lista de (doc_id, text) o lista de dicts con 'id' y 'text'
        """
        self.doc_count = 0
        self.doc_lengths = []
        self.doc_freqs = []
        self.idf = {}
        self.inverted_index = defaultdict(list)
        self.doc_ids = []
        self._doc_texts = []

        corpus_freq = Counter()  # Cuántos docs contienen cada término

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

    def add_document(self, doc_id, text):
        """Añade un documento al índice existente (incremental).

        Más eficiente que reconstruir todo el índice.
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

    def search(self, query, limit=10, min_score=0.0):
        """Busca documentos relevantes usando BM25.

        Retorna lista de (doc_id, score) ordenada por score descendente.
        Usa el índice invertido para eficiencia (solo evalúa docs con matches).
        """
        if not self.idf or self.doc_count == 0:
            return []

        query_tokens = self.tokenize_fn(query)
        if not query_tokens:
            return []

        # Recolectar docs candidatos del índice invertido
        candidate_scores = defaultdict(float)

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
        results = []
        for doc_idx, score in candidate_scores.items():
            if score >= min_score:
                doc_id = self.doc_ids[doc_idx]
                results.append((doc_id, round(score, 4)))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def get_term_coverage(self, query, doc_text):
        """Calcula qué porcentaje de términos de la query aparecen en el documento.

        Retorna un valor entre 0 y 1.
        """
        query_tokens = set(self.tokenize_fn(query))
        if not query_tokens:
            return 0.0
        doc_tokens = set(self.tokenize_fn(doc_text))
        if not doc_tokens:
            return 0.0
        matches = len(query_tokens & doc_tokens)
        return matches / len(query_tokens)

    def rebuild(self, documents):
        """Reconstruye el índice completamente desde una lista de documentos."""
        self._build_index(documents)

    def stats(self):
        """Retorna estadísticas del índice BM25."""
        return {
            "doc_count": self.doc_count,
            "unique_terms": len(self.idf),
            "avg_doc_length": round(self.avgdl, 1),
            "index_size_entries": sum(len(v) for v in self.inverted_index.values()),
        }


def reciprocal_rank_fusion(rankings, k=60):
    """Fusiona múltiples rankings usando Reciprocal Rank Fusion (RRF).

    Cada ranking es una lista de doc_ids ordenados por relevancia.
    RRF score = sum(1 / (k + rank_i)) para cada ranking i.

    Args:
        rankings: Lista de listas de doc_ids, cada una ordenada por relevancia.
        k: Constante de suavizado (60 es estándar, valor alto = menos impacto del rank).

    Returns:
        Lista de (doc_id, rrf_score) ordenada por score descendente.
    """
    scores = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] += 1.0 / (k + rank)

    result = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return result
