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

    Three-stage match (#897 → #899 Phase B):
    1. Exact ``(canonical_name, entity_type)`` lookup — covers stable
       names like "Eugenio Córdoba" repeated across pages.
    2. **Embedding cosine** via LanceDB (`kg.entity_vectors`) over
       same-type entities. Catches semantic divergence in noun
       phrases ("Racial Economic Exclusion" vs "Race and Economic
       Marginalization") that pure SequenceMatcher misses. Cosine
       >= 0.92 → auto-merge; 0.75–0.92 → logged for future review
       gate (#377); <0.75 → fall through.
    3. SequenceMatcher fallback for the case where vectors aren't
       available yet (table empty, model failed to load, etc.). Keeps
       the 0.0.2 behaviour as a floor.

    On a successful merge (#2 or #3), the new ``canonical_name`` and
    ``aliases`` fold into the existing entity's ``aliases``. On a
    create, the new entity is indexed in LanceDB so future lookups
    can find it.

    Returns the entity ID. Idempotent on the exact path; the fuzzy
    paths preserve surface-form evidence via the aliases list.
    """
    existing = db.query(
        KnowledgeEntity,
        canonical_name=canonical_name,
        entity_type=entity_type,
    )
    if existing:
        return existing[0].id

    # Stage 2: embedding cosine. Lazy-imports the model on first call;
    # subsequent calls are free. Failures fall through to stage 3.
    matched: Optional[KnowledgeEntity] = None
    # _pending_review: (survivor_id, score, survivor_name) when we hit
    # the review band; consumed AFTER stage 4 creates the new entity
    # so the EntityMatchCandidate row references a real candidate id.
    _pending_review: Optional[tuple[str, float, str]] = None
    try:
        from fichero.kg import entity_vectors

        hits = entity_vectors.find_similar(
            db=db,
            canonical_name=canonical_name,
            entity_type=entity_type,
            description=description,
            top_k=3,
        )
        if hits:
            best_id, best_score, best_name = hits[0]
            if best_score >= entity_vectors.AUTO_MERGE_THRESHOLD:
                matched = db.get(KnowledgeEntity, best_id)
                if matched is not None:
                    logger.info(
                        "upsert_entity: embedding auto-merge %r → %s (%r, cosine=%.3f)",
                        canonical_name, best_id, best_name, best_score,
                    )
            elif best_score >= entity_vectors.REVIEW_THRESHOLD:
                # Mid-band: surface for the human review queue (#377 /
                # #899 Phase D). We DON'T auto-merge here — false
                # positives would silently collapse distinct entities.
                # Defer the EntityMatchCandidate write until after we
                # know the new entity's id (stage 4 below).
                logger.info(
                    "upsert_entity: embedding flagged-for-review "
                    "%r ~ %s (%r, cosine=%.3f) — queued for human review",
                    canonical_name, best_id, best_name, best_score,
                )
                _pending_review = (best_id, best_score, best_name)
    except Exception as exc:
        # Vector backend unhealthy — don't take down the catalogue.
        logger.warning("upsert_entity: embedding stage failed: %s", exc)

    # Stage 3: SequenceMatcher floor. Only run when embeddings didn't
    # decide a merge; mirrors the 0.0.2 behaviour as a safety net.
    if matched is None:
        same_type = db.query(KnowledgeEntity, entity_type=entity_type)
        matched = _fuzzy_match_existing(same_type, canonical_name)
        if matched is not None:
            logger.info(
                "upsert_entity: SequenceMatcher fallback merged "
                "%r → %s (%r)",
                canonical_name, matched.id, matched.canonical_name,
            )

    if matched is not None:
        # Fold the new surface form + aliases into the existing entity.
        existing_aliases = set(matched.aliases or [])
        existing_aliases.add(canonical_name)
        for alias in aliases or []:
            existing_aliases.add(alias)
        matched.aliases = sorted(existing_aliases - {matched.canonical_name})
        db.save(matched)
        # Refresh the vector to reflect the new alias set — the
        # encoded description grows with each merged occurrence so
        # future matches keep improving.
        try:
            from fichero.kg import entity_vectors

            entity_vectors.index_entity(
                db=db,
                entity_id=matched.id,
                entity_type=entity_type,
                canonical_name=matched.canonical_name,
                description=matched.description,
            )
        except Exception:
            pass
        return matched.id

    # Stage 4: create a brand-new entity + index its vector.
    entity = KnowledgeEntity(
        canonical_name=canonical_name,
        entity_type=entity_type,
        aliases=aliases or [],
        description=description,
    )
    db.save(entity)
    try:
        from fichero.kg import entity_vectors

        entity_vectors.index_entity(
            db=db,
            entity_id=entity.id,
            entity_type=entity_type,
            canonical_name=canonical_name,
            description=description,
        )
    except Exception as exc:
        logger.warning("upsert_entity: failed to index new entity vector: %s", exc)

    # Stage 5: write the EntityMatchCandidate row when stage 2 hit the
    # review band. The survivor is the existing entity (higher claim
    # count typically, definitely the older one); the candidate is the
    # newly-created entity. Reviewer decides later via the review
    # queue API. (#899 Phase D / #377)
    if _pending_review is not None:
        survivor_id, score, survivor_name = _pending_review
        try:
            from fichero.knowledge_models import (
                EntityMatchCandidate,
                PendingMatchMethod,
                PendingMatchState,
            )
            db.save(EntityMatchCandidate(
                survivor_entity_id=survivor_id,
                candidate_entity_id=entity.id,
                score=float(score),
                method=PendingMatchMethod.embedding_cosine,
                state=PendingMatchState.pending,
                reason=(
                    f"embedding cosine {score:.3f} between "
                    f"{canonical_name!r} and {survivor_name!r}"
                ),
            ))
        except Exception as exc:
            logger.warning("upsert_entity: failed to queue review candidate: %s", exc)

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
