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
