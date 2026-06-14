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

RRF Fusion:
    Reciprocal Rank Fusion combina rankings de diferentes sistemas
    sin necesidad de normalizar scores. Para cada documento d::

        RRF_score(d) = Σ  1 / (k + rank_i(d))

    donde k es una constante de suavizado (default: 60 desde config).
    Documentos que aparecen en ambos rankings reciben scores de ambos,
    obteniendo un boost natural por su consenso.

Compatible con ChromaVectorStore y VectorStore casero.
No requiere cambios en TripleMemory ni ReactAgent.
=============================================================
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from config import logger, BM25_K1, BM25_B, RRF_K
from memory.bm25 import BM25, reciprocal_rank_fusion


class HybridVectorStore:
    """Vector store hibrido que combina busqueda semantica y lexica.

    Envuelve (wrapper pattern) cualquier vector store existente
    y anade busqueda BM25 con fusion RRF.

    Flujo de busqueda:
        1. Recuperacion paralela: busqueda vectorial (semantica) y
           BM25 (lexica) se ejecutan de forma independiente.
        2. Fusion RRF: los rankings de ambos sistemas se combinan
           usando Reciprocal Rank Fusion.
        3. Resultados: se retornan los documentos fusionados
           ordenados por score RRF.

    Ventajas sobre busqueda vectorial sola:
    - Encuentra coincidencias exactas de terminos (IDs, nombres, codigos)
    - Mejor recall para terminos tecnicos especificos
    - Reciprocal Rank Fusion no requiere normalizacion de scores
    - Compatible con cualquier backend (ChromaDB, casero, etc.)

    Args:
        vector_store: Instancia de VectorStore o ChromaVectorStore
            existente. Debe implementar al menos los metodos ``add()``,
            ``search()`` y ``count()``.
    """

    # Parametros RRF (desde config.py)
    RRF_K: int = RRF_K

    def __init__(self, vector_store: Any) -> None:
        """Inicializa el store hibrido.

        Args:
            vector_store: Instancia de VectorStore o ChromaVectorStore existente.
        """
        self._vs = vector_store
        self._bm25: BM25 | None = None
        self._build_bm25_index()

    def _build_bm25_index(self) -> None:
        """Construye el indice BM25 a partir de los datos existentes.

        Intenta extraer documentos del vector store subyacente:
        - VectorStore casero: lee de ``self._vs.index``
        - ChromaVectorStore: lee de ``self._vs._collection``

        Si no hay documentos, el indice BM25 queda como None y se
        construira incrementalmente cuando se anadan documentos.
        """
        try:
            documents: list[dict[str, str]] = []
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
                self._bm25 = BM25(documents, k1=BM25_K1, b=BM25_B, use_stemming=True)
                logger.info(f"BM25 index construido con {len(documents)} documentos")
            else:
                self._bm25 = None
                logger.info("Sin documentos para indexar BM25 (se construira incrementalmente)")

        except Exception as e:
            logger.warning(f"Error construyendo indice BM25: {e}")
            self._bm25 = None

    def add(
        self,
        text: str,
        metadata: dict | None = None,
        entry_id: str | None = None,
        skip_embedding: bool = False,
    ) -> Any:
        """Agrega un texto al store (vector + BM25).

        Delega al vector store subyacente y actualiza el indice BM25
        incrementalmente.

        Args:
            text: Contenido textual a agregar.
            metadata: Metadatos asociados al documento. Default: None.
            entry_id: Identificador unico del documento. Si es None,
                se genera uno automaticamente. Default: None.
            skip_embedding: Si True, no genera embedding vectorial.
                Default: False.

        Returns:
            El resultado del metodo ``add()`` del vector store subyacente
            (tipicamente el ID del documento).
        """
        result = self._vs.add(text, metadata=metadata, entry_id=entry_id, skip_embedding=skip_embedding)

        # Actualizar indice BM25 incrementalmente
        if self._bm25 is None:
            # Primer documento: construir indice con este
            self._bm25 = BM25(k1=BM25_K1, b=BM25_B, use_stemming=True)

        try:
            doc_id = entry_id or result
            self._bm25.add_document(doc_id, text)
        except Exception as e:
            logger.debug(f"Error actualizando BM25 incremental: {e}")

        return result

    def search(
        self,
        query: str,
        limit: int = 5,
        min_similarity: float = 0.25,
    ) -> list[dict[str, Any]]:
        """Busqueda hibrida: vectorial + BM25 fusionada con RRF.

        Ejecuta busqueda vectorial y BM25 en paralelo, fusiona los
        resultados con Reciprocal Rank Fusion y retorna los documentos
        ordenados por score RRF.

        Args:
            query: Texto de busqueda.
            limit: Numero maximo de resultados a retornar. Default: 5.
            min_similarity: Umbral minimo de similitud para la busqueda
                vectorial. Se reduce automaticamente a ``min_similarity * 0.7``
                en la fase de recuperacion para maximizar recall. Default: 0.25.

        Returns:
            Lista de diccionarios con los resultados fusionados. Cada
            resultado puede contener las keys: ``id``, ``text``,
            ``metadata``, ``score``, ``rrf_score``, ``source`` (``"hybrid"``
            o ``"bm25"``), y ``bm25_score``. Ordenados por ``rrf_score``
            descendente.
        """
        # Si no hay indice BM25, solo busqueda vectorial
        if self._bm25 is None or self._bm25.doc_count == 0:
            return self._vs.search(query, limit=limit, min_similarity=min_similarity)

        # ============================================================
        # FASE 1: Recuperacion paralela
        # ============================================================

        # Busqueda vectorial (semantica)
        vector_results: list[dict] = []
        try:
            vector_results = self._vs.search(query, limit=limit * 2, min_similarity=max(min_similarity * 0.7, 0.15))
        except Exception as e:
            logger.debug(f"Busqueda vectorial fallo: {e}")

        # Busqueda BM25 (lexica)
        bm25_results: list[tuple[str, float]] = []
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
        id_to_result: dict[str, dict] = {r["id"]: r for r in vector_results}
        id_to_bm25_score: dict[str, float] = {doc_id: score for doc_id, score in bm25_results}

        final_results: list[dict[str, Any]] = []
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

    def _bm25_to_results(
        self,
        bm25_results: list[tuple[str, float]],
    ) -> list[dict[str, Any]]:
        """Convierte resultados BM25 al formato estandar de resultados.

        Args:
            bm25_results: Lista de tuplas ``(doc_id, score)`` de BM25.

        Returns:
            Lista de diccionarios con keys ``id``, ``text``, ``metadata``,
            ``score`` y ``source``.
        """
        results: list[dict[str, Any]] = []
        for doc_id, score in bm25_results:
            result = self._bm25_entry_to_result(doc_id)
            if result:
                result["score"] = round(score, 3)
                result["source"] = "bm25"
                results.append(result)
        return results

    def _bm25_entry_to_result(self, doc_id: str) -> dict[str, Any] | None:
        """Busca un documento por ID y retorna en formato de resultado.

        Busca en el vector store subyacente (casero o ChromaDB).

        Args:
            doc_id: Identificador del documento a buscar.

        Returns:
            Diccionario con los datos del documento, o None si no
            se encuentra.
        """
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
            except Exception as e:
                logger.debug(f"Error buscando documento por ID en ChromaDB: {e}")
        return None

    # ============================================================
    # Delegacion al vector store interno
    # ============================================================

    def count(self) -> int:
        """Retorna el numero total de documentos.

        Returns:
            Numero de documentos en el vector store subyacente.
        """
        return self._vs.count()

    def count_with_vectors(self) -> int:
        """Retorna cuantos documentos tienen vectores.

        Returns:
            Numero de documentos con embedding vectorial, o 0 si el
            backend no soporta este metodo.
        """
        if hasattr(self._vs, 'count_with_vectors'):
            return self._vs.count_with_vectors()
        return 0

    def cleanup(self, max_entries: int = 500) -> Any:
        """Limpia entradas viejas y reconstruye BM25.

        Delega al vector store subyacente y luego reconstruye el
        indice BM25 para mantener la consistencia.

        Args:
            max_entries: Numero maximo de entradas a mantener. Default: 500.

        Returns:
            Resultado del cleanup del vector store subyacente, o None
            si el backend no soporta cleanup.
        """
        result = self._vs.cleanup(max_entries=max_entries) if hasattr(self._vs, 'cleanup') else None
        # Reconstruir indice BM25 despues de cleanup
        self._build_bm25_index()
        return result

    def get_info(self) -> dict[str, Any]:
        """Retorna informacion de diagnostico del store hibrido.

        Returns:
            Diccionario con keys: ``type``, ``backend``, ``total_docs``,
            ``bm25_docs``, ``bm25_terms``. Si el backend soporta
            ``get_info()``, se incluye como ``backend_info``.
        """
        info: dict[str, Any] = {
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
    def index(self) -> list[dict]:
        """Acceso al indice del vector store interno (compatibilidad).

        Returns:
            Lista de entradas del indice del vector store subyacente,
            o lista vacia si no tiene atributo ``index``.
        """
        return self._vs.index if hasattr(self._vs, 'index') else []

    def __getattr__(self, name: str) -> Any:
        """Delegar atributos no encontrados al vector store interno.

        Args:
            name: Nombre del atributo a buscar.

        Returns:
            El atributo del vector store subyacente.

        Raises:
            AttributeError: Si el atributo no existe en el vector store.
        """
        return getattr(self._vs, name)
