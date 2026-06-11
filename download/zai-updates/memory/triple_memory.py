"""
triple_memory.py — Sistema de memoria triple para ZAI
Cambio: integración de `skip_embedding` que se propaga al ChromaStore
para evitar re-calcular embeddings cuando ya están disponibles.
"""

from __future__ import annotations

import time
import hashlib
import logging
from typing import Optional, List, Dict, Any

from memory.chroma_store import ChromaStore

logger = logging.getLogger(__name__)


class TripleMemory:
    """
    Memoria de triple capa:

    1. **Corto plazo**  — contexto inmediato de la conversación.
    2. **Medio plazo**  — hechos y resúmenes recientes.
    3. **Largo plazo**  — conocimiento persistente.

    Cada capa usa una colección ChromaDB independiente y comparte
    la misma función de embedding.
    """

    # ------------------------------------------------------------------ #
    #  Inicialización                                                     #
    # ------------------------------------------------------------------ #
    def __init__(
        self,
        persist_dir: str = "./data/chroma",
        embedding_fn: Optional[Any] = None,
    ):
        self.embedding_fn = embedding_fn

        self.short_term = ChromaStore(
            persist_dir=persist_dir,
            collection_name="zai_short_term",
            embedding_fn=embedding_fn,
        )
        self.mid_term = ChromaStore(
            persist_dir=persist_dir,
            collection_name="zai_mid_term",
            embedding_fn=embedding_fn,
        )
        self.long_term = ChromaStore(
            persist_dir=persist_dir,
            collection_name="zai_long_term",
            embedding_fn=embedding_fn,
        )

        # Buffer temporal para la conversación actual
        self._buffer: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    #  _compute_embedding()  — helper centralizado                        #
    # ------------------------------------------------------------------ #
    def _compute_embedding(self, text: str) -> Optional[List[float]]:
        """Calcula el embedding de un texto usando la función configurada."""
        if self.embedding_fn is None:
            return None
        try:
            result = self.embedding_fn([text])
            # Algunas funciones devuelven una lista plana, otras una lista de listas
            if isinstance(result, list) and len(result) > 0:
                return result[0] if isinstance(result[0], list) else result
        except Exception as exc:
            logger.warning("Error calculando embedding: %s", exc)
        return None

    # ------------------------------------------------------------------ #
    #  add() — con soporte para skip_embedding                            #
    # ------------------------------------------------------------------ #
    def add(
        self,
        text: str,
        layer: str = "short",
        metadata: Optional[Dict[str, Any]] = None,
        skip_embedding: bool = False,
        precomputed_embedding: Optional[List[float]] = None,
    ) -> str:
        """
        Añade un recuerdo a la capa indicada.

        Parámetros
        ----------
        text : str
            Contenido a almacenar.
        layer : str
            "short", "mid" o "long".
        metadata : dict, opcional
            Metadatos adicionales.
        skip_embedding : bool, por defecto False
            Si es True y ``precomputed_embedding`` se proporciona,
            se pasa directamente al ChromaStore sin re-calcular.
        precomputed_embedding : list[float], opcional
            Embedding ya calculado. Se usa junto con ``skip_embedding=True``.

        Retorna
        -------
        str
            ID del documento insertado.
        """
        store = self._get_store(layer)
        doc_id = hashlib.md5(f"{text}{time.time()}".encode()).hexdigest()[:16]

        meta = metadata or {}
        meta["layer"] = layer
        meta["timestamp"] = time.time()

        # ── Determinar embeddings ──
        embeddings_to_pass: Optional[List[List[float]]] = None

        if skip_embedding and precomputed_embedding is not None:
            # Usar embedding precomputado sin re-calcular
            embeddings_to_pass = [precomputed_embedding]
            logger.debug(
                "TripleMemory.add skip_embedding=True para doc %s en capa %s",
                doc_id, layer,
            )
        elif not skip_embedding:
            # Calcular embedding normalmente
            emb = self._compute_embedding(text)
            if emb is not None:
                embeddings_to_pass = [emb]

        store.add(
            documents=[text],
            metadatas=[meta],
            ids=[doc_id],
            embeddings=embeddings_to_pass,
            skip_embedding=skip_embedding,
        )

        # Añadir al buffer si es corto plazo
        if layer == "short":
            self._buffer.append({"id": doc_id, "text": text, "meta": meta})

        return doc_id

    # ------------------------------------------------------------------ #
    #  recall()                                                           #
    # ------------------------------------------------------------------ #
    def recall(
        self,
        query: str,
        layers: Optional[List[str]] = None,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Recupera recuerdos de las capas indicadas.

        Parámetros
        ----------
        query : str
            Texto de consulta.
        layers : list[str], opcional
            Capas en las que buscar. Por defecto las tres.
        n_results : int
            Resultados por capa.

        Retorna
        -------
        list[dict]
            Resultados combinados y ordenados por relevancia.
        """
        if layers is None:
            layers = ["short", "mid", "long"]

        all_results: List[Dict[str, Any]] = []

        for layer in layers:
            store = self._get_store(layer)
            try:
                raw = store.query(query_texts=[query], n_results=n_results)
                for i, doc in enumerate(raw["documents"][0]):
                    dist = raw["distances"][0][i] if "distances" in raw else 0.0
                    meta = raw["metadatas"][0][i] if "metadatas" in raw else {}
                    all_results.append({
                        "text": doc,
                        "layer": layer,
                        "distance": dist,
                        "metadata": meta,
                    })
            except Exception as exc:
                logger.warning("Error consultando capa %s: %s", layer, exc)

        # Ordenar por distancia (menor = más relevante)
        all_results.sort(key=lambda r: r["distance"])
        return all_results

    # ------------------------------------------------------------------ #
    #  consolidate()                                                      #
    # ------------------------------------------------------------------ #
    def consolidate(self, max_items: int = 20) -> int:
        """
        Mueve los recuerdos más relevantes del buffer de corto plazo
        a la memoria de medio plazo.

        Retorna
        -------
        int
            Número de items consolidados.
        """
        if not self._buffer:
            return 0

        to_consolidate = self._buffer[:max_items]
        count = 0

        for item in to_consolidate:
            try:
                # Recuperar embedding del short_term store si es posible
                precomp = self._compute_embedding(item["text"])
                self.add(
                    text=item["text"],
                    layer="mid",
                    metadata=item.get("meta"),
                    skip_embedding=precomp is not None,
                    precomputed_embedding=precomp,
                )
                count += 1
            except Exception as exc:
                logger.warning("Error consolidando item %s: %s", item.get("id"), exc)

        # Limpiar items consolidados del buffer
        self._buffer = self._buffer[max_items:]

        # Eliminar del store de corto plazo
        ids_to_remove = [item["id"] for item in to_consolidate]
        self.short_term.delete(ids=ids_to_remove)

        logger.info("Consolidados %d recuerdos de corto → medio plazo", count)
        return count

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #
    def _get_store(self, layer: str) -> ChromaStore:
        mapping = {
            "short": self.short_term,
            "mid": self.mid_term,
            "long": self.long_term,
        }
        if layer not in mapping:
            raise ValueError(f"Capa inválida: {layer!r}. Usar 'short', 'mid' o 'long'.")
        return mapping[layer]

    def persist(self) -> None:
        """Persiste todas las colecciones en disco."""
        self.short_term.persist()
        self.mid_term.persist()
        self.long_term.persist()
