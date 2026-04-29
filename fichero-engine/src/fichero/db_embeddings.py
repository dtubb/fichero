"""
Embedding helper methods for the Database class.

Mixed into Database via DatabaseEmbeddingMixin to keep db.py focused.
All methods access Database instance state (self._embedder, self.conn, etc.)
and are only valid when mixed into a Database subclass.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# Default embedding model (FastEmbed - no scikit-learn dependency)
DEFAULT_MODEL = "intfloat/multilingual-e5-large"


class DatabaseEmbeddingMixin:
    """Embedding helper methods mixed into Database.

    Provides model loading, text embedding, reindexing, and stats.
    Requires that the host class has: self._embedder, self._lance_path,
    self.all(), self.embed(), self.save_embedding(), self._lance_tables(),
    self.lance.
    """

    def reindex_all(self, on_progress: Callable[[int, int], None] | None = None) -> int:
        """Reindex all documents with page_content.

        Args:
            on_progress: Optional callback(indexed: int, total: int)

        Returns:
            Number of documents indexed
        """
        from fichero.models import Document

        docs = self.all(Document)
        total = len(docs)
        indexed = 0

        for i, doc in enumerate(docs):
            if self.embed(doc):
                indexed += 1

            if on_progress:
                on_progress(indexed, total)

        logger.info("Reindexed %s/%s documents", indexed, total)
        return indexed

    def embedding_stats(self) -> dict:
        """Get statistics about embeddings.

        Returns:
            Dict with indexed_count, table_exists
        """
        try:
            if "embeddings" not in self._lance_tables():
                return {"indexed_count": 0, "table_exists": False}

            table = self.lance.open_table("embeddings")
            count = table.count_rows()
            return {"indexed_count": count, "table_exists": True}
        except Exception:
            return {"indexed_count": 0, "table_exists": False}

    def _get_embedding_model_name(self) -> str:
        """Get configured embedding model, defaulting to multilingual-e5-large."""
        try:
            from fichero.app_db import get_app_db

            model = get_app_db().get_setting("default_embeddings_model")
            if model:
                return model
        except Exception as e:
            logger.debug("Could not read default_embeddings_model setting: %s", e)
        return DEFAULT_MODEL

    def _ensure_embedder(self) -> None:
        """Lazy-load the embedding model.

        Uses FastEmbed (ONNX-based, no scikit-learn dependency).
        Reads configured model from app settings, falls back to DEFAULT_MODEL.
        """
        if self._embedder is None:
            try:
                from fastembed import TextEmbedding
                from fichero.local_models import MODELS_BASE

                model_name = self._get_embedding_model_name()
                cache_dir = MODELS_BASE / "embeddings"
                cache_dir.mkdir(parents=True, exist_ok=True)
                self._embedder = TextEmbedding(
                    model_name=model_name,
                    cache_dir=str(cache_dir),
                )
                logger.info(
                    "Loaded embedding model: %s (cache_dir=%s)",
                    model_name,
                    cache_dir,
                )
            except ImportError:
                raise ImportError(
                    "fastembed not installed. Install with: pip install fastembed"
                )

    def _embed_text(self, text: str) -> list[float]:
        """Generate embedding vector for text.

        Uses FastEmbed for local ONNX-based embedding.
        Lazy-loads the model on first use.

        Args:
            text: Text to embed

        Returns:
            List of floats (embedding vector)
        """
        self._ensure_embedder()
        embeddings = list(self._embedder.embed([text]))
        return embeddings[0].tolist()

    def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Batch embed multiple texts.

        More efficient than calling _embed_text() in a loop.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        self._ensure_embedder()
        embeddings = list(self._embedder.embed(texts))
        return [e.tolist() for e in embeddings]
