"""
chroma_store.py — Almacén vectorial ChromaDB para ZAI
Cambio: parámetro `skip_embedding` en add() para evitar
re-generar embeddings cuando ya están precomputados.
"""

import chromadb
from chromadb.config import Settings
from typing import Optional, List, Dict, Any
import logging
import hashlib

logger = logging.getLogger(__name__)


class ChromaStore:
    """Wrapper de ChromaDB con soporte para skip_embedding."""

    def __init__(
        self,
        persist_dir: str = "./data/chroma",
        collection_name: str = "zai_memory",
        embedding_fn: Optional[Any] = None,
    ):
        self.client = chromadb.Client(
            Settings(
                chroma_db_impl="duckdb+parquet",
                persist_directory=persist_dir,
            )
        )
        self.embedding_fn = embedding_fn
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------ #
    #  add() — ahora acepta skip_embedding                                #
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
            Identificadores únicos. Si no se proporcionan se generan
            a partir de un hash del contenido.
        embeddings : list[list[float]], opcional
            Embeddings precomputados. Si se pasan junto con
            ``skip_embedding=True`` se usan directamente sin llamar
            a la función de embedding.
        skip_embedding : bool, por defecto False
            Si es True y se pasan ``embeddings``, se insertan directamente
            sin invocar ``self.embedding_fn``. Útil cuando los embeddings
            ya fueron calculados previamente (p.ej. en triple_memory).

        Retorna
        -------
        list[str]
            Los IDs de los documentos insertados.
        """
        if ids is None:
            ids = [
                hashlib.md5(doc.encode()).hexdigest()[:16]
                for doc in documents
            ]

        # ── Caso 1: embeddings precomputados + skip ──
        if skip_embedding and embeddings is not None:
            logger.debug(
                "skip_embedding=True — insertando %d docs con embeddings precomputados",
                len(documents),
            )
            self.collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids,
            )
            return ids

        # ── Caso 2: embeddings precomputados pero sin skip ──
        if embeddings is not None and not skip_embedding:
            logger.debug(
                "Se recibieron embeddings pero skip_embedding=False; "
                "se re-calculan con embedding_fn"
            )

        # ── Caso 3: calcular embeddings con la función configurada ──
        if self.embedding_fn is not None:
            computed_embeddings = self.embedding_fn(documents)
            self.collection.add(
                documents=documents,
                embeddings=computed_embeddings,
                metadatas=metadatas,
                ids=ids,
            )
            return ids

        # ── Caso 4: sin función de embedding — dejar que Chroma lo maneje ──
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )
        return ids

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
    def delete(self, ids: Optional[List[str]] = None, where: Optional[Dict[str, Any]] = None) -> None:
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
