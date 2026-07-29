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
    from fichero_server.models.knowledge import KnowledgeClaim


#: Surface order of the three claim roles. Storage is ROLE-keyed
#: (``subject_canonical`` / ``predicate_verb`` / ``object_phrase``) and encodes
#: no word order, so supporting a VSO language (Arabic) or an SOV one is a
#: RENDERING change — this tuple — and NOT a data migration (#4172).
STATEMENT_ROLE_ORDER: tuple[str, str, str] = ("subject", "verb", "object")


def order_statement_parts(
    subject: str | None, verb: str | None, obj: str | None
) -> list[str]:
    """The three roles in surface order, dropping the ones that are absent.

    Every renderer must go through here. The order was previously hardcoded as
    an f-string in four places, so a future VSO/SOV renderer would have had to
    find all four — and one of them is JavaScript in a Jinja template, where a
    missed site fails silently rather than loudly (#4172).
    """
    by_role = {"subject": subject, "verb": verb, "object": obj}
    return [value for role in STATEMENT_ROLE_ORDER if (value := by_role[role])]


def render_statement(
    subject: str | None,
    verb: str | None,
    obj: str | None,
    *,
    separator: str = " ",
) -> str:
    """Join the present roles in surface order."""
    return separator.join(order_statement_parts(subject, verb, obj))


def enum_value(x: Any) -> str:
    """Return ``x.value`` when ``x`` is an enum, else ``str(x)``.

    KG models pass through serialization layers that sometimes leave
    enums as enums and sometimes coerce them to strings already.
    Callers want a string either way.
    """
    return x.value if hasattr(x, "value") else str(x)


