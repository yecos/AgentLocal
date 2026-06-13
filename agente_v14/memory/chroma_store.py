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
from memory.vectorstore import VectorStore

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
    v3: Auto-deteccion robusta y recreacion ante mismatch de dimensiones de embeddings.
        Catch-all de errores de dimension para que NUNCA crashee el agente.
    """

    DECAY_HALF_LIFE_DAYS = 30  # Los recuerdos pierden la mitad de relevancia en 30 dias
    MAX_RECREATE_RETRIES = 2   # Max reintentos al recrear coleccion por dimension mismatch

    def __init__(self, store_dir=None):
        self.store_dir = store_dir or os.path.join(LEARN_DIR, "vectors")
        os.makedirs(self.store_dir, exist_ok=True)

        # Detectar dimension del modelo de embedding actual
        self._embedding_dim = self._detect_embedding_dimension()

        # Inicializar ChromaDB
        self._client = chromadb.PersistentClient(path=self.store_dir)

        # Obtener o crear coleccion con validacion de dimensiones
        self._collection = self._get_or_create_collection()

        # Validacion post-init: verificar que las dimensiones coinciden
        self._validate_collection_dimension()

        self._index_meta = self._load_meta()
        logger.info(f"ChromaDB inicializado: {self._collection.count()} documentos (dim={self._embedding_dim})")

    def _detect_embedding_dimension(self):
        """Detecta la dimension de los embeddings del modelo actual."""
        try:
            test_embedding = ollama.get_embedding("test")
            if test_embedding and isinstance(test_embedding, list):
                return len(test_embedding)
        except Exception as e:
            logger.debug(f"No se pudo detectar dimension del embedding: {e}")
        return None

    def _get_collection_dimension(self, collection):
        """Intenta obtener la dimension de embeddings de una coleccion existente."""
        try:
            metadata = collection.metadata
            if metadata and "hnsw:dim" in metadata:
                return int(metadata["hnsw:dim"])
        except Exception:
            pass
        try:
            peek_result = collection.peek(limit=1)
            if peek_result and peek_result.get("embeddings") and len(peek_result["embeddings"]) > 0:
                return len(peek_result["embeddings"][0])
        except Exception:
            pass
        return None

    def _validate_collection_dimension(self):
        """Validacion post-inicializacion: prueba insertar y buscar un vector de prueba.
        Si falla por dimension mismatch, recrea la coleccion automaticamente.
        Esto atrapa casos donde _get_or_create_collection no detecto el mismatch.
        """
        if self._embedding_dim is None:
            return
        try:
            # Intentar una operacion de query con un vector de la dimension actual
            test_vec = [0.0] * self._embedding_dim
            self._collection.query(
                query_embeddings=[test_vec],
                n_results=1,
                include=["distances"]
            )
            logger.debug("Validacion de dimensiones ChromaDB: OK")
        except Exception as e:
            err_msg = str(e).lower()
            if "dimension" in err_msg or "dim" in err_msg:
                logger.warning(
                    f"⚠️ MISMATCH DETECTADO EN VALIDACION POST-INIT: {e}. "
                    f"Recreando coleccion con dim={self._embedding_dim}..."
                )
                self._force_recreate_collection()
            else:
                logger.debug(f"Validacion ChromaDB fallo (no es dimension): {e}")

    def _force_recreate_collection(self):
        """Fuerza la recreacion de la coleccion, eliminando datos previos."""
        try:
            self._client.delete_collection(name="agent_memory")
            logger.info("Coleccion 'agent_memory' eliminada para recreacion")
        except Exception:
            pass
        metadata = {"hnsw:space": "cosine"}
        if self._embedding_dim is not None:
            metadata["hnsw:dim"] = self._embedding_dim
        self._collection = self._client.create_collection(name="agent_memory", metadata=metadata)
        logger.info(f"Coleccion recreada con dim={self._embedding_dim}")

    def _get_or_create_collection(self):
        """Obtiene o crea la coleccion, manejando mismatch de dimensiones."""
        try:
            existing = self._client.get_collection(name="agent_memory")

            # Verificar dimensiones si las conocemos
            if self._embedding_dim is not None:
                existing_dim = self._get_collection_dimension(existing)

                if existing_dim is not None and existing_dim != self._embedding_dim:
                    logger.warning(
                        f"⚠️ MISMATCH DE DIMENSIONES: coleccion espera {existing_dim} dim, "
                        f"modelo actual produce {self._embedding_dim} dim. Recreando coleccion..."
                    )
                    self._client.delete_collection(name="agent_memory")
                    logger.info(f"Coleccion eliminada. Creando nueva con dim={self._embedding_dim}")
                    return self._client.create_collection(
                        name="agent_memory",
                        metadata={"hnsw:space": "cosine", "hnsw:dim": self._embedding_dim}
                    )

            return existing

        except Exception:
            # La coleccion no existe — crear nueva
            metadata = {"hnsw:space": "cosine"}
            if self._embedding_dim is not None:
                metadata["hnsw:dim"] = self._embedding_dim
            return self._client.create_collection(name="agent_memory", metadata=metadata)

    def _load_meta(self):
        """Carga metadatos adicionales (timestamp para decaimiento)."""
        meta_file = os.path.join(self.store_dir, "meta.json")
        try:
            if os.path.exists(meta_file):
                with open(meta_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.debug(f"Error cargando metadatos: {e}")
        return {}

    def _save_meta(self):
        """Guarda metadatos adicionales."""
        meta_file = os.path.join(self.store_dir, "meta.json")
        try:
            with open(meta_file, "w", encoding="utf-8") as f:
                json.dump(self._index_meta, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug(f"Error guardando metadatos: {e}")

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
        except Exception as e:
            logger.debug(f"Error computando decaimiento: {e}")
            return 0.5

    def _is_duplicate(self, text, threshold=0.95):
        """
        Verifica si un texto es duplicado semantico de uno existente.
        Usa embeddings para comparar.
        v3: Catch de errores de dimension para no crashear.
        """
        embedding = ollama.get_embedding(text)
        if not embedding:
            return False

        # Verificar dimension antes de consultar
        if self._embedding_dim is not None and len(embedding) != self._embedding_dim:
            logger.debug(f"Dimension mismatch en _is_duplicate, saltando verificacion")
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
        except Exception as e:
            err_msg = str(e).lower()
            if "dimension" in err_msg or "dim" in err_msg:
                logger.warning(f"Dimension mismatch en _is_duplicate, recreando coleccion...")
                try:
                    self._handle_dimension_error(embedding)
                except Exception:
                    pass
            else:
                logger.debug(f"Error verificando duplicado semantico: {e}")
        return False

    def add(self, text, metadata=None, entry_id=None, skip_embedding=False):
        """Agrega un texto al vector store con su embedding.
        
        Args:
            skip_embedding: Si True, NO calcula embedding (mas rapido).
                           La entrada solo aparecera en busquedas por texto.
        v3: Catch-all de errores de dimension con reintento automatico.
        """
        if not entry_id:
            entry_id = hashlib.md5(text.encode()).hexdigest()[:12]

        # Verificar duplicado existente en ChromaDB
        try:
            existing = self._collection.get(ids=[entry_id])
            if existing and existing["ids"]:
                return entry_id
        except Exception as e:
            logger.debug(f"Error verificando entrada existente en ChromaDB: {e}")

        # Verificar duplicado semantico (solo si tenemos embedding y no skip)
        if not skip_embedding:
            try:
                if self._is_duplicate(text):
                    logger.debug(f"Texto duplicado semantico, saltando: {text[:50]}...")
                    return entry_id
            except Exception as e:
                logger.debug(f"Error verificando duplicado semantico: {e}")

        now = datetime.now().isoformat()

        # Metadatos con timestamp para decaimiento
        meta = metadata or {}
        meta["created"] = now
        meta["text_preview"] = text[:100]

        # Si skip_embedding, guardar solo con metadatos (sin calculo de embedding)
        if skip_embedding:
            meta["no_embedding"] = True
            try:
                self._collection.add(
                    ids=[entry_id],
                    documents=[text[:500]],
                    metadatas=[meta]
                )
            except Exception as e:
                logger.debug(f"Error agregando sin embedding a ChromaDB: {e}")
            return entry_id

        # Obtener embedding
        embedding = ollama.get_embedding(text)

        if embedding:
            # Actualizar dimension si es la primera vez que obtenemos un embedding valido
            if self._embedding_dim is None:
                self._embedding_dim = len(embedding)
                logger.info(f"Dimension de embedding detectada dinamicamente: {self._embedding_dim}")

            # Validar dimension del embedding antes de insertar
            if len(embedding) != self._embedding_dim:
                logger.warning(
                    f"Embedding con dimension incorrecta ({len(embedding)} vs {self._embedding_dim}). "
                    f"Actualizando dimension y recreando coleccion..."
                )
                self._handle_dimension_error(embedding)

            # Intentar insertar con catch-all de errores de dimension
            for attempt in range(self.MAX_RECREATE_RETRIES + 1):
                try:
                    self._collection.add(
                        ids=[entry_id],
                        embeddings=[embedding],
                        documents=[text[:500]],
                        metadatas=[meta]
                    )
                    return entry_id
                except Exception as e:
                    err_msg = str(e).lower()
                    if "dimension" in err_msg or "dim" in err_msg:
                        if attempt < self.MAX_RECREATE_RETRIES:
                            logger.warning(
                                f"Error de dimension al insertar (intento {attempt + 1}). "
                                f"Recreando coleccion..."
                            )
                            self._handle_dimension_error(embedding)
                        else:
                            logger.error(
                                f"No se pudo resolver error de dimension tras {attempt + 1} intentos. "
                                f"Guardando sin embedding."
                            )
                            # Fallback: guardar sin embedding para no perder el dato
                            meta["no_embedding"] = True
                            try:
                                self._collection.add(
                                    ids=[entry_id],
                                    documents=[text[:500]],
                                    metadatas=[meta]
                                )
                            except Exception:
                                pass
                            return entry_id
                    else:
                        logger.debug(f"Error al insertar en ChromaDB (no dimension): {e}")
                        return entry_id
        else:
            # Sin embedding, guardar solo con metadatos
            meta["no_embedding"] = True
            try:
                self._collection.add(
                    ids=[entry_id],
                    documents=[text[:500]],
                    metadatas=[meta]
                )
            except Exception as e:
                logger.debug(f"Error agregando sin embedding a ChromaDB: {e}")

        return entry_id

    def _handle_dimension_error(self, sample_embedding=None):
        """Maneja error de dimension recreando la coleccion.
        v3: Actualiza _embedding_dim con la dimension real del embedding recibido.
        """
        new_dim = len(sample_embedding) if sample_embedding else self._embedding_dim
        if new_dim:
            self._embedding_dim = new_dim
        logger.warning(
            f"Recreando coleccion 'agent_memory' con dim={new_dim} "
            f"(datos previos se pierden para evitar errores de dimension)"
        )
        try:
            self._client.delete_collection(name="agent_memory")
        except Exception:
            pass
        metadata = {"hnsw:space": "cosine"}
        if new_dim:
            metadata["hnsw:dim"] = new_dim
        try:
            self._collection = self._client.create_collection(name="agent_memory", metadata=metadata)
            logger.info(f"Coleccion recreada exitosamente con dim={new_dim}")
        except Exception as e:
            logger.error(f"Error recreando coleccion: {e}")

    def get_info(self):
        """Retorna info de diagnostico de la coleccion."""
        existing_dim = self._get_collection_dimension(self._collection)
        return {
            "document_count": self.count(),
            "collection_dimension": existing_dim,
            "model_dimension": self._embedding_dim,
            "dimensions_match": existing_dim == self._embedding_dim if existing_dim and self._embedding_dim else "unknown",
            "persist_dir": self.store_dir,
        }

    def search(self, query, limit=5, min_similarity=0.3):
        """Busca entradas semanticamente similares con decaimiento temporal.
        v3: Catch-all de errores de dimension con fallback a busqueda por texto.
        """
        query_embedding = ollama.get_embedding(query)
        if not query_embedding:
            return self._text_search(query, limit)

        # Actualizar dimension si es la primera vez que obtenemos un embedding valido
        if self._embedding_dim is None:
            self._embedding_dim = len(query_embedding)
            logger.info(f"Dimension de embedding detectada dinamicamente: {self._embedding_dim}")

        # Validar dimension del embedding antes de buscar
        if len(query_embedding) != self._embedding_dim:
            logger.warning(
                f"Dimension mismatch en search: {len(query_embedding)} vs {self._embedding_dim}. "
                f"Actualizando dimension y recreando coleccion..."
            )
            try:
                self._handle_dimension_error(query_embedding)
            except Exception as e:
                logger.warning(f"Error recreando coleccion: {e}")
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
            err_msg = str(e).lower()
            if "dimension" in err_msg or "dim" in err_msg:
                logger.warning(f"Dimension mismatch en query, recreando coleccion...")
                try:
                    self._handle_dimension_error(query_embedding)
                except Exception:
                    pass
            else:
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
        except Exception as e:
            logger.debug(f"Error en busqueda por texto ChromaDB: {e}")
            return []

    def count(self):
        """Retorna el numero de documentos en el store."""
        try:
            return self._collection.count()
        except Exception as e:
            logger.warning(f"Error contando documentos ChromaDB: {e}")
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


class SimpleVectorStore(VectorStore):
    """
    Vector store casero (fallback cuando ChromaDB no esta instalado).
    Hereda de VectorStore y agrega decaimiento temporal + deduplicacion por texto.
    Solo sobreescribe los metodos que difieren del base.
    Elimina ~150 lineas de codigo duplicado vs la version anterior.
    """

    DECAY_HALF_LIFE_DAYS = 30

    def _compute_decay(self, created_at):
        """Computa el factor de decaimiento temporal (0.1 - 1.0)."""
        if not created_at:
            return 0.5
        try:
            created = datetime.fromisoformat(created_at)
            days_old = (datetime.now() - created).total_seconds() / 86400
            import math
            decay = math.exp(-0.693 * days_old / self.DECAY_HALF_LIFE_DAYS)
            return max(decay, 0.1)
        except Exception as e:
            logger.debug(f"Error computando decaimiento: {e}")
            return 0.5

    def add(self, text, metadata=None, entry_id=None, skip_embedding=False):
        """Agrega un texto con deduplicacion basica por texto similar."""
        if not entry_id:
            entry_id = hashlib.md5(text.encode()).hexdigest()[:12]

        # Verificar si ya existe
        for entry in self.index:
            if entry["id"] == entry_id:
                return entry_id

        # Deduplicacion basica por texto similar (100 chars lowercase)
        text_lower = text[:100].lower()
        for entry in self.index:
            if entry["text"][:100].lower() == text_lower:
                return entry["id"]

        # Delegar al padre para el resto (guardar con/sin embedding)
        return super().add(text, metadata=metadata, entry_id=entry_id, skip_embedding=skip_embedding)

    def search(self, query, limit=5, min_similarity=0.3):
        """Busca con decaimiento temporal. Sobreescribe para agregar decay al scoring."""
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

        # Scoring vectorizado con decaimiento temporal
        similarities = ollama.cosine_similarity_batch(query_embedding, vectors)

        scored = []
        for entry in candidates:
            if not entry.get("has_vector") or entry["id"] not in similarities:
                continue
            raw_sim = similarities[entry["id"]]
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

    def _text_search(self, query, limit=5):
        """Busqueda por texto con decaimiento temporal."""
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


# ============================================================
# FACTORY: Retorna HybridVectorStore(ChromaVectorStore/SimpleVectorStore)
# ============================================================
def create_vector_store(store_dir=None, use_hybrid=True, use_reranker=True):
    """Factory que retorna el mejor vector store disponible.

    v14.5: Por defecto retorna HybridVectorStore que envuelve el backend
    y anade busqueda BM25 + fusion RRF. Opcionalmente anade re-ranker.

    Args:
        store_dir: Directorio de persistencia
        use_hybrid: Si True, envuelve en HybridVectorStore con BM25+RRF
        use_reranker: Si True, anade MultiSignalReranker al TripleMemory
    """
    # 1. Seleccionar backend base
    base_store = None
    if CHROMADB_AVAILABLE:
        try:
            base_store = ChromaVectorStore(store_dir=store_dir)
            logger.info("Backend base: ChromaDB")
        except Exception as e:
            logger.warning(f"Error inicializando ChromaDB, fallback a casero: {e}")

    if base_store is None:
        base_store = SimpleVectorStore(store_dir=store_dir)
        logger.info("Backend base: SimpleVectorStore (casero)")

    # 2. Envolver en Hibrido si se solicita
    if use_hybrid:
        try:
            from memory.hybrid import HybridVectorStore
            hybrid_store = HybridVectorStore(base_store)
            logger.info(
                f"Vector store hibrido activado: "
                f"{hybrid_store.count()} docs, BM25 + RRF"
            )
            return hybrid_store
        except ImportError as e:
            logger.warning(f"HybridVectorStore no disponible ({e}), usando base store")
        except Exception as e:
            logger.warning(f"Error inicializando HybridVectorStore: {e}, usando base store")

    return base_store
