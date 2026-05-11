"""Tests for SVO claim-text composition in extractors.

Locks the contract that:
- Pydantic section models accept `verb` + `object` as separate fields
- The KG writer composes claim.text deterministically as a real
  sentence: "{name} {verb} {object}." for entity sections,
  "{date}: {verb} {object}." for date sections
- The SVO triple lands in KnowledgeClaim.metadata so downstream
  queries can reason structurally
- Legacy `context` is still accepted for graceful in-flight cache hits
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from fichero.workflows.tools.extractors import (
    _SectionDate,
    _SectionEvent,
    _SectionPerson,
    _SectionPlace,
    _SECTIONS,
    _write_kg_rows,
)


# =============================================================================
# Pydantic models accept verb+object
# =============================================================================


def test_person_model_accepts_svo() -> None:
    person = _SectionPerson(
        name="Eugenio Córdoba",
        alternative_spellings=["E. Córdoba"],
        verb="served as",
        object="the alcalde of Popayán",
    )
    assert person.name == "Eugenio Córdoba"
    assert person.verb == "served as"
    assert person.object == "the alcalde of Popayán"


def test_place_model_accepts_svo() -> None:
    place = _SectionPlace(
        name="Chocó",
        verb="is",
        object="a gold-mining region in western Colombia",
    )
    assert place.verb == "is"
    assert place.object == "a gold-mining region in western Colombia"


def test_date_model_accepts_svo() -> None:
    date = _SectionDate(
        date="23 de julio de 1933",
        date_normalized="1933-07-23",
        verb="records",
        object="the filing of the original mining petition",
    )
    assert date.verb == "records"
    assert date.object == "the filing of the original mining petition"


def test_event_model_accepts_svo() -> None:
    event = _SectionEvent(
        event="Filing of the Petition",
        date="1933-07-23",
        verb="was",
        object="submitted to the Constitutional Court by the heirs",
    )
    assert event.verb == "was"
    assert event.object == "submitted to the Constitutional Court by the heirs"


# =============================================================================
# _write_kg_rows composes SVO claim text correctly
# =============================================================================


def _people_section() -> dict:
    return next(s for s in _SECTIONS if s["name"] == "people_extract")


def _dates_section() -> dict:
    return next(s for s in _SECTIONS if s["name"] == "dates_extract")


def _capture_save_claim() -> tuple[MagicMock, list[dict]]:
    """Patch save_claim + upsert_entity to capture invocations."""
    captured: list[dict] = []
    db = MagicMock()

    def fake_save(db_arg, **kwargs):
        captured.append(kwargs)
        return None

    def fake_upsert(db_arg, **kwargs):
        return f"entity:{kwargs['canonical_name']}"

    import fichero.workflows.tools._entity_writer as ew
    ew.save_claim = fake_save  # type: ignore[assignment]
    ew.upsert_entity = fake_upsert  # type: ignore[assignment]
    return db, captured


def test_person_svo_composes_as_real_sentence() -> None:
    db, captured = _capture_save_claim()
    _write_kg_rows(
        db,
        _people_section(),
        items=[{
            "name": "Eugenio Córdoba",
            "alternative_spellings": [],
            "verb": "served as",
            "object": "the alcalde of Popayán",
        }],
        container_id="doc-1",
    )
    assert len(captured) == 1
    claim = captured[0]
    assert claim["text"] == "Eugenio Córdoba served as the alcalde of Popayán."
    # SVO triple lands in metadata
    meta = claim["metadata"]
    assert meta["subject"] == "Eugenio Córdoba"
    assert meta["verb"] == "served as"
    assert meta["object"] == "the alcalde of Popayán"


def test_date_svo_composes_with_normalized_subject() -> None:
    db, captured = _capture_save_claim()
    _write_kg_rows(
        db,
        _dates_section(),
        items=[{
            "date": "23 de julio de 1933",
            "date_normalized": "1933-07-23",
            "verb": "records",
            "object": "the filing of the original mining petition",
        }],
        container_id="doc-1",
    )
    assert len(captured) == 1
    claim = captured[0]
    # Date section uses the normalized date as the subject.
    assert claim["text"] == "1933-07-23: records the filing of the original mining petition."
    meta = claim["metadata"]
    assert meta["date_text"] == "23 de julio de 1933"
    assert meta["date_normalized"] == "1933-07-23"
    assert meta["verb"] == "records"
    assert meta["object"] == "the filing of the original mining petition"


def test_legacy_context_still_writes_claim_with_colon_shape() -> None:
    """If an in-flight cache or human-authored item still has the old
    `context` field (no verb/object), the writer falls back to the
    pre-SVO shape so we don't lose data during the transition."""
    db, captured = _capture_save_claim()
    _write_kg_rows(
        db,
        _people_section(),
        items=[{
            "name": "Eugenio Córdoba",
            "context": "is described as the alcalde of Popayán.",
        }],
        container_id="doc-1",
    )
    assert len(captured) == 1
    claim = captured[0]
    assert claim["text"] == (
        "Eugenio Córdoba: is described as the alcalde of Popayán."
    )
    meta = claim["metadata"]
    # Legacy items have no structured verb/object — metadata only
    # carries the subject.
    assert meta["subject"] == "Eugenio Córdoba"
    assert "verb" not in meta
    assert "object" not in meta


def test_empty_predicate_falls_back_to_bare_name() -> None:
    db, captured = _capture_save_claim()
    _write_kg_rows(
        db,
        _people_section(),
        items=[{"name": "Eugenio Córdoba", "verb": "", "object": ""}],
        container_id="doc-1",
    )
    claim = captured[0]
    # No predicate → just the name (no trailing punctuation).
    assert claim["text"] == "Eugenio Córdoba"


def test_verb_only_or_object_only_still_composes() -> None:
    """If the LLM emits only one of verb/object (e.g. a one-word
    predicate), still produce a sentence — the join handles either."""
    db, captured = _capture_save_claim()
    _write_kg_rows(
        db,
        _people_section(),
        items=[{"name": "Juan Pérez", "verb": "signed", "object": ""}],
        container_id="doc-1",
    )
    assert captured[0]["text"] == "Juan Pérez signed."


@pytest.mark.parametrize(
    "section_name,artifact",
    [(s["name"], s["artifact"]) for s in _SECTIONS if s["name"] != "keywords_extract"],
)
def test_every_section_prompt_mentions_svo(section_name: str, artifact: str) -> None:
    """Every entity-bearing section's instruction must point the LLM at
    the verb/object split."""
    section = next(s for s in _SECTIONS if s["name"] == section_name)
    instruction = section["instruction"]
    # Every section's instruction should reference verb + object —
    # locks the contract so future edits don't accidentally regress
    # one section's prompt.
    assert "verb" in instruction.lower()
    assert "object" in instruction.lower()
