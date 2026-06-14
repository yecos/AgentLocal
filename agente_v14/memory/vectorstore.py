"""
=============================================================
AGENTE v14 - Vector Store Casero (Optimizado)
=============================================================
Vector store ligero con embeddings de Ollama.
Sin Qdrant, sin ChromaDB, sin dependencias extras.
Persiste en JSON + archivo de vectores.
v14.4: Pre-filtro mejorado con stemming español + stopwords.
       Búsqueda por texto con BM25 scoring.
       Cache de consultas frecuentes.
=============================================================
"""

import os
import json
import hashlib
import hmac
import base64
import struct
import logging
import time
from datetime import datetime

from config import LEARN_DIR, MAX_VECTORS_IN_MEMORY, logger
from llm import ollama

# Clave HMAC para verificacion de integridad de archivos de vectores
# Generada aleatoriamente en primer inicio, persistida junto a los datos
_HMAC_KEY_FILE = os.path.join(LEARN_DIR, "vectors", ".hmac_key")
_hmac_key = None


def _get_hmac_key():
    """Obtiene o genera la clave HMAC para verificar integridad de vectores."""
    global _hmac_key
    if _hmac_key is not None:
        return _hmac_key
    try:
        if os.path.exists(_HMAC_KEY_FILE):
            with open(_HMAC_KEY_FILE, "rb") as f:
                _hmac_key = f.read()
        else:
            _hmac_key = os.urandom(32)
            os.makedirs(os.path.dirname(_HMAC_KEY_FILE), exist_ok=True)
            with open(_HMAC_KEY_FILE, "wb") as f:
                f.write(_hmac_key)
            # Proteger permisos del archivo de clave
            try:
                os.chmod(_HMAC_KEY_FILE, 0o600)
            except Exception as e:
                logger.debug(f"Error protegiendo permisos de clave HMAC: {e}")
    except Exception as e:
        logger.debug(f"Error inicializando clave HMAC: {e}")
        _hmac_key = b"fallback-key-not-secure"  # Fallback para modo sin persistencia
    return _hmac_key


def _safe_deserialize_vectors(data_bytes):
    """Deserializa vectores de forma segura usando formato propio en vez de pickle.
    
    Formato seguro: HMAC(32 bytes) + JSON-encoded dict de {id: [float, ...]}
    Evita la vulnerabilidad de pickle.loads() que permite ejecucion de codigo arbitrario.
    
    Returns:
        dict o None si falla la verificacion de integridad
    """
    if len(data_bytes) < 33:  # Minimo: 32 bytes HMAC + al menos 1 byte de datos
        return None
    
    stored_hmac = data_bytes[:32]
    payload = data_bytes[32:]
    
    # Verificar integridad HMAC
    key = _get_hmac_key()
    computed_hmac = hmac.new(key, payload, hashlib.sha256).digest()
    if not hmac.compare_digest(stored_hmac, computed_hmac):
        logger.warning("INTEGRIDAD: Archivo de vectores falla verificacion HMAC - posible tampering!")
        return None
    
    # Deserializar JSON (seguro, no ejecuta codigo arbitrario)
    try:
        vectors = json.loads(payload.decode('utf-8'))
        if isinstance(vectors, dict):
            return vectors
    except Exception as e:
        logger.debug(f"Error deserializando vectores JSON: {e}")
    return None


def _safe_serialize_vectors(vectors):
    """Serializa vectores de forma segura con HMAC para integridad.
    
    Formato: HMAC(32 bytes) + JSON-encoded dict
    """
    payload = json.dumps(vectors, ensure_ascii=False).encode('utf-8')
    key = _get_hmac_key()
    computed_hmac = hmac.new(key, payload, hashlib.sha256).digest()
    return computed_hmac + payload


