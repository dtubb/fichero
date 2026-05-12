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
    """Result of triangulation aggregation for one triple."""
    key: TripleKey
    support_count: int
    source_document_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]

    @property
    def corroboration(self) -> str:
        """Human-readable corroboration label."""
        if self.support_count >= TRIANGULATED_THRESHOLD:
            return "triangulated"
        if self.support_count >= CORROBORATED_THRESHOLD:
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


def _predicate_slug(verb: str) -> str:
    """Predicate slug — must match fichero.kg.triples._predicate_uri's
    URI slug exactly so SPARQL queries over the RDF graph agree with
    the in-Python aggregation below."""
    if not verb or not verb.strip():
        return "assertedAbout"
    slug = "".join(c if c.isalnum() else "-" for c in verb.lower().strip())
    slug = "-".join(p for p in slug.split("-") if p)
    if not slug or slug[0].isdigit():
        slug = "v-" + slug
    return slug


def compute_support_counts(db: "Database") -> dict[TripleKey, TripleSupport]:
    """Aggregate KnowledgeClaim rows by canonical SVO triple key.

    O(N) over claim count. Returns a dict keyed by TripleKey; only
    triples with at least one supporting claim appear. Claims with
    no entity_ids (date-only claims) are skipped — triangulation
    isn't meaningful for "1933-07-23 records X" since each is
    uniquely tied to a date.
    """
    from fichero.knowledge_models import KnowledgeClaim

    # Group: TripleKey → (sources, claims)
    grouped: dict[TripleKey, tuple[set[str], list[str]]] = defaultdict(
        lambda: (set(), [])
    )

    for claim in db.query(KnowledgeClaim):
        meta = claim.metadata or {}
        verb = (meta.get("verb") or "").strip()
        object_text = _normalize_object(meta.get("object") or "")
        predicate = _predicate_slug(verb)

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

    return {
        key: TripleSupport(
            key=key,
            support_count=len(sources),
            source_document_ids=tuple(sorted(sources)),
            claim_ids=tuple(claims),
        )
        for key, (sources, claims) in grouped.items()
    }


def triples_for_entity(
    db: "Database",
    entity_id: str,
) -> list[TripleSupport]:
    """Return all triples involving ``entity_id`` as subject, sorted
    by descending support_count.

    Use case: the entity detail view in the KG inspector shows
    "Davidson is described as an alternative spelling of Deibinson
    (triangulated, 6 sources)" — this function provides the rows.
    """
    all_supports = compute_support_counts(db)
    matches = [
        s for s in all_supports.values()
        if s.key.subject_id == entity_id
    ]
    matches.sort(key=lambda s: -s.support_count)
    return matches


def triangulated_facts(
    db: "Database",
    threshold: int = TRIANGULATED_THRESHOLD,
) -> list[TripleSupport]:
    """Return only the corpus-wide triangulated triples (support >= threshold).

    Use case: a "most-supported facts in this library" view that
    surfaces what the corpus most strongly attests.
    """
    all_supports = compute_support_counts(db)
    return sorted(
        (s for s in all_supports.values() if s.support_count >= threshold),
        key=lambda s: -s.support_count,
    )
