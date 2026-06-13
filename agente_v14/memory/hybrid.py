"""
=============================================================
AGENTE v14 - Vector Store Hibrido
=============================================================
Combina busqueda vectorial (semantica) con BM25 (lexica)
usando Reciprocal Rank Fusion (RRF) para resultados superiores.

Arquitectura: Wrapper pattern sobre cualquier VectorStore existente.
- Fase 1: Recuperacion paralela (vectorial + BM25)
- Fase 2: Fusion con RRF
- Fase 3: Re-ranking opcional con multi-señal

Compatible con ChromaVectorStore y VectorStore casero.
No requiere cambios en TripleMemory ni ReactAgent.
=============================================================
"""

import logging
from datetime import datetime

from config import logger
from memory.bm25 import BM25, reciprocal_rank_fusion


class HybridVectorStore:
    """
    Vector store hibrido que combina busqueda semantica y lexica.

    Envuelve (wrapper pattern) cualquier vector store existente
    y anade busqueda BM25 con fusion RRF.

    Ventajas sobre busqueda vectorial sola:
    - Encuentra coincidencias exactas de terminos (IDs, nombres, codigos)
    - Mejor recall para terminos tecnicos especificos
    - Reciprocal Rank Fusion no requiere normalizacion de scores
    - Compatible con cualquier backend (ChromaDB, casero, etc.)
    """

    # Parametros RRF
    RRF_K = 60  # Constante de suavizado estandar

    def __init__(self, vector_store):
        """Inicializa el store hibrido.

        Args:
            vector_store: Instancia de VectorStore o ChromaVectorStore existente.
        """
        self._vs = vector_store
        self._bm25 = None
        self._build_bm25_index()

    def _build_bm25_index(self):
        """Construye el indice BM25 a partir de los datos existentes."""
        try:
            documents = []
            # Obtener documentos del vector store subyacente
            if hasattr(self._vs, 'index'):
                # VectorStore casero: index es una lista
                for entry in self._vs.index:
                    documents.append({
                        "id": entry.get("id", ""),
                        "text": entry.get("text", "")
                    })
            elif hasattr(self._vs, '_collection'):
                # ChromaVectorStore: obtener de la coleccion
                try:
                    all_docs = self._vs._collection.get(include=["documents", "metadatas"])
                    if all_docs and all_docs.get("ids"):
                        for i, doc_id in enumerate(all_docs["ids"]):
                            doc_text = all_docs["documents"][i] if all_docs.get("documents") else ""
                            documents.append({"id": doc_id, "text": doc_text})
                except Exception as e:
                    logger.warning(f"Error obteniendo docs de ChromaDB para BM25: {e}")

            if documents:
                self._bm25 = BM25(documents, k1=1.5, b=0.75, use_stemming=True)
                logger.info(f"BM25 index construido con {len(documents)} documentos")
            else:
                self._bm25 = None
                logger.info("Sin documentos para indexar BM25 (se construira incrementalmente)")

        except Exception as e:
            logger.warning(f"Error construyendo indice BM25: {e}")
            self._bm25 = None

    def add(self, text, metadata=None, entry_id=None, skip_embedding=False):
        """Agrega un texto al store (vector + BM25)."""
        result = self._vs.add(text, metadata=metadata, entry_id=entry_id, skip_embedding=skip_embedding)

        # Actualizar indice BM25 incrementalmente
        if self._bm25 is None:
            # Primer documento: construir indice con este
            self._bm25 = BM25(k1=1.5, b=0.75, use_stemming=True)

        try:
            doc_id = entry_id or result
            self._bm25.add_document(doc_id, text)
        except Exception as e:
            logger.debug(f"Error actualizando BM25 incremental: {e}")

        return result

    def search(self, query, limit=5, min_similarity=0.25):
        """Busqueda hibrida: vectorial + BM25 fusionada con RRF.

        Args:
            query: Texto de busqueda
            limit: Numero maximo de resultados
            min_similarity: Umbral minimo de similitud (reducido para hibrido)

        Retorna resultados fusionados ordenados por score RRF.
        """
        # Si no hay indice BM25, solo busqueda vectorial
        if self._bm25 is None or self._bm25.doc_count == 0:
            return self._vs.search(query, limit=limit, min_similarity=min_similarity)

        # ============================================================
        # FASE 1: Recuperacion paralela
        # ============================================================

        # Busqueda vectorial (semantica)
        vector_results = []
        try:
            vector_results = self._vs.search(query, limit=limit * 2, min_similarity=max(min_similarity * 0.7, 0.15))
        except Exception as e:
            logger.debug(f"Busqueda vectorial fallo: {e}")

        # Busqueda BM25 (lexica)
        bm25_results = []
        try:
            bm25_results = self._bm25.search(query, limit=limit * 2, min_score=0.0)
        except Exception as e:
            logger.debug(f"Busqueda BM25 fallo: {e}")

        # Si una de las dos no tiene resultados, usar la otra directamente
        if not vector_results and not bm25_results:
            return self._vs.search(query, limit=limit, min_similarity=min_similarity)
        if not vector_results:
            # Solo BM25: convertir a formato de resultado
            return self._bm25_to_results(bm25_results[:limit])
        if not bm25_results:
            # Solo vectorial
            return vector_results[:limit]

        # ============================================================
        # FASE 2: Fusion con Reciprocal Rank Fusion
        # ============================================================

        # Rankings como listas de IDs ordenados
        v_ids = [r["id"] for r in vector_results]
        b_ids = [doc_id for doc_id, _ in bm25_results]

        # Fusion RRF
        fused = reciprocal_rank_fusion([v_ids, b_ids], k=self.RRF_K)

        # Mapear IDs a resultados completos
        id_to_result = {r["id"]: r for r in vector_results}
        id_to_bm25_score = {doc_id: score for doc_id, score in bm25_results}

        final_results = []
        for doc_id, rrf_score in fused:
            if doc_id in id_to_result:
                # Resultado que esta en ambos rankings o solo en vectorial
                result = {**id_to_result[doc_id]}
                result["rrf_score"] = round(rrf_score, 4)
                result["source"] = "hybrid"
                if doc_id in id_to_bm25_score:
                    result["bm25_score"] = id_to_bm25_score[doc_id]
                final_results.append(result)
            else:
                # Resultado que solo esta en BM25 (no en vectorial)
                result = self._bm25_entry_to_result(doc_id)
                if result:
                    result["rrf_score"] = round(rrf_score, 4)
                    result["source"] = "bm25"
                    result["bm25_score"] = id_to_bm25_score.get(doc_id, 0)
                    final_results.append(result)

        return final_results[:limit]

    def _bm25_to_results(self, bm25_results):
        """Convierte resultados BM25 al formato estandar de resultados."""
        results = []
        for doc_id, score in bm25_results:
            result = self._bm25_entry_to_result(doc_id)
            if result:
                result["score"] = round(score, 3)
                result["source"] = "bm25"
                results.append(result)
        return results

    def _bm25_entry_to_result(self, doc_id):
        """Busca un documento por ID y retorna en formato de resultado."""
        # Buscar en VectorStore casero
        if hasattr(self._vs, 'index'):
            for entry in self._vs.index:
                if entry.get("id") == doc_id:
                    return {**entry}
        # Buscar en ChromaVectorStore
        elif hasattr(self._vs, '_collection'):
            try:
                doc = self._vs._collection.get(ids=[doc_id], include=["documents", "metadatas"])
                if doc and doc["ids"]:
                    meta = doc["metadatas"][0] if doc.get("metadatas") else {}
                    return {
                        "id": doc_id,
                        "text": doc["documents"][0] if doc.get("documents") else "",
                        "metadata": meta,
                        "has_vector": not meta.get("no_embedding", False),
                    }
            except Exception:
                pass
        return None

    # ============================================================
    # Delegacion al vector store interno
    # ============================================================

    def count(self):
        """Retorna el numero total de documentos."""
        return self._vs.count()

    def count_with_vectors(self):
        """Retorna cuantos documentos tienen vectores."""
        if hasattr(self._vs, 'count_with_vectors'):
            return self._vs.count_with_vectors()
        return 0

    def cleanup(self, max_entries=500):
        """Limpia entradas viejas y reconstruye BM25."""
        result = self._vs.cleanup(max_entries=max_entries) if hasattr(self._vs, 'cleanup') else None
        # Reconstruir indice BM25 despues de cleanup
        self._build_bm25_index()
        return result

    def get_info(self):
        """Retorna informacion de diagnostico."""
        info = {
            "type": "HybridVectorStore",
            "backend": type(self._vs).__name__,
            "total_docs": self.count(),
            "bm25_docs": self._bm25.doc_count if self._bm25 else 0,
            "bm25_terms": self._bm25.stats()["unique_terms"] if self._bm25 else 0,
        }
        if hasattr(self._vs, 'get_info'):
            info["backend_info"] = self._vs.get_info()
        return info

    # Propiedades para compatibilidad con codigo que accede directamente
    @property
    def index(self):
        """Acceso al indice del vector store interno (compatibilidad)."""
        return self._vs.index if hasattr(self._vs, 'index') else []

    def __getattr__(self, name):
        """Delegar atributos no encontrados al vector store interno."""
        return getattr(self._vs, name)
