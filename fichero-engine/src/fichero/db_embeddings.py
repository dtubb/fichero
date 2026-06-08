"""
Embedding helper methods for the Database class.

Mixed into Database via DatabaseEmbeddingMixin to keep db.py focused.
All methods access Database instance state (self._embedder, self.conn, etc.)
and are only valid when mixed into a Database subclass.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from typing import Callable

logger = logging.getLogger(__name__)

# Default embedding model (FastEmbed - no scikit-learn dependency)
DEFAULT_MODEL = "intfloat/multilingual-e5-large"
KG_ENTITY_EMBEDDINGS_TABLE = "kg_entity_embeddings"
KG_CLAIM_EMBEDDINGS_TABLE = "kg_claim_embeddings"


def _l2_normalize(vec: list[float]) -> list[float]:
    """L2-normalise a vector to unit length.

    Why: LanceDB returns L2 distance from `table.search(query_vector)`. On
    *un-normalised* vectors L2 distance can be hundreds, so the score
    formula `1/(1+d)` collapses every result into the 0.002–0.005 band —
    indistinguishable noise. On *unit-length* vectors L2 distance lives
    in [0, 2] and relates to cosine similarity exactly:

        L2² = 2 - 2·cos_sim   ⇒   cos_sim = 1 - L2²/2

    So normalising once at index time and once at query time gives us
    real, interpretable [0, 1] cosine scores from the same `_distance`
    column without changing the LanceDB API.
    """
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        return vec
    return [x / norm for x in vec]


def _quantize_int8(vec: list[float]) -> tuple[list[int], float]:
    """Symmetric int8 quantisation with per-vector scale."""
    if not vec:
        return [], 1.0
    max_abs = max(abs(x) for x in vec)
    if max_abs == 0.0:
        return [0 for _ in vec], 1.0
    scale = max_abs / 127.0
    quantized = [max(-127, min(127, int(round(x / scale)))) for x in vec]
    return quantized, scale


def _dequantize_int8(qvec: list[int], scale: float) -> list[float]:
    """Dequantise int8 values back to float vector."""
    if not qvec:
        return []
    if scale <= 0:
        scale = 1.0
    return [float(x) * scale for x in qvec]


def _join_text_parts(parts: list[str | None]) -> str:
    """Join non-empty text fragments into one embedding payload."""
    values = [part.strip() for part in parts if part and part.strip()]
    return " ".join(values)


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
        doc_stats = self._vector_table_stats("embeddings")
        entity_stats = self._vector_table_stats(KG_ENTITY_EMBEDDINGS_TABLE)
        claim_stats = self._vector_table_stats(KG_CLAIM_EMBEDDINGS_TABLE)
        return {
            "indexed_count": doc_stats["indexed_count"],
            "table_exists": doc_stats["table_exists"],
            "entity_indexed_count": entity_stats["indexed_count"],
            "entity_table_exists": entity_stats["table_exists"],
            "claim_indexed_count": claim_stats["indexed_count"],
            "claim_table_exists": claim_stats["table_exists"],
        }

    def _vector_table_stats(self, table_name: str) -> dict[str, int | bool]:
        """Count rows in one LanceDB vector table if present."""
        try:
            if table_name not in self._lance_tables():
                return {"indexed_count": 0, "table_exists": False}

            table = self.lance.open_table(table_name)
            return {"indexed_count": table.count_rows(), "table_exists": True}
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

    def _use_int8_embeddings(self) -> bool:
        """Feature flag for int8 embedding storage."""
        raw = os.getenv("FICHERO_EMBEDDINGS_INT8", "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

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
        return _l2_normalize(embeddings[0].tolist())

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
        return [_l2_normalize(e.tolist()) for e in embeddings]

    def entity_embedding_text(self, entity) -> str:
        """Compose the canonical text stored/searched for one entity."""
        entity_type = (
            entity.entity_type.value
            if getattr(entity, "entity_type", None) is not None
            else None
        )
        aliases = ", ".join(entity.aliases or [])
        return _join_text_parts(
            [
                entity.canonical_name,
                aliases,
                entity.description,
                entity_type,
            ]
        )

    def claim_embedding_text(self, claim) -> str:
        """Compose the canonical text stored/searched for one claim."""
        subject = claim.subject_canonical or claim.svo_subject
        predicate = (
            claim.predicate_verb or claim.svo_verb or claim.predicate_canonical
        )
        obj = claim.object_phrase or claim.svo_object
        source_text = claim.source_excerpt or claim.text
        return _join_text_parts(
            [
                subject,
                predicate,
                obj,
                source_text,
            ]
        )

    def embed_entities(self, entities) -> int:
        """Write entity embeddings into the canonical LanceDB table."""
        entities = [entity for entity in entities if entity is not None]
        if not entities:
            return 0

        texts = [self.entity_embedding_text(entity) for entity in entities]
        vectors = self._embed_texts(texts)
        records = [
            {
                "id": entity.id,
                "text": text,
                "canonical_name": entity.canonical_name,
                "aliases_text": ", ".join(entity.aliases or []),
                "description": entity.description or "",
                "entity_type": entity.entity_type.value if entity.entity_type else None,
                "vector": vector,
            }
            for entity, text, vector in zip(entities, texts, vectors)
        ]
        self.save_vectors(KG_ENTITY_EMBEDDINGS_TABLE, records, replace=True)
        return len(records)

    def embed_claims(self, claims) -> int:
        """Write claim embeddings into the canonical LanceDB table."""
        claims = [claim for claim in claims if claim is not None]
        if not claims:
            return 0

        texts = [self.claim_embedding_text(claim) for claim in claims]
        vectors = self._embed_texts(texts)
        records = [
            {
                "id": claim.id,
                "text": text,
                "source_text": claim.source_excerpt or claim.text,
                "claim_text": claim.text,
                "subject": claim.subject_canonical or claim.svo_subject or "",
                "predicate": (
                    claim.predicate_verb
                    or claim.svo_verb
                    or claim.predicate_canonical
                    or ""
                ),
                "object": claim.object_phrase or claim.svo_object or "",
                "claim_type": claim.claim_type.value if claim.claim_type else "",
                "curation_state": (
                    claim.curation_state.value if claim.curation_state else ""
                ),
                "vector": vector,
            }
            for claim, text, vector in zip(claims, texts, vectors)
        ]
        self.save_vectors(KG_CLAIM_EMBEDDINGS_TABLE, records, replace=True)
        return len(records)

    def schedule_entity_embedding(self, entity) -> None:
        """Best-effort background embed for a just-written entity."""
        self._schedule_embedding_task([entity], label="entity")

    def schedule_claim_embedding(self, claim) -> None:
        """Best-effort background embed for a just-written claim."""
        self.schedule_claim_embeddings([claim])

    def schedule_claim_embeddings(self, claims) -> None:
        """Best-effort background embed for a batch of written claims."""
        self._schedule_embedding_task(list(claims), label="claim")

    def _schedule_embedding_task(self, records, *, label: str) -> None:
        """Run embedding work off-loop when possible; degrade to sync otherwise."""
        def _run() -> None:
            from fichero.db import Database

            worker_db = Database(self.path)
            try:
                if label == "entity":
                    worker_db.embed_entities(records)
                else:
                    worker_db.embed_claims(records)
            finally:
                worker_db.close()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            try:
                _run()
            except Exception as exc:
                logger.warning("Failed to auto-embed %s synchronously: %s", label, exc)
            return

        async def _runner() -> None:
            try:
                await asyncio.to_thread(_run)
            except Exception as exc:
                logger.warning("Failed to auto-embed %s in background: %s", label, exc)

        loop.create_task(_runner())
