"""Deterministic readable rendering of the KG (biography / regest / gazetteer).

spec: docs/contributor/specs/kg-readable-representation.md

The Reiter & Dale NLG pipeline, built as small pure functions over KnowledgeClaim so the
whole thing is testable without a GUI, an engine, or an LLM. NOTHING here calls a model:
the prose is a pure function of stored claims (the `narrative_v1` LLM prompt is what this
replaces). Sentence-level composition already lives in `knowledge/paragraph.py`; this module
adds the entry/biography-scale stages around it — starting with:

  1. content determination — which claims belong in an entity's entry.
  2. document structuring   — the order they're presented in (chronological / by source).

Later stages (aggregation, lexicalisation per language, referring expressions, realisation)
land on top of these, each test-first. See the spec's pipeline section.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from fichero_server.knowledge.paragraph import (
    _claim_object,
    _claim_subject,
    _claim_verb,
    _normalize,
)
from fichero_server.models.knowledge import KnowledgeClaim


class Ordering(str, Enum):
    """How an entry's claims are sequenced (Reiter & Dale stage 2)."""

    chronological = "chronological"
    by_source = "by_source"


def select_entry_claims(
    claims: Sequence[KnowledgeClaim], entity_id: str
) -> list[KnowledgeClaim]:
    """Stage 1 — content determination.

    The claims that belong in ``entity_id``'s entry: those it is the subject of, plus those
    that mention it (``entity_ids``). Input order is preserved (structuring is stage 2's job).
    """
    return [
        claim
        for claim in claims
        if claim.subject_entity_id == entity_id or entity_id in (claim.entity_ids or [])
    ]


def _chronological_key(claim: KnowledgeClaim) -> tuple[bool, str]:
    # Undated claims sort last (True > False); dated claims sort by their start.
    # time_start is an ISO-ish string, so a lexical sort is date order. Ties keep
    # input order because Python's sort is stable.
    start = claim.time_start or ""
    return (start == "", start)


def _by_source_key(claim: KnowledgeClaim) -> tuple[bool, str, str, int]:
    # Group by source document, then by position within it (page, then char offset),
    # so a reader can follow one record at a time. Sourceless (manually-asserted)
    # claims sort last.
    doc = claim.source_document_id or ""
    return (
        doc == "",
        doc,
        claim.source_page_label or "",
        claim.source_char_start if claim.source_char_start is not None else 0,
    )


def order_claims(
    claims: Sequence[KnowledgeClaim], ordering: Ordering
) -> list[KnowledgeClaim]:
    """Stage 2 — document structuring. Deterministic; never drops a claim."""
    if ordering == Ordering.chronological:
        return sorted(claims, key=_chronological_key)
    return sorted(claims, key=_by_source_key)


@dataclass
class Aggregation:
    """Stage 3 output — one (subject, verb) collapsed across its claims.

    Repetition becomes a count plus the distinct objects/places, so "witnessed the
    will, witnessed the sale, …" renders as one sentence. `claim_ids` keeps every
    contributing claim for citation (provenance is never lost by aggregating).
    """

    subject: str | None
    verb: str | None
    objects: list[str]
    count: int
    claim_ids: list[str]


def aggregate_claims(claims: Sequence[KnowledgeClaim]) -> list[Aggregation]:
    """Stage 3 — aggregation. Group claims by (subject, verb); within a group keep
    the count of claims and the DISTINCT objects. First-seen group order is preserved
    (ordering is stage 2's job; this doesn't re-sort). No claim is dropped — every id
    is retained for citation."""
    groups: dict[tuple[str, str], Aggregation] = {}
    order: list[tuple[str, str]] = []
    for claim in claims:
        subject = _claim_subject(claim)
        verb = _claim_verb(claim)
        obj = _claim_object(claim)
        key = (_normalize(subject or ""), _normalize(verb or ""))
        agg = groups.get(key)
        if agg is None:
            agg = Aggregation(subject=subject, verb=verb, objects=[], count=0, claim_ids=[])
            groups[key] = agg
            order.append(key)
        agg.count += 1
        agg.claim_ids.append(claim.id)
        if obj is not None and obj not in agg.objects:
            agg.objects.append(obj)
    return [groups[key] for key in order]


def referring_expression(full_name: str, *, first_mention: bool) -> str:
    """Stage 5 — referring expressions.

    Full name on first mention; the family name thereafter. ponytail: "family name =
    last whitespace token" is a heuristic that holds for most Spanish/European names
    in the corpus (e.g. "María de Córdoba" -> "Córdoba"); refine per-language (two
    Spanish surnames, particles like "de la") if it proves too blunt. Pronoun-level
    reference (stage 5's finer grain) needs the entity's gender + language and lands
    with lexicalisation.
    """
    name = " ".join(full_name.split())  # collapse whitespace
    if not name:
        return ""
    if first_mention:
        return name
    tokens = name.split(" ")
    return tokens[-1] if len(tokens) > 1 else name
