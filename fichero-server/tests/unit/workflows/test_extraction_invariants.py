"""Tests for the extractor → KG boundary invariant checks (#1017 layer 2).

Locks the contract that:
- anchorless extractor items are flagged (the #1006 / #1003 silent-drop
  signature), not silently ``continue``-d past
- degenerate entity descriptions are reported, not just quietly nulled
- verb-only / object-only items are NOT flagged — the writer composes a
  partial sentence for those and that is intentional
- ``summarize_violations`` collapses repeated reasons into counts
"""

from __future__ import annotations

from fichero_server.workflows.tools.extraction_invariants import (
    claim_item_violations,
    entity_description_violation,
    item_canonical,
    summarize_violations,
)


# =============================================================================
# item_canonical
# =============================================================================


def test_item_canonical_entity_section_prefers_name() -> None:
    assert item_canonical({"name": "Eugenio Córdoba"}, is_date_section=False) == (
        "Eugenio Córdoba"
    )


def test_item_canonical_entity_section_falls_back_to_event() -> None:
    assert item_canonical({"event": "Filing of the Petition"}, is_date_section=False) == (
        "Filing of the Petition"
    )


def test_item_canonical_date_section_prefers_normalized() -> None:
    item = {"date": "23 de julio de 1933", "date_normalized": "1933-07-23"}
    assert item_canonical(item, is_date_section=True) == "1933-07-23"


def test_item_canonical_date_section_falls_back_to_raw_date() -> None:
    assert item_canonical({"date": "sometime in 1933"}, is_date_section=True) == (
        "sometime in 1933"
    )


def test_item_canonical_empty_when_no_anchor() -> None:
    assert item_canonical({"verb": "signed"}, is_date_section=False) == ""


# =============================================================================
# claim_item_violations
# =============================================================================


def test_well_formed_entity_item_has_no_violations() -> None:
    item = {"name": "Juan Pérez", "verb": "signed", "object": "the deed"}
    assert claim_item_violations(item, is_date_section=False) == []


def test_anchorless_entity_item_is_flagged() -> None:
    """The #1006 silent-drop signature: an item with no name is
    ``continue``-d past in _write_kg_rows and vanishes."""
    item = {"verb": "signed", "object": "the deed"}
    violations = claim_item_violations(item, is_date_section=False)
    assert any("no canonical name" in v for v in violations)


def test_verb_only_item_is_not_flagged() -> None:
    """The writer composes 'Juan Pérez signed.' for verb-only items —
    that is intentional, not a violation."""
    item = {"name": "Juan Pérez", "verb": "signed", "object": ""}
    assert claim_item_violations(item, is_date_section=False) == []


def test_completely_empty_item_is_flagged_twice() -> None:
    item: dict = {}
    violations = claim_item_violations(item, is_date_section=False)
    assert any("no canonical name" in v for v in violations)
    assert any("empty claim" in v for v in violations)


def test_date_item_with_normalized_date_has_no_violations() -> None:
    item = {"date": "1933", "date_normalized": "1933", "verb": "records", "object": "x"}
    assert claim_item_violations(item, is_date_section=True) == []


def test_legacy_context_item_is_not_flagged() -> None:
    """Pre-SVO items carry a `context` field instead of verb/object —
    the writer still composes a claim, so it is not a violation."""
    item = {"name": "Juan Pérez", "context": "was the alcalde"}
    assert claim_item_violations(item, is_date_section=False) == []


# =============================================================================
# entity_description_violation
# =============================================================================


def test_good_description_has_no_violation() -> None:
    assert entity_description_violation(
        "served as the alcalde of Popayán", "Eugenio Córdoba"
    ) is None


def test_none_description_has_no_violation() -> None:
    assert entity_description_violation(None, "Eugenio Córdoba") is None


def test_short_description_is_flagged() -> None:
    assert entity_description_violation("called", "Eugenio Córdoba") is not None


def test_description_echoing_canonical_name_is_flagged() -> None:
    # 3+ words so it clears the length gate, but still a substring of
    # the canonical name — i.e. the description just echoes the name.
    violation = entity_description_violation(
        "Eugenio Córdoba de", "Eugenio Córdoba de Popayán"
    )
    assert violation is not None
    assert "echoes" in violation


# =============================================================================
# summarize_violations
# =============================================================================


def test_summarize_empty_list_returns_empty_string() -> None:
    assert summarize_violations([]) == ""


def test_summarize_collapses_repeats_into_counts() -> None:
    violations = [
        "no canonical name — item will be dropped",
        "no canonical name — item will be dropped",
        "entity description under 3 words — dropped as degenerate",
    ]
    summary = summarize_violations(violations)
    assert "2× no canonical name — item will be dropped" in summary
    assert "1× entity description under 3 words — dropped as degenerate" in summary