def slug_verb(verb: str) -> str:
    """Canonical predicate slug for an SVO verb.

    Preserves multi-word predicates (including prepositions) by converting
    spaces and non-alphanumeric characters to dashes.

    Rules (must match what ``triples._predicate_uri`` produces after
    the namespace strip — the RDF predicate URI and the triangulation
    aggregation key are the same string):

    - Empty / whitespace verb → ``"assertedAbout"`` (the generic fallback).
    - Lowercase + alphanumerics-only; non-alnum chars become ``-``.
    - Collapse runs of dashes; trim leading/trailing dashes.
    - Leading-digit slugs get a ``v-`` prefix so they're valid URI
      fragments.
    - Multi-word verbs with prepositions are fully preserved:
      - ``"entered into"`` → ``"entered-into"``
      - ``"funded trips to"`` → ``"funded-trips-to"``
      - ``"is located in"`` → ``"is-located-in"``
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


_GENERIC_COPULA_OBJECTS = frozenset({
    "citation",
    "citations",
    "concept",
    "concepts",
    "document",
    "documents",
    "event",
    "events",
    "group",
    "groups",
    "idea",
    "ideas",
    "location",
    "locations",
    "organization",
    "organizations",
    "organisation",
    "organisations",
    "other",
    "others",
    "people",
    "person",
    "persons",
    "place",
    "places",
    "region",
    "regions",
    "thing",
    "things",
    "topic",
    "topics",
})

_COPULA_VERBS = frozenset({"is", "are", "was", "were", "be"})


def _norm_rule_text(value: str | None) -> str:
    return " ".join(str(value or "").split()).strip().casefold()


def is_bare_is_a_copula(
    predicate_verb: str | None,
    object_phrase: str | None,
    *,
    predicate_canonical: str | None = None,
) -> bool:
    """Return True for conservative, trivially-generic type copulas.

    This intentionally catches only low-information category assertions like
    "Andagoya is a place" or "Pedro was a person". False positives are worse
    than false negatives, so the heuristic stays narrow:

    - the predicate must clearly be a copula / ``is_a`` relation
    - the object must reduce to one generic type noun after stripping
      articles and "kind/type/sort of" wrappers
    """
    canonical = _norm_rule_text(predicate_canonical)
    predicate = _norm_rule_text(predicate_verb)
    if canonical != "is_a" and predicate not in _COPULA_VERBS:
        return False

    cleaned = re.sub(
        r"^[\s\[\]\(\)\"'`]+|[\s\[\]\(\)\"'`.,;:!?]+$",
        "",
        object_phrase or "",
    )
    tokens = [token for token in _norm_rule_text(cleaned).split() if token]
    if not tokens:
        return False
    while tokens and tokens[0] in {"a", "an", "the"}:
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[0] in {"kind", "sort", "type"} and tokens[1] == "of":
        tokens = tokens[2:]
    return len(tokens) == 1 and tokens[0] in _GENERIC_COPULA_OBJECTS


def is_trivial_claim(claim: "KnowledgeClaim") -> bool:
    """Conservative detector for low-information, trivially-true claims."""
    metadata = claim.metadata or {}
    subject = (
        getattr(claim, "subject_canonical", None)
        or getattr(claim, "svo_subject", None)
        or metadata.get("subject")
    )
    predicate = (
        getattr(claim, "predicate_verb", None)
        or getattr(claim, "svo_verb", None)
        or metadata.get("verb")
    )
    object_phrase = (
        getattr(claim, "object_phrase", None)
        or getattr(claim, "svo_object", None)
        or metadata.get("object")
    )
    if not _norm_rule_text(subject):
        return False
    return is_bare_is_a_copula(
        predicate,
        object_phrase,
        predicate_canonical=getattr(claim, "predicate_canonical", None),
    )


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


# =============================================================================
# #1124 — Hermeneutic predicate vocabulary (interpretive moves, not facts)
# =============================================================================
# Free-text variants → canonical slug for interpretive predicates. These
# describe moves an interpretation makes (e.g. "centers women's labor",
# "exposes silenced voices") not facts about the world. Used by the
# ``Interpretation`` model to populate ``predicate_canonical`` at write time.
#
# Categories: Application, Framework, Inter-interpretation, Recognition,
# Categorization, Naming, Revelation, Power, Comparison, Critique.

HERMENEUTIC_PREDICATES: dict[str, str] = {
    # --- application ---
    "applies to": "applies_to",
    "applies_to": "applies_to",
    "interprets": "interprets",
    "interprets as": "interprets",
    "glosses": "glosses",
    "reads as": "reads_as",
    "reads_as": "reads_as",
    # --- framework ---
    "uses framework": "uses_framework",
    "uses_framework": "uses_framework",
    "extends framework": "extends_framework",
    "extends_framework": "extends_framework",
    "combines frameworks": "combines_frameworks",
    "combines_frameworks": "combines_frameworks",
    # --- inter-interpretation ---
    "contests reading": "contests_reading",
    "contests_reading": "contests_reading",
    "extends reading": "extends_reading",
    "extends_reading": "extends_reading",
    "complicates reading": "complicates_reading",
    "complicates_reading": "complicates_reading",
    "subsumes reading": "subsumes_reading",
    "subsumes_reading": "subsumes_reading",
    # --- recognition ---
    "centers": "centers",
    "decenters": "decenters",
    "recovers": "recovers",
    "silences": "silences",
    "foregrounds": "foregrounds",
    "backgrounds": "backgrounds",
    # --- categorization ---
    "gendered as": "gendered_as",
    "gendered_as": "gendered_as",
    "racialized as": "racialized_as",
    "racialized_as": "racialized_as",
    "classed as": "classed_as",
    "classed_as": "classed_as",
    "colonized as": "colonized_as",
    "colonized_as": "colonized_as",
    "secularized as": "secularized_as",
    "secularized_as": "secularized_as",
    # --- naming ---
    "frames as": "frames_as",
    "frames_as": "frames_as",
    "reframes as": "reframes_as",
    "reframes_as": "reframes_as",
    "re-frames as": "reframes_as",
    "relabels as": "relabels_as",
    "relabels_as": "relabels_as",
    # --- revelation ---
    "exposes": "exposes",
    "obscures": "obscures",
    "reveals": "reveals",
    "conceals": "conceals",
    # --- power ---
    "legitimates": "legitimates",
    "delegitimates": "delegitimates",
    "naturalizes": "naturalizes",
    "denaturalizes": "denaturalizes",
    # --- comparison ---
    "analogous to": "analogous_to",
    "analogous_to": "analogous_to",
    "contrasts with": "contrasts_with",
    "contrasts_with": "contrasts_with",
    "parallels": "parallels",
    "inverts": "inverts",
    # --- critique ---
    "critiques": "critiques",
    "defends": "defends",
    "complicates": "complicates",
    "troubles": "troubles",
}


def canonical_hermeneutic_predicate(predicate: str | None) -> str | None:
    """Map a free-text interpretive predicate to a canonical slug.

    Lookup is case-insensitive on the stripped predicate. Returns ``None``
    for empty input and for predicates not in the controlled vocabulary.
    Used by ``Interpretation.save()`` to populate ``predicate_canonical``
    at write time (#1124).
    """
    if not predicate:
        return None
    return HERMENEUTIC_PREDICATES.get(predicate.lower().strip())


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


__all__ = [name for name in globals() if not name.startswith("__")]
