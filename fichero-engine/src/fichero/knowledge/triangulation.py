"""Cross-source triangulation of KG claims (#900).

Computes a derived **support count** for each unique
(subject, predicate, object) triple: how many distinct source
documents assert the same fact. The result is a second epistemic
axis on top of the per-claim ``epistemic_status``:

  support_count == 1  → single-source (no triangulation)
  support_count == 2  → corroborated
  support_count >= 3  → triangulated

Crucially distinct from ``KnowledgeClaim.epistemic_status``:

- ``epistemic_status`` is the LLM's read of how firmly *one passage*
  asserts the fact (tentative / confirmed / rejected). Sentence-local.
- ``support_count`` is how many independent passages assert the same
  fact across the whole corpus. Corpus-global.

Both signals are useful and the UI should show both — a fact that's
hedged in every source ("Pérez may have signed...") but appears in
6 sources is meaningfully different from a fact stated directly in
one source.

Independence caveat (v1 simplification): support_count just counts
distinct ``source_document_id`` values. Two documents quoting each
other will both contribute even though they're not independent
evidence. Future refinement could weight by citation distance.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fichero.kg._common import enum_value, extract_svo, slug_verb

if TYPE_CHECKING:  # pragma: no cover
    from fichero.db import Database

logger = logging.getLogger(__name__)


# Tunable thresholds — exposed as module constants so the API
# endpoint / inspector UI can override per user preference.
CORROBORATED_THRESHOLD = 2
TRIANGULATED_THRESHOLD = 3


@dataclass(frozen=True)
class TripleKey:
    """Canonical key for grouping claims that assert the same fact.

    Two claims with the same subject + predicate (slugified verb) +
    object string are treated as the same underlying fact even when
    their text is phrased differently. The KnowledgeEntity layer
    already deduplicates subjects (Phase B fuzzy match); the object
    side stays a literal string for v1 since we don't yet resolve
    object references to canonical entities.
    """
    subject_id: str
    predicate: str
    object_text: str


@dataclass(frozen=True)
class TripleSupport:
    """Result of triangulation aggregation for one triple.

    Two support metrics:
    - ``support_count`` — raw number of distinct source documents
      asserting the fact. The user-facing "is this triangulated?"
      question uses this.
    - ``weighted_support`` — same count, scaled by each contributing
      document's ``SourceAuthority`` (primary=1.0, secondary=0.6,
      tertiary=0.3). Distinguishes "3 archive originals all say X"
      from "3 textbook citations of the same blog post." (#903)
    """
    key: TripleKey
    support_count: int
    weighted_support: float
    source_document_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]

    @property
    def corroboration(self) -> str:
        """Human-readable corroboration label based on weighted support.

        Falls back to raw count when authority isn't set anywhere
        (so existing libraries don't suddenly show "single-source"
        on what used to be triangulated facts).
        """
        # The weighted_support metric is preferred — if it crosses
        # the threshold, the fact is triangulated regardless of raw
        # count (3 primaries + 5 tertiaries both clear 3.0).
        if self.weighted_support >= TRIANGULATED_THRESHOLD:
            return "triangulated"
        if self.weighted_support >= CORROBORATED_THRESHOLD:
            return "corroborated"
        return "single-source"


def _normalize_object(text: str) -> str:
    """Normalize an object phrase for grouping.

    Two claims that emit slightly different surface forms of the
    same object ("the deed" vs "the Deed") should still group. Pure
    lowercase + whitespace collapse. More aggressive normalisation
    (stemming, paraphrase clustering) lives in #899 Phase B's
    embedding space and could fold in later.
    """
    if not text:
        return ""
    return " ".join(text.lower().split())


# Predicate slug — shared with fichero.kg.triples._predicate_uri via
# fichero.kg._common.slug_verb so SPARQL queries over the RDF graph
# agree with the in-Python aggregation below.
_predicate_slug = slug_verb


def compute_support_counts(db: "Database") -> dict[TripleKey, TripleSupport]:
    """Aggregate KnowledgeClaim rows by canonical SVO triple key.

    O(N) over claim count. Returns a dict keyed by TripleKey; only
    triples with at least one supporting claim appear. Claims with
    no entity_ids (date-only claims) are skipped — triangulation
    isn't meaningful for "1933-07-23 records X" since each is
    uniquely tied to a date.
    """
    from fichero.models.knowledge import KnowledgeClaim

    # Group: TripleKey → (sources, claims)
    grouped: dict[TripleKey, tuple[set[str], list[str]]] = defaultdict(
        lambda: (set(), [])
    )

    for claim in db.query(KnowledgeClaim):
        verb, raw_object = extract_svo(claim)
        # Claims with no verb + no object are structurally empty SVO rows.
        # Treating them as "assertedAbout ''" collapses unrelated claims into
        # one synthetic triple and inflates corroboration metrics.
        if not (str(verb or "").strip() or str(raw_object or "").strip()):
            continue
        object_text = _normalize_object(raw_object)
        predicate = slug_verb(verb)

        # Each claim can link to multiple entities (rare). Emit a
        # separate triple for each (subject, predicate, object).
        for subject_id in (claim.entity_ids or []):
            key = TripleKey(
                subject_id=subject_id,
                predicate=predicate,
                object_text=object_text,
            )
            sources, claim_ids = grouped[key]
            if claim.source_document_id:
                sources.add(claim.source_document_id)
            claim_ids.append(claim.id)

    # Build authority weights for every source document that
    # contributes — one query, cached per call. (#903)
    authority_by_doc: dict[str, float] = {}
    try:
        from fichero.models import AUTHORITY_WEIGHTS, Document

        contributing_doc_ids: set[str] = set()
        for sources, _ in grouped.values():
            contributing_doc_ids.update(sources)
        for doc_id in contributing_doc_ids:
            doc = db.get(Document, doc_id)
            if doc is None:
                continue
            authority = enum_value(doc.source_authority) if doc.source_authority else "unknown"
            authority_by_doc[doc_id] = AUTHORITY_WEIGHTS.get(authority, 1.0)
    except Exception as exc:
        logger.warning("triangulation: authority lookup failed, weights default to 1.0: %s", exc)

    return {
        key: TripleSupport(
            key=key,
            support_count=len(sources),
            weighted_support=sum(
                authority_by_doc.get(doc_id, 1.0) for doc_id in sources
            ),
            source_document_ids=tuple(sorted(sources)),
            claim_ids=tuple(claims),
        )
        for key, (sources, claims) in grouped.items()
    }


def persist_support_counts(
    db: "Database",
    threshold: int = CORROBORATED_THRESHOLD,
) -> int:
    """Write cross-source support counts back onto ``KnowledgeClaim`` rows.

    For each claim, sets:

    - ``corroboration_count`` — number of distinct source documents asserting
      the same (subject, predicate, object) triple.  Replaces the write-time
      value (which is always 1 for a brand-new claim) with the corpus-global
      count.
    - ``weighted_corroboration_count`` — same aggregation, but weighted by
      each source document's ``SourceAuthority``.
    - ``corroborating_source_ids`` — sorted list of those document IDs, so the
      inspector can surface provenance without re-running the aggregation.

    Claims that share a TripleKey get the same ``corroboration_count``; claims
    with no ``entity_ids`` (date-only) keep their existing values because they
    don't participate in SVO grouping.

    Returns the number of claims updated.

    Design note: we re-use the *existing* ``corroboration_count`` /
    ``corroborating_source_ids`` fields rather than adding new columns.  Those
    fields were always intended as "multi-source support count" — they were just
    computed at write time (per-claim).  This function replaces the write-time
    value with the corpus-global value. (#900)
    """
    from fichero.models.knowledge import KnowledgeClaim

    supports = compute_support_counts(db)

    # Build a lookup: claim_id → TripleSupport for fast per-claim update.
    claim_to_support: dict[str, TripleSupport] = {}
    for support in supports.values():
        for cid in support.claim_ids:
            # A claim can map to multiple triples (when entity_ids has > 1
            # entry).  Keep the one with the highest support_count so the
            # stored value is conservative (max evidence).
            if cid not in claim_to_support or (
                support.support_count > claim_to_support[cid].support_count
            ):
                claim_to_support[cid] = support

    updated = 0
    for claim in db.query(KnowledgeClaim):
        support = claim_to_support.get(claim.id)
        if support is None:
            # Date-only claim or claim with no entity_ids — skip.
            continue
        new_count = support.support_count
        new_weighted_count = support.weighted_support
        new_sources = sorted(support.source_document_ids)
        # Only write back when the value changed to minimise DuckDB writes.
        if (
            claim.corroboration_count != new_count
            or claim.weighted_corroboration_count != new_weighted_count
            or list(claim.corroborating_source_ids) != new_sources
        ):
            claim.corroboration_count = new_count
            claim.weighted_corroboration_count = new_weighted_count
            claim.corroborating_source_ids = new_sources
            db.save(claim)
            updated += 1

    logger.info(
        "triangulation: persist_support_counts updated %d claims (threshold=%d)",
        updated,
        threshold,
    )
    return updated


def triples_for_entity(
    db: "Database",
    entity_id: str,
) -> list[TripleSupport]:
    """Return all triples involving ``entity_id`` as subject, sorted
    by descending weighted support.

    Use case: the entity detail view in the KG inspector shows
    "Davidson is described as an alternative spelling of Deibinson
    (triangulated, 6 sources)" — this function provides the rows.
    """
    all_supports = compute_support_counts(db)
    matches = [
        s for s in all_supports.values()
        if s.key.subject_id == entity_id
    ]
    matches.sort(key=lambda s: (-s.weighted_support, -s.support_count))
    return matches


def triangulated_facts(
    db: "Database",
    threshold: float = TRIANGULATED_THRESHOLD,
) -> list[TripleSupport]:
    """Return only the corpus-wide triangulated triples.

    A triple qualifies when its weighted support meets ``threshold``.

    Use case: a "most-supported facts in this library" view that
    surfaces what the corpus most strongly attests.
    """
    all_supports = compute_support_counts(db)
    return sorted(
        (s for s in all_supports.values() if s.weighted_support >= threshold),
        key=lambda s: (-s.weighted_support, -s.support_count),
    )


__all__ = [name for name in globals() if not name.startswith("__")]
