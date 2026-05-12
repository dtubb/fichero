"""Entity writer helpers for catalogue extractors.

Centralizes the upsert + claim save pattern so each extractor in
`extractors.py` doesn't reimplement it. Bridges structured-extraction
outputs (people, places, organizations, events, concepts) into the
existing knowledge-graph layer (`KnowledgeEntity`, `KnowledgeClaim`).

See `docs/architecture/typed_entity_storage.md` §0 for the design and
`docs/superpowers/plans/2026-04-28-typed-entity-storage.md` for the
implementation plan (#728).
"""

from __future__ import annotations

import logging
from typing import Optional

from fichero.db import Database
from fichero.knowledge_models import (
    ClaimType,
    EntityType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
)

logger = logging.getLogger(__name__)


def _fuzzy_match_existing(
    existing: list[KnowledgeEntity],
    canonical_name: str,
    threshold: float = 0.78,
) -> Optional[KnowledgeEntity]:
    """Return the best fuzzy match for ``canonical_name`` among existing
    entities of the same type, or None if nothing scores above threshold.

    Handles two divergence patterns observed on per-page extraction (#897):
    - **Surface variation**: "Eugenio Córdoba" vs "Eugenio Cordoba" vs
      "E. Córdoba". Caught by SequenceMatcher token-set similarity.
    - **Rephrasing the same recurring scene as N events**: the LLM
      titles the same monologue differently per page ("Narrator's
      Account of Racial Economic Exclusion" / "Narrator's Monologue
      on Race and Economic Marginalization" / etc.). Caught by
      token-overlap on the noun phrase after stop-word removal.

    Threshold defaults to 0.78 — empirically separates the 6-event
    monologue cluster (~0.85 between any two) from genuinely distinct
    events ("Filing of the Petition" vs "Sale of the Estate" — 0.30).

    The match is a heuristic, not a knowledge-graph linker. For a real
    entity-resolution pipeline we'd swap in splink or dedupe.io with
    learned model weights (#897 follow-up).
    """
    from difflib import SequenceMatcher

    if not canonical_name or not existing:
        return None

    # Normalise: lower, drop punctuation. Token-set similarity is
    # more forgiving of reordering than raw SequenceMatcher.ratio.
    def _tokens(s: str) -> set[str]:
        cleaned = "".join(c if c.isalnum() or c.isspace() else " " for c in s.lower())
        return {tok for tok in cleaned.split() if len(tok) > 2}

    needle_tokens = _tokens(canonical_name)
    needle_lower = canonical_name.lower()

    best: tuple[float, Optional[KnowledgeEntity]] = (0.0, None)
    for ent in existing:
        # Two metrics, take the max so either signal can hit threshold.
        seq_ratio = SequenceMatcher(None, needle_lower, ent.canonical_name.lower()).ratio()
        ent_tokens = _tokens(ent.canonical_name)
        if needle_tokens and ent_tokens:
            intersection = len(needle_tokens & ent_tokens)
            union = len(needle_tokens | ent_tokens)
            token_ratio = intersection / union if union else 0.0
        else:
            token_ratio = 0.0
        score = max(seq_ratio, token_ratio)
        if score > best[0]:
            best = (score, ent)

    return best[1] if best[0] >= threshold else None


def upsert_entity(
    db: Database,
    canonical_name: str,
    entity_type: EntityType,
    aliases: Optional[list[str]] = None,
    description: Optional[str] = None,
) -> str:
    """Look up entity by ``(canonical_name, entity_type)``; create if missing.

    Two-stage match (#897):
    1. Exact ``(canonical_name, entity_type)`` lookup — covers stable
       names like "Eugenio Córdoba" repeated across pages.
    2. Fuzzy fallback over all entities of the same type — catches LLM
       rephrasings of the same recurring scene as N event entities, plus
       accent/case drift. When a fuzzy match hits, the new ``canonical_name``
       and ``aliases`` fold into the existing entity's ``aliases``
       (preserving surface-form evidence) and we reuse its id.

    Returns the entity ID. Still idempotent on the exact path; the
    fuzzy path is the new contract.
    """
    existing = db.query(
        KnowledgeEntity,
        canonical_name=canonical_name,
        entity_type=entity_type,
    )
    if existing:
        return existing[0].id

    # Fuzzy fallback. Scope: all entities of this type. Could be tightened
    # to "same source document" if cross-doc bleed becomes a problem, but
    # the cross-doc consolidation is actually a feature for the KG: one
    # Davidson across the whole library.
    same_type = db.query(KnowledgeEntity, entity_type=entity_type)
    matched = _fuzzy_match_existing(same_type, canonical_name)
    if matched is not None:
        # Fold the new surface form + aliases into the existing entity.
        existing_aliases = set(matched.aliases or [])
        existing_aliases.add(canonical_name)
        for alias in aliases or []:
            existing_aliases.add(alias)
        matched.aliases = sorted(existing_aliases - {matched.canonical_name})
        db.save(matched)
        logger.info(
            "upsert_entity: fuzzy-matched %r → existing entity %s (%r); folded aliases",
            canonical_name, matched.id, matched.canonical_name,
        )
        return matched.id

    entity = KnowledgeEntity(
        canonical_name=canonical_name,
        entity_type=entity_type,
        aliases=aliases or [],
        description=description,
    )
    db.save(entity)
    return entity.id


def save_claim(
    db: Database,
    text: str,
    source_document_id: str,
    entity_ids: Optional[list[str]] = None,
    source_excerpt: Optional[str] = None,
    source_page_label: Optional[str] = None,
    claim_type: ClaimType = ClaimType.fact,
    confidence: float = 0.5,
    metadata: Optional[dict] = None,
    epistemic_status: Optional[EpistemicStatus] = None,
) -> str:
    """Save a `KnowledgeClaim` row. Returns the claim ID.

    Claims are document-scoped textual assertions linked to entities via
    ``entity_ids``. Date-style claims (no canonical entity to dedup) pass
    an empty list for ``entity_ids``; the normalized date lives in
    ``metadata['date_normalized']``.

    ``source_page_label`` lands on the dedicated ``KnowledgeClaim`` field
    so cross-doc views and graph traversal can answer "which page of
    which document mentions this entity?"

    ``epistemic_status`` records the LLM-assigned confidence label
    (tentative/confirmed/rejected) so the inspector can filter and
    badge claims. None means leave the default on the model.
    """
    claim = KnowledgeClaim(
        text=text,
        source_document_id=source_document_id,
        entity_ids=entity_ids or [],
        source_excerpt=source_excerpt,
        source_page_label=source_page_label,
        claim_type=claim_type,
        confidence=confidence,
        metadata=metadata or {},
        epistemic_status=epistemic_status,
    )
    db.save(claim)
    return claim.id
