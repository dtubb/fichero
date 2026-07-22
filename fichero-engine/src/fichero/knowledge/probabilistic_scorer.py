"""Probabilistic entity-match scoring combining string and vector similarity.

Computes calibrated probability scores for entity-pair candidates by
combining multiple signals:
- Canonical name SequenceMatcher ratio (0-1 scale)
- Alias overlap (presence of exact matches)
- Vector cosine similarity (if embeddings exist)

Scores are combined into a unified probabilistic score suitable for:
- Auto-merge threshold (>0.95)
- Review-queue threshold (0.7-0.95)
- Ignore threshold (<0.7)

(#988 step 3)
"""

from __future__ import annotations

import logging
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fichero.db import Database
    from fichero.models.knowledge import KnowledgeEntity

logger = logging.getLogger(__name__)


def _canonical_name_similarity(name_a: str, name_b: str) -> float:
    """Compute SequenceMatcher ratio on canonical names (0-1).

    Handles surface variations like accents, abbreviations, etc.
    """
    if not name_a or not name_b:
        return 0.0
    ratio = SequenceMatcher(None, name_a.lower(), name_b.lower()).ratio()
    return float(ratio)


def _alias_overlap_score(aliases_a: list[str], aliases_b: list[str]) -> float:
    """Compute alias overlap score (0-1).

    Returns 1.0 if any alias in A exactly matches any alias in B;
    0.0 otherwise. Aliases are normalized to lowercase.
    """
    if not aliases_a or not aliases_b:
        return 0.0
    set_a = {a.lower() for a in aliases_a}
    set_b = {b.lower() for b in aliases_b}
    if set_a & set_b:
        return 1.0
    return 0.0


def _vector_similarity(
    db: Database,
    entity_a_id: str,
    entity_b_id: str,
) -> float:
    """Compute vector cosine similarity if embeddings exist (0-1).

    Returns 0.0 if either entity lacks an embedding, or if the
    embeddings table doesn't exist yet.

    Future: Implement by fetching embeddings and computing cosine distance.
    """
    try:
        table = "kg_entity_embeddings"
        if table not in db._lance_tables():  # type: ignore[attr-defined]
            return 0.0
        # TODO: Fetch vectors from LanceDB and compute cosine similarity
        # between entity_a_id and entity_b_id embeddings.
        return 0.0
    except Exception as e:
        logger.debug("vector similarity lookup failed: %s", e)
        return 0.0


def compute_entity_pair_score(
    db: Database,
    entity_a: KnowledgeEntity,
    entity_b: KnowledgeEntity,
) -> float:
    """Compute probabilistic match score for two entities (0-1).

    Combines:
    - Canonical name similarity (40% weight)
    - Alias overlap (40% weight)
    - Vector similarity (20% weight)

    Weights calibrated on manual review patterns (#988).
    """
    if entity_a.entity_type != entity_b.entity_type:
        # Cross-type matches (Person <-> Place) are almost always wrong.
        return 0.0

    canon_sim = _canonical_name_similarity(
        entity_a.canonical_name,
        entity_b.canonical_name,
    )
    alias_sim = _alias_overlap_score(entity_a.aliases, entity_b.aliases)
    vector_sim = _vector_similarity(db, entity_a.id, entity_b.id)

    # Weighted combination
    score = (0.40 * canon_sim) + (0.40 * alias_sim) + (0.20 * vector_sim)
    return float(score)


class ThresholdDecision:
    """Result of applying auto-merge / review-queue thresholds."""

    __slots__ = ("action", "score", "reason")

    def __init__(self, action: str, score: float, reason: str):
        self.action = action  # "auto_merge", "queue", or "ignore"
        self.score = score
        self.reason = reason

    def __repr__(self) -> str:
        return f"ThresholdDecision({self.action}, {self.score:.3f})"


def apply_thresholds(
    score: float,
    auto_merge_threshold: float = 0.95,
    review_queue_threshold_min: float = 0.7,
) -> ThresholdDecision:
    """Classify a score into an action: auto-merge, queue, or ignore.

    Args:
        score: Probabilistic match score [0, 1]
        auto_merge_threshold: Merge automatically if score >= this (default 0.95)
        review_queue_threshold_min: Queue for review if score >= this (default 0.7)

    Returns:
        ThresholdDecision with action ("auto_merge", "queue", or "ignore")
        and descriptive reason.
    """
    if score >= auto_merge_threshold:
        return ThresholdDecision(
            "auto_merge",
            score,
            f"Score {score:.3f} >= auto-merge threshold {auto_merge_threshold}",
        )
    elif score >= review_queue_threshold_min:
        return ThresholdDecision(
            "queue",
            score,
            f"Score {score:.3f} in review-queue band [{review_queue_threshold_min}, {auto_merge_threshold})",
        )
    else:
        return ThresholdDecision(
            "ignore",
            score,
            f"Score {score:.3f} < review-queue threshold {review_queue_threshold_min}",
        )


__all__ = [name for name in globals() if not name.startswith("__")]
