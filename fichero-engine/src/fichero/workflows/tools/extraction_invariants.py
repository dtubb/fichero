"""Boundary invariant checks for the extractor → KG write path (#1017).

The extractor pipeline can silently drop or degrade what the LLM
produced: an item with no canonical name is ``continue``-d past inside
``_write_kg_rows``, a claim can land with a verb but no object, an
entity description can echo its own name. Before #1017 those failures
were invisible — a page just came back "empty" with no signal whether
the model genuinely found nothing or the writer threw the items away.

This module is the explicit-not-silent layer. The functions are pure:
they take already-extracted field values and return human-readable
violation strings. ``_write_kg_rows`` calls them per item and logs the
aggregate at WARNING so silent drops surface in the activity log. No
DB, no I/O — trivially unit-testable.

The checks here are *observational*, not *enforcing*: they never raise
and never mutate. A violation means "this item lost information on the
way into the KG", which is a diagnostic signal, not a hard error.
"""

from __future__ import annotations

from typing import Any

# Sections whose canonical value is a date string, not an entity name.
# Mirrors the ``entity_type is None`` branch in ``_write_kg_rows``.
_DATE_CANONICAL_KEYS = ("date_normalized", "date", "fecha_normalizada", "fecha")
_NAME_CANONICAL_KEYS = ("name", "event", "date", "nombre", "evento", "fecha")


def item_canonical(item: dict[str, Any], *, is_date_section: bool) -> str:
    """Resolve the canonical anchor for an extractor item.

    Matches the precedence ``_write_kg_rows`` uses so the invariant
    check sees exactly the value the writer will key on.
    """
    if is_date_section:
        for key in _DATE_CANONICAL_KEYS:
            if (val := item.get(key)):
                return str(val).strip()
        return ""
    for key in _NAME_CANONICAL_KEYS:
        if (val := item.get(key)):
            return str(val).strip()
    return ""


def claim_item_violations(
    item: dict[str, Any], *, is_date_section: bool
) -> list[str]:
    """Return violation strings for one raw extractor item.

    An empty list means the item rounds-trips into the KG without
    losing information. Each string names a concrete way the item is
    degenerate so the activity log can show *why* a page looks thin.
    """
    violations: list[str] = []

    canonical = item_canonical(item, is_date_section=is_date_section)
    if not canonical:
        # The #1006 / #1003 silent-drop signature: entity sections
        # ``continue`` past anchorless items, so they vanish with no
        # trace beyond the items_in count.
        violations.append("no canonical name — item will be dropped")

    verb = str(item.get("verb") or "").strip()
    obj = str(item.get("object") or "").strip()
    legacy_context = str(
        item.get("context") or item.get("contexto") or ""
    ).strip()
    # A claim with neither an SVO predicate nor a legacy context nor a
    # canonical anchor carries no assertion at all — it composes down to
    # a bare fragment or nothing. Verb-only / object-only is allowed
    # (the writer composes a partial sentence); fully empty is not.
    if not verb and not obj and not legacy_context and not canonical:
        violations.append("empty claim — no subject, predicate, or context")

    return violations


def entity_description_violation(
    description: str | None, canonical_name: str
) -> str | None:
    """Return a violation string when an entity description is degenerate.

    Mirrors the reject rules in ``_sanitize_entity_description`` so the
    invariant log can report *that* a description was thrown away —
    ``_sanitize_entity_description`` silently returns ``None`` and the
    inspector just shows a blank blurb. ``None`` here means the
    description is fine (or legitimately absent).
    """
    if not description:
        return None
    cleaned = description.strip()
    if not cleaned:
        return None
    if len(cleaned.split()) < 3:
        return "entity description under 3 words — dropped as degenerate"
    canonical_folded = (canonical_name or "").casefold().strip()
    if canonical_folded and cleaned.casefold() in canonical_folded:
        return "entity description echoes the canonical name — dropped"
    return None


def summarize_violations(violations: list[str]) -> str:
    """Collapse a per-item violation list into one log-friendly line.

    Counts each distinct violation reason so a 40-item page that lost
    six anchorless entities reads as ``6× no canonical name`` rather
    than six identical log lines.
    """
    if not violations:
        return ""
    counts: dict[str, int] = {}
    for v in violations:
        counts[v] = counts.get(v, 0) + 1
    return "; ".join(
        f"{count}× {reason}" for reason, count in sorted(counts.items())
    )
