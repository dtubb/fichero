"""Deterministic readable rendering of the KG (biography / regest / gazetteer).

spec: docs/contributor/specs/kg-readable-representation.md

The Reiter & Dale NLG pipeline, built as small pure functions over KnowledgeClaim so the
whole thing is testable without a GUI, an engine, or an LLM. NOTHING here calls a model:
the prose is a pure function of stored claims (the `narrative_v1` LLM prompt is what this
replaces). Sentence-level composition already lives in `knowledge/paragraph.py`; this module
adds the entry/biography-scale stages around it (Reiter & Dale). Built so far:

  1. content determination — `select_entry_claims`: which claims belong in an entry.
  2. document structuring   — `order_claims`: chronological (time_start / date_values)
     or by source (document → page → offset).
  3. aggregation            — `aggregate_claims`: collapse same-(subject,verb) claims to a
     count + distinct objects + place distribution, keeping every claim_id for citation.
  5. referring expressions  — `referring_expression`: full name first, family name after.
  6. realisation            — `render_aggregation`: phrase an Aggregation per language
     (es/en glue for count/places; the verb + objects stay the claim's own words).

Not yet built: stage 4 (lexicalisation — per-language verb lexicon) beyond the count/place
glue; deferred until the corpus's languages + real verb vocab are grounded (spec open Q).
See docs/contributor/specs/kg-readable-representation.md for the pipeline + behaviors.
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
    # input order because Python's sort is stable. The spec dates a claim by its
    # event/attestation date, so when time_start is absent fall back to the
    # earliest `date_values` start (evidential dates) before treating it as undated.
    start = claim.time_start
    if not start and claim.date_values:
        starts = [dv.start for dv in claim.date_values if dv.start]
        if starts:
            start = min(starts)
    start = start or ""
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
    places: list[str]
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
            agg = Aggregation(
                subject=subject, verb=verb, objects=[], places=[], count=0, claim_ids=[]
            )
            groups[key] = agg
            order.append(key)
        agg.count += 1
        agg.claim_ids.append(claim.id)
        if obj is not None and obj not in agg.objects:
            agg.objects.append(obj)
        place = claim.claim_location
        if place and place not in agg.places:
            agg.places.append(place)
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


# Stage 6 — realisation. ponytail: a minimal per-language phrase table for the
# count/place scaffolding ONLY. The verb + objects come from the claim's own SVO
# (already in the source's language — we never translate); this table supplies the
# language-specific glue ("N veces", "en X y Y" / "N times", "at X and Y"). Add a
# language by adding a row. Escalate to Grammatical Framework (the Abstract
# Wikipedia path) only when morphology outgrows this.
_REALISATION = {
    "es": {"times": "veces", "at": "en", "and": "y"},
    "en": {"times": "times", "at": "at", "and": "and"},
}


def _join_list(items: list[str], conjunction: str) -> str:
    """"A, B y C" / "A, B and C" — the last item joined by the language's conjunction."""
    parts = [p for p in items if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return f"{', '.join(parts[:-1])} {conjunction} {parts[-1]}"


def render_aggregation(agg: "Aggregation", language: str = "es") -> str:
    """Stage 6 — realise one Aggregation into a sentence in `language`.

    Deterministic, no LLM. The subject/verb are the claim's own words (source
    language); this only phrases the count and the place distribution.
    """
    glue = _REALISATION.get(language, _REALISATION["en"])
    head = " ".join(part for part in (agg.subject, agg.verb) if part).strip()
    if agg.count > 1:
        body = f"{head} {agg.count} {glue['times']}".strip()
    elif agg.objects:
        body = f"{head} {_join_list(agg.objects, glue['and'])}".strip()
    else:
        body = head
    if not body:
        return ""
    if agg.places:
        body = f"{body} ({glue['at']} {_join_list(agg.places, glue['and'])})"
    return body if body.endswith(".") else body + "."