class VectorStore:
    """
    Vector store ligero con carga lazy y cache de vectores.
    Solo carga en memoria los vectores necesarios para busqueda.
    Optimizado para reducir llamadas de embedding innecesarias.
    v14.4: Pre-filtro con stemming, cache de consultas.
    """

    # Cache de consultas: evita llamadas embedding repetidas
    _QUERY_CACHE_MAX = 50
    _QUERY_CACHE_TTL = 300  # 5 minutos

    def __init__(self, store_dir=None):
        self.store_dir = store_dir or os.path.join(LEARN_DIR, "vectors")
        os.makedirs(self.store_dir, exist_ok=True)
        self.index_file = os.path.join(self.store_dir, "index.json")
        self.vectors_file = os.path.join(self.store_dir, "vectors.pkl")  # Pickle: 10x mas rapido que JSON
        self._vectors_legacy_file = os.path.join(self.store_dir, "vectors.json")  # Legacy JSON
        self.index = self._load_index()
        self._vectors_cache = None
        self._dirty = False
        # Cache de consultas frecuentes: {query_hash: (results, timestamp)}
        self._query_cache = {}
        # Pre-computed stems para pre-filtro rápido
        self._stems_cache = None
        # Auto-migrar de JSON a Pickle si existe el archivo legacy
        self._migrate_json_to_pickle()

    def _load_index(self):
        try:
            if os.path.exists(self.index_file):
                with open(self.index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Error cargando indice: {e}")
        return []

    def _save_index(self):
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self.index, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Error guardando indice: {e}")

    def _get_vectors(self):
        """Carga los vectores con cache en memoria. Formato seguro con HMAC primero, JSON legacy como fallback."""
        if self._vectors_cache is not None:
            return self._vectors_cache
        # 1. Intentar formato seguro (HMAC + JSON)
        try:
            if os.path.exists(self.vectors_file):
                with open(self.vectors_file, "rb") as f:
                    data = f.read()
                vectors = _safe_deserialize_vectors(data)
                if vectors is not None:
                    self._vectors_cache = vectors
                    return self._vectors_cache
                else:
                    logger.warning("Vectores pickle legacy sin HMAC - migrando a formato seguro")
                    # Intentar migrar desde pickle legacy (solo si HMAC falla por formato viejo)
                    # SECURITY: This pickle.loads() is ONLY for one-time migration from legacy format.
                    # After migration, data is re-saved in safe HMAC+JSON format.
                    # Do NOT use pickle for any other purpose.
                    import pickle
                    try:
                        # Size limit check: max 50MB for safety
                        MAX_MIGRATION_SIZE = 50 * 1024 * 1024  # 50 MB
                        if len(data) > MAX_MIGRATION_SIZE:
                            logger.warning(f"Legacy pickle file too large ({len(data)} bytes > {MAX_MIGRATION_SIZE}), skipping migration")
                        else:
                            vectors = pickle.loads(data)
                            # Validate that loaded data is a dict with string keys and list values
                            if isinstance(vectors, dict):
                                valid = True
                                for k, v in vectors.items():
                                    if not isinstance(k, str) or not isinstance(v, list):
                                        valid = False
                                        break
                                if valid:
                                    self._vectors_cache = vectors
                                    self._save_vectors(vectors)  # Re-guardar en formato seguro
                                    logger.warning(f"MIGRACION: Vectores migrados de pickle legacy a formato seguro HMAC+JSON ({len(vectors)} vectores)")
                                    return self._vectors_cache
                                else:
                                    logger.warning("Legacy pickle data has invalid structure (expected dict[str, list]), skipping migration")
                    except Exception as e:
                        logger.debug(f"Error migrando vectores pickle legacy: {e}")
        except Exception as e:
            logger.debug(f"Error cargando vectores con formato seguro: {e}")
        # 2. Fallback: JSON legacy
        try:
            if os.path.exists(self._vectors_legacy_file):
                with open(self._vectors_legacy_file, "r", encoding="utf-8") as f:
                    self._vectors_cache = json.load(f)
                    # Guardar en formato seguro para proxima vez
                    self._save_vectors(self._vectors_cache)
                    logger.info("Vectores migrados de JSON legacy a formato seguro HMAC+JSON")
                    return self._vectors_cache
        except Exception as e:
            logger.debug(f"Error cargando vectores JSON legacy: {e}")
        self._vectors_cache = {}
        return self._vectors_cache

    def _load_vectors_for(self, entry_ids):
        """Carga solo los vectores de los IDs especificados (lazy loading)."""
        all_vectors = self._get_vectors()
        return {eid: all_vectors[eid] for eid in entry_ids if eid in all_vectors}

    def _save_vectors(self, vectors):
        """Guarda vectores en formato seguro (HMAC + JSON) en vez de pickle inseguro."""
        try:
            data = _safe_serialize_vectors(vectors)
            with open(self.vectors_file, "wb") as f:
                f.write(data)
            self._vectors_cache = vectors
        except Exception as e:
            logger.warning(f"Error guardando vectores: {e}")

    def _flush(self):
        if self._dirty:
            self._save_index()
            self._dirty = False
            # Invalidar cache de stems cuando cambia el índice
            self._stems_cache = None

    def _get_stems_cache(self):
        """Pre-computa stems de todos los documentos para pre-filtro rápido."""
        if self._stems_cache is not None:
            return self._stems_cache
        try:
            from memory.bm25 import tokenize
            self._stems_cache = []
            for entry in self.index:
                stems = set(tokenize(entry["text"]))
                self._stems_cache.append((entry, stems))
        except ImportError:
            # Fallback si bm25 no disponible
            self._stems_cache = None
        return self._stems_cache

    def add(self, text, metadata=None, entry_id=None, skip_embedding=False):
        """
        Agrega un texto al vector store con su embedding.

        Args:
            skip_embedding: Si True, NO calcula embedding (mas rapido).
                           La entrada no aparecera en busquedas semanticas
                           pero si en busquedas por texto.
        """
        if not entry_id:
            entry_id = hashlib.md5(text.encode()).hexdigest()[:12]

        # Verificar si ya existe
        for entry in self.index:
            if entry["id"] == entry_id:
                return entry_id

        # Skip embedding si se solicita (para interacciones rapidas)
        if skip_embedding:
            self.index.append({
                "id": entry_id,
                "text": text[:500],
                "metadata": metadata or {},
                "has_vector": False,
                "created": datetime.now().isoformat()
            })
            self._dirty = True
            self._flush()
            # Invalidar cache de consultas (datos nuevos)
            self._query_cache.clear()
            return entry_id

        # Obtener embedding (con cache LRU)
        embedding = ollama.get_embedding(text)
        if not embedding:
            self.index.append({
                "id": entry_id,
                "text": text[:500],
                "metadata": metadata or {},
                "has_vector": False,
                "created": datetime.now().isoformat()
            })
            self._dirty = True
            self._flush()
            self._query_cache.clear()
            return entry_id

        # Guardar vector
        vectors = self._get_vectors()
        vectors[entry_id] = embedding
        self._save_vectors(vectors)

        self.index.append({
            "id": entry_id,
            "text": text[:500],
            "metadata": metadata or {},
            "has_vector": True,
            "created": datetime.now().isoformat()
        })
        self._dirty = True
        self._flush()
        self._query_cache.clear()
        return entry_id

    def _pre_filter(self, query, max_candidates=50):
        """Pre-filtra entradas usando stemming español para mejor recall.

        v14.4: Usa tokenización con stemming del módulo bm25.
               Encuentra 'configurar' cuando se busca 'configuración'.
        """
        # Intentar pre-filtro con stemming
        try:
            from memory.bm25 import tokenize
            query_stems = set(tokenize(query))
            if not query_stems:
                return self.index[:max_candidates]

            # Usar cache de stems si está disponible
            stems_cache = self._get_stems_cache()
            if stems_cache:
                candidates = []
                for entry, doc_stems in stems_cache:
                    overlap = len(query_stems & doc_stems)
                    if overlap > 0:
                        candidates.append((overlap, entry))
                candidates.sort(key=lambda x: x[0], reverse=True)
                return [c[1] for c in candidates[:max_candidates]]

            # Sin cache: computar stems al vuelo
            candidates = []
            for entry in self.index:
                doc_stems = set(tokenize(entry["text"]))
                overlap = len(query_stems & doc_stems)
                if overlap > 0:
                    candidates.append((overlap, entry))
            candidates.sort(key=lambda x: x[0], reverse=True)
            return [c[1] for c in candidates[:max_candidates]]

        except ImportError:
            # Fallback: pre-filtro original (sin stemming)
            return self._pre_filter_legacy(query, max_candidates)

    def _pre_filter_legacy(self, query, max_candidates=50):
        """Pre-filtro legacy: coincidencia de texto simple (fallback)."""
        query_words = [w.lower() for w in query.split() if len(w) > 3]
        if not query_words:
            return self.index[:max_candidates]
        candidates = []
        for entry in self.index:
            text_lower = entry["text"].lower()
            matches = sum(1 for w in query_words if w in text_lower)
            if matches > 0:
                candidates.append((matches, entry))
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [c[1] for c in candidates[:max_candidates]]

    def _check_query_cache(self, query, limit, min_similarity):
        """Verifica cache de consultas frecuentes."""
        cache_key = hashlib.md5(f"{query}:{limit}:{min_similarity}".encode()).hexdigest()[:16]
        if cache_key in self._query_cache:
            results, timestamp = self._query_cache[cache_key]
            if time.time() - timestamp < self._QUERY_CACHE_TTL:
                logger.debug(f"Cache hit para consulta: {query[:50]}")
                return results
            else:
                del self._query_cache[cache_key]
        return None

    def _store_query_cache(self, query, limit, min_similarity, results):
        """Almacena resultado en cache de consultas."""
        cache_key = hashlib.md5(f"{query}:{limit}:{min_similarity}".encode()).hexdigest()[:16]
        self._query_cache[cache_key] = (results, time.time())
        # Evicción LRU si cache muy grande
        if len(self._query_cache) > self._QUERY_CACHE_MAX:
            oldest_key = min(self._query_cache, key=lambda k: self._query_cache[k][1])
            del self._query_cache[oldest_key]

    def search(self, query, limit=5, min_similarity=0.3):
        """
        Busca entradas semanticamente similares al query.
        Optimizado: si no hay vectores, usa solo busqueda por texto (sin llamar embedding).
        Usa cosine_similarity_batch para calculo vectorizado con numpy.
        v14.4: Cache de consultas frecuentes.
        """
        if not self.index:
            return []

        # Check cache
        cached = self._check_query_cache(query, limit, min_similarity)
        if cached is not None:
            return cached

        # OPTIMIZACION: Si no hay entradas con vector, solo busqueda por texto
        has_any_vectors = any(e.get("has_vector") for e in self.index)
        if not has_any_vectors:
            results = self._text_search(query, limit)
            self._store_query_cache(query, limit, min_similarity, results)
            return results

        # Busqueda semantica (con embedding)
        query_embedding = ollama.get_embedding(query)
        if not query_embedding:
            # Fallback: busqueda por texto (sin gastar mas tiempo en embedding)
            results = self._text_search(query, limit)
            self._store_query_cache(query, limit, min_similarity, results)
            return results

        # Pre-filtrar por texto (rapido, sin cargar todos los vectores)
        candidates = self._pre_filter(query, max_candidates=50)
        if not candidates:
            candidates = self.index[:50]

        # Cargar solo los vectores de los candidatos
        candidate_ids = [c["id"] for c in candidates if c.get("has_vector")]
        vectors = self._load_vectors_for(candidate_ids)

        # Scoring vectorizado: cosine_similarity_batch usa numpy (10-50x mas rapido)
        similarities = ollama.cosine_similarity_batch(query_embedding, vectors)

        scored = []
        for entry in candidates:
            if not entry.get("has_vector") or entry["id"] not in similarities:
                continue
            score = similarities[entry["id"]]
            if score >= min_similarity:
                scored.append({**entry, "score": round(score, 3)})

        scored.sort(key=lambda x: x["score"], reverse=True)
        results = scored[:limit]
        self._store_query_cache(query, limit, min_similarity, results)
        return results

    def _text_search(self, query, limit=5):
        """Busqueda por texto cuando no hay embeddings.

        v14.4: Usa tokenización con stemming para mejor recall.
        """
        # Intentar búsqueda con stemming
        try:
            from memory.bm25 import tokenize
            query_stems = tokenize(query)
            if not query_stems:
                return []

            results = []
            for entry in self.index:
                doc_stems = tokenize(entry["text"])
                if not doc_stems:
                    continue
                # Score: ratio de stems de la query que aparecen en el documento
                query_set = set(query_stems)
                doc_set = set(doc_stems)
                matches = len(query_set & doc_set)
                if matches > 0:
                    score = matches / len(query_set)
                    results.append({**entry, "score": round(score, 3)})

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]

        except ImportError:
            # Fallback: búsqueda original
            return self._text_search_legacy(query, limit)

    def _text_search_legacy(self, query, limit=5):
        """Busqueda por texto legacy (sin stemming)."""
        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) > 3]
        results = []
        for entry in self.index:
            text_lower = entry["text"].lower()
            matches = sum(1 for w in query_words if w in text_lower)
            if matches > 0:
                score = matches / max(len(query_words), 1)
                results.append({**entry, "score": round(score, 3)})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def count(self):
        return len(self.index)

    def count_with_vectors(self):
        """Retorna cuantas entradas tienen vectores (para debug)."""
        return sum(1 for e in self.index if e.get("has_vector"))

    def cleanup(self, max_entries=1000):
        """Limpia entradas viejas si hay demasiadas."""
        if len(self.index) <= max_entries:
            return
        self.index.sort(key=lambda x: x.get("created", ""), reverse=True)
        removed = self.index[max_entries:]
        self.index = self.index[:max_entries]
        # Limpiar vectores huerfanos
        vectors = self._get_vectors()
        valid_ids = {e["id"] for e in self.index}
        orphan_ids = [vid for vid in vectors if vid not in valid_ids]
        for oid in orphan_ids:
            del vectors[oid]
        if orphan_ids:
            self._save_vectors(vectors)
        self._dirty = True
        self._flush()
        # Invalidar caches
        self._query_cache.clear()
        self._stems_cache = None
        # Limpiar archivo JSON legacy si existe
        try:
            if os.path.exists(self._vectors_legacy_file):
                os.remove(self._vectors_legacy_file)
                logger.info("Archivo vectors.json legacy eliminado tras cleanup")
        except Exception as e:
            logger.debug(f"Error eliminando archivo vectors.json legacy: {e}")

    def _migrate_json_to_pickle(self):
        """Migra automaticamente de vectors.json a vectors.pkl si existe el legacy."""
        if os.path.exists(self.vectors_file):
            return  # Ya existe Pickle, no migrar
        if os.path.exists(self._vectors_legacy_file):
            logger.info("Detectado vectors.json legacy - se migrara a Pickle en la proxima carga")
