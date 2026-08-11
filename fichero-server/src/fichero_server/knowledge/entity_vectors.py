"""Canonical entity embeddings in LanceDB.

This module keeps the older ``entity_vectors`` API surface used by the KG
writer, but routes all reads/writes through the same embedding model and
canonical table as the search endpoints.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import TYPE_CHECKING, Optional

from fichero_server.db.embeddings import KG_ENTITY_EMBEDDINGS_TABLE
from fichero_server.knowledge._common import enum_value

if TYPE_CHECKING:  # pragma: no cover
    from fichero_server.db import Database
    from fichero_server.models.knowledge import EntityType

logger = logging.getLogger(__name__)

TABLE = KG_ENTITY_EMBEDDINGS_TABLE
AUTO_MERGE_THRESHOLD = 0.92
REVIEW_THRESHOLD = 0.75
_OVERLAP_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "into",
    "over",
    "under",
    "this",
    "that",
    "was",
    "were",
    "are",
    "but",
    "not",
    "por",
    "para",
    "con",
    "los",
    "las",
    "del",
}


def _token_overlap(left: str | None, right: str | None) -> float:
    """Cheap lexical overlap guard for semantic-merge decisions."""
    left_tokens = _content_tokens(left)
    right_tokens = _content_tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _content_tokens(text: str | None) -> set[str]:
    """Normalized content tokens, excluding stopwords and tiny words."""
    return {
        token
        for token in "".join(
            ch if ch.isalnum() or ch.isspace() else " " for ch in (text or "").lower()
        ).split()
        if len(token) > 2 and token not in _OVERLAP_STOPWORDS
    }


def _distance_to_similarity(row: dict) -> float:
    """Convert LanceDB distance output into cosine similarity."""
    if "_score" in row and row["_score"] is not None:
        return float(row["_score"])
    distance = row.get("_distance")
    if distance is None:
        return 0.0
    value = 1.0 - (float(distance) ** 2) / 2.0
    return max(-1.0, min(1.0, value))


def _adjust_similarity(
    *,
    raw_score: float,
    query_name: str,
    row_name: str,
    query_description: str | None,
    row_description: str | None,
) -> float:
    """Re-rank raw vector similarity with lightweight lexical guardrails."""
    name_overlap = _token_overlap(query_name, row_name)
    description_overlap = _token_overlap(query_description, row_description)
    description_tokens = min(
        len(_content_tokens(query_description)),
        len(_content_tokens(row_description)),
    )

    score = raw_score
    if description_overlap >= 0.95 and description_tokens >= 4 and raw_score >= 0.65:
        score = max(score, AUTO_MERGE_THRESHOLD)
    if name_overlap == 0.0 and description_tokens < 4:
        score = min(score, REVIEW_THRESHOLD - 0.01)
    if name_overlap == 0.0 and description_overlap == 0.0:
        score = min(score, REVIEW_THRESHOLD - 0.01)
    return score


def index_entity(
    db: "Database",
    entity_id: str,
    entity_type: "EntityType",
    canonical_name: str,
    description: Optional[str] = None,
) -> None:
    """Add or update an entity's vector in the canonical table."""
    try:
        from fichero_server.models.knowledge import KnowledgeEntity

        entity = db.get(KnowledgeEntity, entity_id)
        if entity is None:
            entity = SimpleNamespace(
                id=entity_id,
                canonical_name=canonical_name,
                entity_type=entity_type,
                aliases=[],
                description=description,
            )
        else:
            if description and not entity.description:
                entity.description = description
        db.embed_entities([entity])
    except Exception as exc:
        logger.warning("entity_vectors.index_entity: %s", exc)


def find_similar(
    db: "Database",
    canonical_name: str,
    entity_type: "EntityType",
    description: Optional[str] = None,
    top_k: int = 5,
) -> list[tuple[str, float, str]]:
    """Search canonical entity vectors by semantic similarity."""
    try:
        if TABLE not in db._lance_tables():
            return []

        probe = SimpleNamespace(
            canonical_name=canonical_name,
            entity_type=entity_type,
            aliases=[],
            description=description,
        )
        query_vector = db._embed_text(db.entity_embedding_text(probe), role="passage")  # type: ignore[attr-defined]
        results = db.search_vectors(TABLE, query_vector, limit=max(top_k * 5, top_k))

        hits: list[tuple[str, float, str]] = []
        expected_type = enum_value(entity_type)
        for row in results:
            if row.get("entity_type") != expected_type:
                continue
            hits.append(
                (
                    row["id"],
                    _adjust_similarity(
                        raw_score=_distance_to_similarity(row),
                        query_name=canonical_name,
                        row_name=str(row.get("canonical_name", "")),
                        query_description=description,
                        row_description=str(row.get("description", "")),
                    ),
                    str(row.get("canonical_name", "")),
                )
            )
            if len(hits) >= top_k:
                break
        return hits
    except Exception as exc:
        logger.warning("entity_vectors.find_similar: %s", exc)
        return []


def remove(db: "Database", entity_id: str) -> None:
    """Drop an entity's vector from the canonical table."""
    try:
        if TABLE not in db._lance_tables():
            return
        table = db.lance.open_table(TABLE)
        safe_id = entity_id.replace("'", "''")
        table.delete(f"id = '{safe_id}'")
    except Exception as exc:
        logger.warning("entity_vectors.remove: %s", exc)


__all__ = [name for name in globals() if not name.startswith("__")]
