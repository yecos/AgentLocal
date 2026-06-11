"""
chroma_store.py — Almacén vectorial ChromaDB para ZAI
v2: Manejo automático de mismatch de dimensiones de embeddings.
    - Detecta si la colección existe con dimensiones diferentes.
    - Recrea la colección automáticamente si hay mismatch.
    - Parámetro `skip_embedding` en add().
"""

import chromadb
from chromadb.config import Settings
from typing import Optional, List, Dict, Any
import logging
import hashlib
import os
import shutil

logger = logging.getLogger(__name__)


class ChromaStore:
    """
    Wrapper de ChromaDB con soporte para:
    - skip_embedding: evitar re-generar embeddings precomputados
    - auto-recreación de colección cuando cambian las dimensiones del modelo
    """

    def __init__(
        self,
        persist_dir: str = "./data/chroma",
        collection_name: str = "zai_memory",
        embedding_fn: Optional[Any] = None,
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.embedding_fn = embedding_fn

        self.client = chromadb.Client(
            Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=persist_dir,
            )
        )

        # Detectar dimensión del modelo de embedding actual
        self._embedding_dim = self._detect_embedding_dimension()

        # Obtener o crear la colección (con validación de dimensiones)
        self.collection = self._get_or_create_collection()

    # ------------------------------------------------------------------ #
    #  _detect_embedding_dimension() — detecta dim del modelo actual      #
    # ------------------------------------------------------------------ #
    def _detect_embedding_dimension(self) -> Optional[int]:
        """
        Detecta la dimensión de los embeddings del modelo actual
        generando un embedding de prueba.
        """
        if self.embedding_fn is None:
            return None

        try:
            test_embedding = self.embedding_fn(["test"])
            if isinstance(test_embedding, list) and len(test_embedding) > 0:
                if isinstance(test_embedding[0], list):
                    return len(test_embedding[0])
                else:
                    # Algunas funciones devuelven una lista plana
                    return len(test_embedding)
        except Exception as exc:
            logger.warning("No se pudo detectar la dimensión del embedding: %s", exc)

        return None

    # ------------------------------------------------------------------ #
    #  _get_collection_dimension() — lee dim de una colección existente    #
    # ------------------------------------------------------------------ #
    def _get_collection_dimension(self, collection) -> Optional[int]:
        """
        Intenta obtener la dimensión de embeddings de una colección existente.
        """
        try:
            # ChromaDB almacena metadata con la dimensión en algunas versiones
            metadata = collection.metadata
            if metadata and "hnsw:dim" in metadata:
                return int(metadata["hnsw:dim"])
        except Exception:
            pass

        # Intentar inferir de los embeddings existentes
        try:
            peek_result = collection.peek(limit=1)
            if peek_result and peek_result.get("embeddings") and len(peek_result["embeddings"]) > 0:
                return len(peek_result["embeddings"][0])
        except Exception:
            pass

        return None

    # ------------------------------------------------------------------ #
    #  _get_or_create_collection() — con validación de dimensiones        #
    # ------------------------------------------------------------------ #
    def _get_or_create_collection(self):
        """
        Obtiene o crea la colección, manejando automáticamente
        el mismatch de dimensiones de embeddings.
        """
        try:
            # Intentar obtener colección existente
            existing = self.client.get_collection(name=self.collection_name)

            # Verificar dimensiones si las conocemos
            if self._embedding_dim is not None:
                existing_dim = self._get_collection_dimension(existing)

                if existing_dim is not None and existing_dim != self._embedding_dim:
                    logger.warning(
                        "⚠️ MISMATCH DE DIMENSIONES: colección '%s' espera %d dim, "
                        "modelo actual produce %d dim. Recreando colección...",
                        self.collection_name, existing_dim, self._embedding_dim,
                    )
                    # Eliminar colección con dimensiones incorrectas
                    self.client.delete_collection(name=self.collection_name)
                    logger.info(
                        "Colección '%s' eliminada. Creando nueva con dim=%d",
                        self.collection_name, self._embedding_dim,
                    )

                    # Crear nueva colección con metadata de dimensión
                    return self.client.create_collection(
                        name=self.collection_name,
                        metadata={
                            "hnsw:space": "cosine",
                            "hnsw:dim": self._embedding_dim,
                        },
                    )

            return existing

        except Exception:
            # La colección no existe — crear nueva
            metadata = {"hnsw:space": "cosine"}
            if self._embedding_dim is not None:
                metadata["hnsw:dim"] = self._embedding_dim

            return self.client.create_collection(
                name=self.collection_name,
                metadata=metadata,
            )

    # ------------------------------------------------------------------ #
    #  add() — con skip_embedding y validación de dimensión               #
    # ------------------------------------------------------------------ #
    def add(
        self,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
        skip_embedding: bool = False,
    ) -> List[str]:
        """
        Añade documentos a la colección.

        Parámetros
        ----------
        documents : list[str]
            Textos a almacenar.
        metadatas : list[dict], opcional
            Metadatos asociados a cada documento.
        ids : list[str], opcional
            Identificadores únicos. Se generan desde hash si no se pasan.
        embeddings : list[list[float]], opcional
            Embeddings precomputados.
        skip_embedding : bool, por defecto False
            Si es True y se pasan embeddings, se usan directamente sin
            invocar la función de embedding.

        Retorna
        -------
        list[str]
            Los IDs insertados.
        """
        if ids is None:
            ids = [
                hashlib.md5(doc.encode()).hexdigest()[:16]
                for doc in documents
            ]

        # ── Caso 1: embeddings precomputados + skip ──
        if skip_embedding and embeddings is not None:
            # Validar dimensión de embeddings recibidos
            if self._embedding_dim is not None:
                for i, emb in enumerate(embeddings):
                    if len(emb) != self._embedding_dim:
                        logger.error(
                            "Embedding #%d tiene %d dim, se esperaban %d. "
                            "Skip embedding cancelado — se recalculará.",
                            i, len(emb), self._embedding_dim,
                        )
                        skip_embedding = False
                        embeddings = None
                        break

            if skip_embedding and embeddings is not None:
                logger.debug(
                    "skip_embedding=True — insertando %d docs con embeddings precomputados",
                    len(documents),
                )
                try:
                    self.collection.add(
                        documents=documents,
                        embeddings=embeddings,
                        metadatas=metadatas,
                        ids=ids,
                    )
                    return ids
                except chromadb.errors.InvalidArgumentError as e:
                    if "dimension" in str(e).lower():
                        logger.warning(
                            "Error de dimensión al insertar con skip_embedding. "
                            "Recreando colección y reintentando..."
                        )
                        self._handle_dimension_error(embeddings[0] if embeddings else None)
                        # Reintentar sin skip_embedding
                        skip_embedding = False
                        embeddings = None
                    else:
                        raise

        # ── Caso 2: calcular embeddings con la función configurada ──
        if self.embedding_fn is not None:
            computed_embeddings = self.embedding_fn(documents)

            # Validar dimensiones
            if computed_embeddings and isinstance(computed_embeddings[0], list):
                computed_dim = len(computed_embeddings[0])
                if self._embedding_dim is None:
                    self._embedding_dim = computed_dim
                elif computed_dim != self._embedding_dim:
                    logger.warning(
                        "Embedding calculado tiene %d dim, se esperaban %d. "
                        "Actualizando dimensión de referencia.",
                        computed_dim, self._embedding_dim,
                    )
                    self._embedding_dim = computed_dim

            try:
                self.collection.add(
                    documents=documents,
                    embeddings=computed_embeddings,
                    metadatas=metadatas,
                    ids=ids,
                )
                return ids
            except chromadb.errors.InvalidArgumentError as e:
                if "dimension" in str(e).lower():
                    logger.warning(
                        "Error de dimensión al insertar. Recreando colección..."
                    )
                    self._handle_dimension_error(
                        computed_embeddings[0] if computed_embeddings else None
                    )
                    # Reintentar
                    self.collection.add(
                        documents=documents,
                        embeddings=computed_embeddings,
                        metadatas=metadatas,
                        ids=ids,
                    )
                    return ids
                else:
                    raise

        # ── Caso 3: sin función de embedding — dejar que Chroma lo maneje ──
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        return ids

    # ------------------------------------------------------------------ #
    #  _handle_dimension_error() — recrea colección con dim correcta      #
    # ------------------------------------------------------------------ #
    def _handle_dimension_error(self, sample_embedding: Optional[List[float]] = None) -> None:
        """
        Maneja un error de dimensión recreando la colección.
        Si se proporciona un embedding de muestra, se usa su dimensión.
        """
        new_dim = None
        if sample_embedding is not None:
            new_dim = len(sample_embedding)

        if new_dim is not None:
            self._embedding_dim = new_dim

        logger.warning(
            "Recreando colección '%s' con dim=%s (datos previos se pierden)",
            self.collection_name, new_dim,
        )

        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception:
            pass

        metadata = {"hnsw:space": "cosine"}
        if new_dim is not None:
            metadata["hnsw:dim"] = new_dim

        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata=metadata,
        )

    # ------------------------------------------------------------------ #
    #  query()                                                            #
    # ------------------------------------------------------------------ #
    def query(
        self,
        query_texts: Optional[List[str]] = None,
        query_embeddings: Optional[List[List[float]]] = None,
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Busca documentos similares."""
        kwargs: Dict[str, Any] = {"n_results": n_results}
        if query_texts is not None:
            kwargs["query_texts"] = query_texts
        if query_embeddings is not None:
            kwargs["query_embeddings"] = query_embeddings
        if where is not None:
            kwargs["where"] = where
        return self.collection.query(**kwargs)

    # ------------------------------------------------------------------ #
    #  delete()                                                           #
    # ------------------------------------------------------------------ #
    def delete(
        self,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Elimina documentos por ID o filtro."""
        kwargs: Dict[str, Any] = {}
        if ids is not None:
            kwargs["ids"] = ids
        if where is not None:
            kwargs["where"] = where
        if kwargs:
            self.collection.delete(**kwargs)

    # ------------------------------------------------------------------ #
    #  count()                                                            #
    # ------------------------------------------------------------------ #
    def count(self) -> int:
        """Devuelve el número de documentos en la colección."""
        return self.collection.count()

    # ------------------------------------------------------------------ #
    #  persist()                                                          #
    # ------------------------------------------------------------------ #
    def persist(self) -> None:
        """Fuerza la persistencia en disco."""
        self.client.persist()

    # ------------------------------------------------------------------ #
    #  reset_collection() — utility para forzar recreación                #
    # ------------------------------------------------------------------ #
    def reset_collection(self, new_dim: Optional[int] = None) -> None:
        """
        Elimina y recrea la colección desde cero.

        Parámetros
        ----------
        new_dim : int, opcional
            Nueva dimensión de embeddings. Si no se pasa,
            se detecta automáticamente del modelo.
        """
        if new_dim is not None:
            self._embedding_dim = new_dim
        elif self._embedding_dim is None:
            self._embedding_dim = self._detect_embedding_dimension()

        logger.warning(
            "Reseteando colección '%s' con dim=%s — TODOS LOS DATOS SE PERDERÁN",
            self.collection_name, self._embedding_dim,
        )

        try:
            self.client.delete_collection(name=self.collection_name)
        except Exception:
            pass

        metadata = {"hnsw:space": "cosine"}
        if self._embedding_dim is not None:
            metadata["hnsw:dim"] = self._embedding_dim

        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata=metadata,
        )

    # ------------------------------------------------------------------ #
    #  get_info() — diagnóstico de la colección                           #
    # ------------------------------------------------------------------ #
    def get_info(self) -> Dict[str, Any]:
        """
        Retorna información de diagnóstico de la colección:
        nombre, count, dimensión esperada, dimensión del modelo.
        """
        existing_dim = self._get_collection_dimension(self.collection)
        return {
            "collection_name": self.collection_name,
            "document_count": self.count(),
            "collection_dimension": existing_dim,
            "model_dimension": self._embedding_dim,
            "dimensions_match": existing_dim == self._embedding_dim if existing_dim and self._embedding_dim else "unknown",
            "persist_dir": self.persist_dir,
        }
