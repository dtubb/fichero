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
"""

from __future__ import annotations

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
