"""
=============================================================
AGENTE v14 - Vector Store con ChromaDB
=============================================================
Vector store profesional con ChromaDB como backend.
Fallback automatico al VectorStore casero si ChromaDB no esta.
- Busqueda semantica rapida y escalable
- Decaimiento temporal de recuerdos
- Deduplicacion semantica
- Auto-cleanup
=============================================================
"""

import os
import json
import hashlib
import logging
from datetime import datetime

from config import LEARN_DIR, MAX_VECTORS_IN_MEMORY, logger

# Intentar importar ChromaDB
try:
    import chromadb
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logger.info("ChromaDB no instalado. Usando VectorStore casero (fallback).")

if CHROMADB_AVAILABLE:
    from llm import ollama


class ChromaVectorStore:
    """
    Vector store basado en ChromaDB con decaimiento temporal y deduplicacion.
    Escalable a miles de documentos con busqueda semantica rapida.
    """

    DECAY_HALF_LIFE_DAYS = 30  # Los recuerdos pierden la mitad de relevancia en 30 dias

    def __init__(self, store_dir=None):
        self.store_dir = store_dir or os.path.join(LEARN_DIR, "vectors")
        os.makedirs(self.store_dir, exist_ok=True)

        # Inicializar ChromaDB
        self._client = chromadb.PersistentClient(path=self.store_dir)
        self._collection = self._client.get_or_create_collection(
            name="agent_memory",
            metadata={"hnsw:space": "cosine"}
        )
        self._index_meta = self._load_meta()
        logger.info(f"ChromaDB inicializado: {self._collection.count()} documentos")

    def _load_meta(self):
        """Carga metadatos adicionales (timestamp para decaimiento)."""
        meta_file = os.path.join(self.store_dir, "meta.json")
        try:
            if os.path.exists(meta_file):
                with open(meta_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return {}

    def _save_meta(self):
        """Guarda metadatos adicionales."""
        meta_file = os.path.join(self.store_dir, "meta.json")
        try:
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(self._index_meta, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _compute_decay(self, created_at, now=None):
        """
        Computa el factor de decaimiento temporal.
        Los recuerdos recientes pesan mas que los viejos.
        Retorna un valor entre 0 y 1.
        """
        if not created_at:
            return 0.5
        try:
            created = datetime.fromisoformat(created_at)
            if now is None:
                now = datetime.now()
            days_old = (now - created).total_seconds() / 86400
            # Decaimiento exponencial
            import math
            decay = math.exp(-0.693 * days_old / self.DECAY_HALF_LIFE_DAYS)
            return max(decay, 0.1)  # Minimo 10% de relevancia
        except Exception:
            return 0.5

    def _is_duplicate(self, text, threshold=0.95):
        """
        Verifica si un texto es duplicado semantico de uno existente.
        Usa embeddings para comparar.
        """
        embedding = ollama.get_embedding(text)
        if not embedding:
            return False

        try:
            results = self._collection.query(
                query_embeddings=[embedding],
                n_results=1,
                include=["distances"]
            )
            if results and results["distances"] and results["distances"][0]:
                # ChromaDB con cosine space: distance < (1 - threshold) = duplicado
                distance = results["distances"][0][0]
                similarity = 1 - distance
                return similarity >= threshold
        except Exception:
            pass
        return False

    def add(self, text, metadata=None, entry_id=None, skip_embedding=False):
        """Agrega un texto al vector store con su embedding.
        
        Args:
            skip_embedding: Si True, NO calcula embedding (mas rapido).
                           La entrada solo aparecera en busquedas por texto.
        """
        if not entry_id:
            entry_id = hashlib.md5(text.encode()).hexdigest()[:12]

        # Verificar duplicado existente en ChromaDB
        try:
            existing = self._collection.get(ids=[entry_id])
            if existing and existing["ids"]:
                return entry_id
        except Exception:
            pass

        # Verificar duplicado semantico (solo si tenemos embedding)
        if not skip_embedding and self._is_duplicate(text):
            logger.debug(f"Texto duplicado semantico, saltando: {text[:50]}...")
            return entry_id

        now = datetime.now().isoformat()

        # Metadatos con timestamp para decaimiento
        meta = metadata or {}
        meta["created"] = now
        meta["text_preview"] = text[:100]

        # Si skip_embedding, guardar solo con metadatos (sin calculo de embedding)
        if skip_embedding:
            meta["no_embedding"] = True
            self._collection.add(
                ids=[entry_id],
                documents=[text[:500]],
                metadatas=[meta]
            )
            return entry_id

        # Obtener embedding
        embedding = ollama.get_embedding(text)

        if embedding:
            self._collection.add(
                ids=[entry_id],
                embeddings=[embedding],
                documents=[text[:500]],
                metadatas=[meta]
            )
        else:
            # Sin embedding, guardar solo con metadatos
            meta["no_embedding"] = True
            self._collection.add(
                ids=[entry_id],
                documents=[text[:500]],
                metadatas=[meta]
            )

        return entry_id

    def search(self, query, limit=5, min_similarity=0.3):
        """Busca entradas semanticamente similares con decaimiento temporal."""
        query_embedding = ollama.get_embedding(query)
        if not query_embedding:
            return self._text_search(query, limit)

        try:
            # Buscar mas candidatos de los necesarios para re-rankear con decaimiento
            n_candidates = min(limit * 3, 20)
            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=n_candidates,
                include=["documents", "metadatas", "distances"]
            )

            if not results or not results["ids"] or not results["ids"][0]:
                return self._text_search(query, limit)

            scored = []
            now = datetime.now()
            for i, doc_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i]
                similarity = 1 - distance

                # Aplicar decaimiento temporal
                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                created_at = meta.get("created", "")
                decay = self._compute_decay(created_at, now)

                # Score final = similitud * decaimiento
                final_score = similarity * decay

                if final_score >= min_similarity * 0.5:  # Umbral mas bajo tras decaimiento
                    scored.append({
                        "id": doc_id,
                        "text": results["documents"][0][i] if results["documents"] else "",
                        "metadata": meta,
                        "has_vector": True,
                        "score": round(final_score, 3),
                        "raw_similarity": round(similarity, 3),
                        "decay": round(decay, 3),
                    })

            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:limit]

        except Exception as e:
            logger.warning(f"Error en busqueda ChromaDB: {e}")
            return self._text_search(query, limit)

    def _text_search(self, query, limit=5):
        """Busqueda por texto cuando no hay embeddings."""
        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) > 3]

        if not query_words:
            return []

        try:
            # ChromaDB no tiene text search nativo, obtener todos y filtrar
            all_docs = self._collection.get(include=["documents", "metadatas"])
            results = []

            for i, doc in enumerate(all_docs["documents"]):
                doc_lower = doc.lower()
                matches = sum(1 for w in query_words if w in doc_lower)
                if matches > 0:
                    score = matches / max(len(query_words), 1)
                    meta = all_docs["metadatas"][i] if all_docs["metadatas"] else {}
                    results.append({
                        "id": all_docs["ids"][i],
                        "text": doc,
                        "metadata": meta,
                        "has_vector": not meta.get("no_embedding", False),
                        "score": round(score, 3),
                    })

            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:limit]
        except Exception:
            return []

    def count(self):
        """Retorna el numero de documentos en el store."""
        try:
            return self._collection.count()
        except Exception:
            return 0

    def cleanup(self, max_entries=1000):
        """Limpia entradas viejas si hay demasiadas."""
        current = self.count()
        if current <= max_entries:
            return

        try:
            # Obtener todos los documentos con metadatos
            all_docs = self._collection.get(include=["metadatas"])

            # Ordenar por fecha de creacion
            entries_with_dates = []
            for i, entry_id in enumerate(all_docs["ids"]):
                meta = all_docs["metadatas"][i] if all_docs["metadatas"] else {}
                created = meta.get("created", "2000-01-01")
                entries_with_dates.append((entry_id, created))

            entries_with_dates.sort(key=lambda x: x[1])

            # Eliminar los mas viejos
            to_remove = entries_with_dates[:current - max_entries]
            if to_remove:
                ids_to_remove = [e[0] for e in to_remove]
                self._collection.delete(ids=ids_to_remove)
                logger.info(f"Cleanup: eliminados {len(ids_to_remove)} documentos viejos")
        except Exception as e:
            logger.warning(f"Error en cleanup: {e}")


