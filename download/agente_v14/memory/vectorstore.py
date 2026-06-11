"""
=============================================================
AGENTE v14 - Vector Store Casero (Optimizado)
=============================================================
Vector store ligero con embeddings de Ollama.
Sin Qdrant, sin ChromaDB, sin dependencias extras.
Persiste en JSON + archivo de vectores.
v14.3: Skip embedding si el store esta vacio, busqueda
       por texto primero (sin embedding), y cache masivo.
=============================================================
"""

import os
import json
import hashlib
import logging
from datetime import datetime

from config import LEARN_DIR, MAX_VECTORS_IN_MEMORY, logger
from llm import ollama

class VectorStore:
    """
    Vector store ligero con carga lazy y cache de vectores.
    Solo carga en memoria los vectores necesarios para busqueda.
    Optimizado para reducir llamadas de embedding innecesarias.
    """

    def __init__(self, store_dir=None):
        self.store_dir = store_dir or os.path.join(LEARN_DIR, "vectors")
        os.makedirs(self.store_dir, exist_ok=True)
        self.index_file = os.path.join(self.store_dir, "index.json")
        self.vectors_file = os.path.join(self.store_dir, "vectors.json")
        self.index = self._load_index()
        self._vectors_cache = None
        self._dirty = False
        self._last_search_cache = {}  # Cache de busquedas recientes

    def _load_index(self):
        try:
            if os.path.exists(self.index_file):
                with open(self.index_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_index(self):
        try:
            with open(self.index_file, "w", encoding="utf-8") as f:
                json.dump(self.index, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _get_vectors(self):
        """Carga los vectores con cache en memoria."""
        if self._vectors_cache is not None:
            return self._vectors_cache
        try:
            if os.path.exists(self.vectors_file):
                with open(self.vectors_file, "r", encoding="utf-8") as f:
                    self._vectors_cache = json.load(f)
                    return self._vectors_cache
        except Exception:
            pass
        self._vectors_cache = {}
        return self._vectors_cache

    def _load_vectors_for(self, entry_ids):
        """Carga solo los vectores de los IDs especificados (lazy loading)."""
        all_vectors = self._get_vectors()
        return {eid: all_vectors[eid] for eid in entry_ids if eid in all_vectors}

    def _save_vectors(self, vectors):
        try:
            with open(self.vectors_file, "w", encoding="utf-8") as f:
                json.dump(vectors, f)
            self._vectors_cache = vectors
        except Exception:
            pass

    def _flush(self):
        if self._dirty:
            self._save_index()
            self._dirty = False

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
        return entry_id

    def _pre_filter(self, query, max_candidates=50):
        """Pre-filtra entradas por texto antes de busqueda semantica."""
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

    def search(self, query, limit=5, min_similarity=0.3):
        """
        Busca entradas semanticamente similares al query.
        Optimizado: si no hay vectores, usa solo busqueda por texto (sin llamar embedding).
        """
        if not self.index:
            return []

        # OPTIMIZACION: Si no hay entradas con vector, solo busqueda por texto
        has_any_vectors = any(e.get("has_vector") for e in self.index)
        if not has_any_vectors:
            return self._text_search(query, limit)

        # Busqueda semantica (con embedding)
        query_embedding = ollama.get_embedding(query)
        if not query_embedding:
            # Fallback: busqueda por texto (sin gastar mas tiempo en embedding)
            return self._text_search(query, limit)

        # Pre-filtrar por texto (rapido, sin cargar todos los vectores)
        candidates = self._pre_filter(query, max_candidates=50)
        if not candidates:
            candidates = self.index[:50]

        # Cargar solo los vectores de los candidatos
        candidate_ids = [c["id"] for c in candidates if c.get("has_vector")]
        vectors = self._load_vectors_for(candidate_ids)

        # Scoring
        scored = []
        for entry in candidates:
            if not entry.get("has_vector") or entry["id"] not in vectors:
                continue
            vec = vectors[entry["id"]]
            score = ollama.cosine_similarity(query_embedding, vec)
            if score >= min_similarity:
                scored.append({**entry, "score": round(score, 3)})

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def _text_search(self, query, limit=5):
        """Busqueda por texto cuando no hay embeddings."""
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
