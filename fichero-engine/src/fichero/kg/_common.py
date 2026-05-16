"""Shared helpers across the kg submodules.

Three small primitives that were re-implemented in five places before
this consolidation:

- ``enum_value`` — extracts ``.value`` from an Enum or falls back to
  ``str()`` for plain strings. Used wherever KG code stringifies an
  ``EntityType`` / ``EpistemicStatus`` / ``ClaimType`` / ``SourceAuthority``.
- ``slug_verb`` — canonical predicate slug used by both
  ``triples._predicate_uri`` and ``triangulation._predicate_slug``.
  These had to stay in lockstep so SPARQL queries over the RDF graph
  agree with the in-Python aggregation; a single source of truth
  removes the drift risk.
- ``extract_svo`` — pulls ``(verb, object_text)`` from a claim's
  ``metadata`` dict, stripped and falling back to ``""``. Four call
  sites had the same three lines.
- ``parse_kwarg_repr`` — detects a leaked kwarg-style repr
  (``verb='X', object='Y'``) and pulls the structured keys back out.
  Shared by the extractor write path (``_normalize_kwarg_repr_fields``)
  and the #1030 repair migration so detection can't drift between them.
- ``CANONICAL_VERBS`` / ``canonical_verb`` — controlled vocabulary for
  ``KnowledgeClaim.predicate_canonical`` (#1123 Phase C). Maps free-text
  natural-language verbs to a canonical slug from a small bounded set
  (~45 verbs across ontological / spatial / temporal / speech / role /
  kinship / property / causal / quantitative / authorship / domain
  categories). The lookup is case-insensitive on the stripped verb.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from fichero.knowledge_models import KnowledgeClaim


def enum_value(x: Any) -> str:
    """Return ``x.value`` when ``x`` is an enum, else ``str(x)``.

    KG models pass through serialization layers that sometimes leave
    enums as enums and sometimes coerce them to strings already.
    Callers want a string either way.
    """
    return x.value if hasattr(x, "value") else str(x)


def slug_verb(verb: str) -> str:
    """Canonical predicate slug for an SVO verb.

    Rules (must match what ``triples._predicate_uri`` produces after
    the namespace strip — the RDF predicate URI and the triangulation
    aggregation key are the same string):

    - Empty / whitespace verb → ``"assertedAbout"`` (the generic fallback).
    - Lowercase + alphanumerics-only; non-alnum chars become ``-``.
    - Collapse runs of dashes; trim leading/trailing dashes.
    - Leading-digit slugs get a ``v-`` prefix so they're valid URI
      fragments.
    """
    if not verb or not verb.strip():
        return "assertedAbout"
    slug = "".join(c if c.isalnum() else "-" for c in verb.lower().strip())
    slug = "-".join(p for p in slug.split("-") if p)
    if not slug or slug[0].isdigit():
        slug = "v-" + slug
    return slug


def extract_svo(claim: "KnowledgeClaim") -> tuple[str, str]:
    """Pull ``(verb, object_text)`` from a claim's metadata.

    Returns stripped strings, falling back to ``""`` when either key
    is missing. Centralises the ``meta = claim.metadata or {}`` /
    ``.get("verb") or ""`` / ``.strip()`` boilerplate that four KG
    modules each carried.
    """
    meta = claim.metadata or {}
    verb = (meta.get("verb") or "").strip()
    obj_text = (meta.get("object") or "").strip()
    return verb, obj_text


# Keys the extractor prompt uses in its kwarg-style examples
# ("name='X', verb='Y', object='Z'"). Weaker / fallback models
# sometimes echo that whole literal string back into a *single*
# field instead of returning structured keys — see #1030.
_KWARG_REPR_SEGMENT = re.compile(
    r"(name|verb|object)\s*=\s*(['\"])(.*?)\2"
    r"(?=\s*,\s*(?:name|verb|object)\s*=|\s*$)",
    re.DOTALL,
)


# =============================================================================
# #1123 Phase C — Canonical predicate vocabulary
# =============================================================================
# Free-text variants → canonical slug. The canonical slug is what gets
# written to ``KnowledgeClaim.predicate_canonical`` and what SPARQL /
# aggregation queries pivot on. The variant (free text) stays in
# ``predicate_verb`` for human-readable display.
#
# Categories are documented in the section dividers below — keep them
# updated when you add a verb so the controlled vocabulary stays
# discoverable from this file alone. Unknown verbs return ``None`` from
# ``canonical_verb`` so the field encodes honest absence rather than a
# guessed mapping. The reasoning: a misclassified canonical_verb is
# worse than a null one, because downstream aggregations (SPARQL, the
# Tinderbox-style focus graph, the entity inspector) all assume
# canonical means "this predicate is known to refer to category X."
#
# When tuning: prefer adding variants under existing canonical slugs
# over inventing new slugs. The ~45-slug ceiling is intentional —
# every slot pays for itself by being a node the UI can render with
# a dedicated affordance (icon, filter, render hint).

CANONICAL_VERBS: dict[str, str] = {
    # --- ontological / identity ---
    "is": "is_a",
    "is a": "is_a",
    "is an": "is_a",
    "is the": "is_a",
    "is_a": "is_a",
    "instance_of": "instance_of",
    "instance of": "instance_of",
    "part of": "part_of",
    "part_of": "part_of",
    "is part of": "part_of",
    "belongs to": "belongs_to",
    "belongs_to": "belongs_to",
    # --- spatial ---
    "located in": "located_in",
    "located_in": "located_in",
    "is located in": "located_in",
    "is in": "located_in",
    "lives in": "located_in",
    "resides in": "located_in",
    "near": "near",
    "near to": "near",
    "contains": "contains",
    "borders": "borders",
    "borders on": "borders",
    # --- temporal ---
    "preceded by": "preceded_by",
    "preceded_by": "preceded_by",
    "before": "preceded_by",
    "followed by": "followed_by",
    "followed_by": "followed_by",
    "after": "followed_by",
    "contemporary with": "contemporary_with",
    "contemporary_with": "contemporary_with",
    "dated to": "dated_to",
    "dated_to": "dated_to",
    "occurred in": "occurred_in",
    "occurred_in": "occurred_in",
    "happened in": "occurred_in",
    # --- speech / testimony ---
    "said": "said",
    "stated": "said",
    "declared": "said",
    "asserted": "said",
    "claimed": "claimed",
    "denied": "denied",
    "testified": "testified",
    "testified that": "testified",
    "testified about": "testified_about",
    "petitioned": "petitioned",
    "requested": "requested",
    "reported": "reported",
    "argued": "argued",
    # --- role / office ---
    "served as": "served_as",
    "served_as": "served_as",
    "became": "served_as",
    "appointed": "appointed",
    "appointed as": "appointed",
    "was appointed": "appointed",
    "dismissed": "dismissed",
    "held office": "held_office",
    "held_office": "held_office",
    "held the office of": "held_office",
    "elected": "elected",
    # --- kinship ---
    "parent of": "parent_of",
    "parent_of": "parent_of",
    "father of": "parent_of",
    "mother of": "parent_of",
    "child of": "child_of",
    "child_of": "child_of",
    "son of": "child_of",
    "daughter of": "child_of",
    "sibling of": "sibling_of",
    "sibling_of": "sibling_of",
    "brother of": "sibling_of",
    "sister of": "sibling_of",
    "married to": "married_to",
    "married_to": "married_to",
    "married": "married_to",
    "wife of": "married_to",
    "husband of": "married_to",
    "descendant of": "descendant_of",
    "descendant_of": "descendant_of",
    "descended from": "descendant_of",
    "ancestor of": "ancestor_of",
    "ancestor_of": "ancestor_of",
    # --- property / transfer ---
    "owns": "owns",
    "owned": "owns",
    "transferred": "transferred",
    "transferred to": "transferred",
    "inherited": "inherited",
    "inherited from": "inherited",
    "sold": "sold",
    "sold to": "sold",
    "bought": "bought",
    "purchased": "bought",
    "granted": "granted",
    "granted to": "granted",
    "received": "received",
    # --- causal ---
    "caused": "caused",
    "led to": "caused",
    "prevented": "prevented",
    "enabled": "enabled",
    "made possible": "enabled",
    "resulted in": "resulted_in",
    "resulted_in": "resulted_in",
    # --- quantitative ---
    "measured": "measured",
    "valued at": "valued_at",
    "valued_at": "valued_at",
    "worth": "valued_at",
    "counted": "counted",
    # --- authorship / record-keeping ---
    "wrote": "wrote",
    "authored": "wrote",
    "signed": "signed",
    "witnessed": "witnessed",
    "recorded": "recorded",
    # --- domain (archival / historical) ---
    "filed": "filed",
    "compiled": "compiled",
    "copied": "copied",
    "translated": "translated",
    "annotated": "annotated",
}


def canonical_verb(verb: str | None) -> str | None:
    """Map a free-text predicate verb to a canonical slug.

    Lookup is case-insensitive on the stripped verb. Returns ``None``
    for empty input and for verbs not in the controlled vocabulary —
    honest absence rather than a guessed mapping. Callers that need
    *any* URI fragment for SPARQL (regardless of canonical-ness) should
    fall back to ``slug_verb(verb)``; this function answers the narrower
    question "is this verb in the controlled vocabulary?"

    Used by ``_entity_writer.save_claim`` to populate
    ``KnowledgeClaim.predicate_canonical`` at write time (#1123 Phase C).
    """
    if not verb:
        return None
    return CANONICAL_VERBS.get(verb.lower().strip())


def parse_kwarg_repr(text: str) -> dict[str, str] | None:
    """Parse a Python-kwarg-style repr like ``verb='is', object='a mine'``
    into ``{"verb": "is", "object": "a mine"}``.

    Returns ``None`` when ``text`` doesn't *start* with one of the known
    extractor keys followed by ``=`` and a quote — i.e. it's ordinary
    prose, not a leaked repr. (#1030)

    Shared between the extractor write path (``extractors._normalize_kwarg_repr_fields``)
    and the ``MigrationRunner.repair_kg_svo_repr_leak`` cleanup so the
    forward guard and the backfill repair agree on what counts as a leak.
    """
    s = (text or "").strip()
    if not re.match(r"^(name|verb|object)\s*=\s*['\"]", s):
        return None
    out: dict[str, str] = {}
    for m in _KWARG_REPR_SEGMENT.finditer(s):
        out[m.group(1)] = m.group(3).strip()
    return out or None