class SimpleVectorStore:
    """
    Vector store casero (fallback cuando ChromaDB no esta instalado).
    Persiste en JSON + archivo de vectores.
    Incluye decaimiento temporal y deduplicacion basica.
    """

    DECAY_HALF_LIFE_DAYS = 30

    def __init__(self, store_dir=None):
        self.store_dir = store_dir or os.path.join(LEARN_DIR, "vectors")
        os.makedirs(self.store_dir, exist_ok=True)
        self.index_file = os.path.join(self.store_dir, "index.json")
        self.vectors_file = os.path.join(self.store_dir, "vectors.json")
        self.index = self._load_index()
        self._vectors_cache = None
        self._dirty = False

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

    def _compute_decay(self, created_at):
        if not created_at:
            return 0.5
        try:
            created = datetime.fromisoformat(created_at)
            days_old = (datetime.now() - created).total_seconds() / 86400
            import math
            decay = math.exp(-0.693 * days_old / self.DECAY_HALF_LIFE_DAYS)
            return max(decay, 0.1)
        except Exception:
            return 0.5

    def add(self, text, metadata=None, entry_id=None, skip_embedding=False):
        """Agrega un texto al vector store con su embedding.
        
        Args:
            skip_embedding: Si True, NO calcula embedding (mas rapido).
                           La entrada solo aparecera en busquedas por texto.
        """
        if not entry_id:
            entry_id = hashlib.md5(text.encode()).hexdigest()[:12]

        # Verificar si ya existe
        for entry in self.index:
            if entry["id"] == entry_id:
                return entry_id

        # Deduplicacion basica por texto similar
        text_lower = text[:100].lower()
        for entry in self.index:
            if entry["text"][:100].lower() == text_lower:
                return entry["id"]

        now = datetime.now().isoformat()

        # Si skip_embedding, guardar sin vector (mas rapido)
        if skip_embedding:
            self.index.append({
                "id": entry_id,
                "text": text[:500],
                "metadata": metadata or {},
                "has_vector": False,
                "created": now
            })
            self._dirty = True
            self._flush()
            return entry_id

        embedding = ollama.get_embedding(text)

        if not embedding:
            self.index.append({
                "id": entry_id,
                "text": text[:500],
                "metadata": metadata or {},
                "has_vector": False,
                "created": now
            })
            self._dirty = True
            self._flush()
            return entry_id

        vectors = self._get_vectors()
        vectors[entry_id] = embedding
        self._save_vectors(vectors)

        self.index.append({
            "id": entry_id,
            "text": text[:500],
            "metadata": metadata or {},
            "has_vector": True,
            "created": now
        })
        self._dirty = True
        self._flush()
        return entry_id

    def search(self, query, limit=5, min_similarity=0.3):
        if not self.index:
            return []

        query_embedding = ollama.get_embedding(query)
        if not query_embedding:
            return self._text_search(query, limit)

        candidates = self._pre_filter(query, max_candidates=50)
        if not candidates:
            candidates = self.index[:50]

        candidate_ids = [c["id"] for c in candidates if c.get("has_vector")]
        vectors = self._load_vectors_for(candidate_ids)

        scored = []
        for entry in candidates:
            if not entry.get("has_vector") or entry["id"] not in vectors:
                continue
            vec = vectors[entry["id"]]
            raw_sim = ollama.cosine_similarity(query_embedding, vec)

            # Aplicar decaimiento temporal
            decay = self._compute_decay(entry.get("created", ""))
            final_score = raw_sim * decay

            if final_score >= min_similarity * 0.5:
                scored.append({
                    **entry,
                    "score": round(final_score, 3),
                    "raw_similarity": round(raw_sim, 3),
                    "decay": round(decay, 3),
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def _pre_filter(self, query, max_candidates=50):
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

    def _text_search(self, query, limit=5):
        query_lower = query.lower()
        query_words = [w for w in query_lower.split() if len(w) > 3]
        results = []
        for entry in self.index:
            text_lower = entry["text"].lower()
            matches = sum(1 for w in query_words if w in text_lower)
            if matches > 0:
                decay = self._compute_decay(entry.get("created", ""))
                score = (matches / max(len(query_words), 1)) * decay
                results.append({**entry, "score": round(score, 3)})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def count(self):
        return len(self.index)

    def cleanup(self, max_entries=1000):
        if len(self.index) <= max_entries:
            return
        self.index.sort(key=lambda x: x.get("created", ""), reverse=True)
        removed = self.index[max_entries:]
        self.index = self.index[:max_entries]
        vectors = self._get_vectors()
        valid_ids = {e["id"] for e in self.index}
        orphan_ids = [vid for vid in vectors if vid not in valid_ids]
        for oid in orphan_ids:
            del vectors[oid]
        if orphan_ids:
            self._save_vectors(vectors)
        self._dirty = True
        self._flush()


# ============================================================
# FACTORY: Retorna ChromaVectorStore o SimpleVectorStore
# ============================================================
def create_vector_store(store_dir=None):
    """Factory que retorna el mejor vector store disponible."""
    if CHROMADB_AVAILABLE:
        try:
            store = ChromaVectorStore(store_dir=store_dir)
            logger.info("Usando ChromaDB como vector store")
            return store
        except Exception as e:
            logger.warning(f"Error inicializando ChromaDB, fallback a casero: {e}")

    logger.info("Usando VectorStore casero como fallback")
    return SimpleVectorStore(store_dir=store_dir)
