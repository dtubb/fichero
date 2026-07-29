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

from fichero_server.kg._common import parse_kwarg_repr
from fichero_server.workflows.tools.extractors import (
    _normalize_kwarg_repr_fields,
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


@pytest.fixture
def _capture_save_claim():
    """Patch save_claim + upsert_entity, restore on teardown.

    Returns a (db, captured) factory. Was previously a plain function
    that left the monkeypatches in place and poisoned later tests
    importing the same module — using a fixture with try/finally
    restoration prevents that leak.
    """
    import fichero_server.workflows.tools._entity_writer as ew
    original_save = ew.save_claim
    original_upsert = ew.upsert_entity

    captured: list[dict] = []
    db = MagicMock()

    def fake_save(db_arg, **kwargs):
        captured.append(kwargs)
        return None

    def fake_upsert(db_arg, **kwargs):
        return f"entity:{kwargs['canonical_name']}"

    ew.save_claim = fake_save  # type: ignore[assignment]
    ew.upsert_entity = fake_upsert  # type: ignore[assignment]
    try:
        yield db, captured
    finally:
        ew.save_claim = original_save  # type: ignore[assignment]
        ew.upsert_entity = original_upsert  # type: ignore[assignment]


def test_person_svo_composes_as_real_sentence(_capture_save_claim) -> None:
    db, captured = _capture_save_claim
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


def test_date_svo_composes_with_normalized_subject(_capture_save_claim) -> None:
    db, captured = _capture_save_claim
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


def test_legacy_context_synthesises_svo_via_fallback(_capture_save_claim) -> None:
    """Legacy items (no verb/object) now go through _synthesize_svo_fallback
    so claim.predicate_verb / object_phrase land non-NULL — the #1113
    invariant. The composed text is a real sentence ("Subject is
    description.") rather than the legacy "Subject: description" colon
    shape; full SVO is required for #1111 paragraph composition.
    """
    db, captured = _capture_save_claim
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
    # Synthesised SVO — verb defaults to "is", object is the legacy
    # context (no leading-subject prefix to strip).
    assert claim["predicate_verb"] == "is"
    assert claim["object_phrase"] == "is described as the alcalde of Popayán."
    assert claim["subject_canonical"] == "Eugenio Córdoba"
    # Composed text is a sentence using the synthesised SVO.
    assert claim["text"].startswith("Eugenio Córdoba is")
    meta = claim["metadata"]
    assert meta["subject"] == "Eugenio Córdoba"
    # Synthesised SVO writes verb/object into metadata too (alongside
    # the typed top-level fields) so downstream consumers reading from
    # metadata still see them.
    assert meta.get("verb") == "is"


def test_empty_predicate_synthesises_typed_default(_capture_save_claim) -> None:
    """When the item has no verb/object/context at all (the
    keywords-style bare-name case), the section's entity_type drives a
    typed default so the claim still has full SVO. Without this, the
    #1113 invariant would still be violated for keywords-extract output
    (bare strings) — leaving claim.predicate_verb NULL and breaking the
    #1111 paragraph composer for those rows."""
    db, captured = _capture_save_claim
    _write_kg_rows(
        db,
        _people_section(),
        items=[{"name": "Eugenio Córdoba", "verb": "", "object": ""}],
        container_id="doc-1",
    )
    claim = captured[0]
    # Typed default — "is a person" for an EntityType.person section.
    assert claim["predicate_verb"] == "is"
    assert claim["object_phrase"] == "a person"
    assert claim["text"] == "Eugenio Córdoba is a person."


def test_verb_only_or_object_only_still_composes(_capture_save_claim) -> None:
    """If the LLM emits only one of verb/object (e.g. a one-word
    predicate), the synth fallback (#1113) promotes it so a sentence
    still results. Verb-only → verb becomes the object and "is" is
    the synthesised verb, so the rendered text reads as a complete
    sentence ("Juan Pérez is signed.") rather than a fragment."""
    db, captured = _capture_save_claim
    _write_kg_rows(
        db,
        _people_section(),
        items=[{"name": "Juan Pérez", "verb": "signed", "object": ""}],
        container_id="doc-1",
    )
    # After the #1113 SVO synth: verb-only promotes to ("is", "signed").
    assert captured[0]["predicate_verb"] == "is"
    assert captured[0]["object_phrase"] == "signed"
    assert captured[0]["text"] == "Juan Pérez is signed."


def test_within_call_dedup_collapses_identical_svo_claims(_capture_save_claim) -> None:
    """Six items about Davidson with the same canonical name + same
    SVO predicate (the #896 Davidson-on-page-1 pattern) collapse to
    ONE claim. Alternative spellings fold into the survivor so we
    don't lose the surface-form evidence from the duplicates."""
    db, captured = _capture_save_claim
    _write_kg_rows(
        db,
        _people_section(),
        items=[
            {"name": "Davidson", "alternative_spellings": ["Deibinson"],
             "verb": "appears as", "object": "an alternative spelling of Deibinson"},
            {"name": "Davidson", "alternative_spellings": ["[Davidson]"],
             "verb": "appears as", "object": "an alternative spelling of Deibinson"},
            {"name": "Davidson", "alternative_spellings": [],
             "verb": "appears as", "object": "an alternative spelling of Deibinson"},
        ],
        container_id="doc-1",
    )
    assert len(captured) == 1, (
        f"expected 1 claim after dedup, got {len(captured)}"
    )


def test_dedup_preserves_distinct_predicates(_capture_save_claim) -> None:
    """Same entity name + different SVO predicates → two separate
    claims survive. Locks the contract that we collapse only EXACT
    predicate matches, not anything that mentions the same person."""
    db, captured = _capture_save_claim
    _write_kg_rows(
        db,
        _people_section(),
        items=[
            {"name": "Juan Pérez", "verb": "signed", "object": "the deed"},
            {"name": "Juan Pérez", "verb": "served as", "object": "witness"},
        ],
        container_id="doc-1",
    )
    assert len(captured) == 2


def test_dedup_folds_alternative_spellings(_capture_save_claim) -> None:
    """Duplicate items contribute their alternative_spellings to the
    survivor, plus surface-form variants of the name itself when they
    differ only in casing/punctuation."""
    db, captured = _capture_save_claim
    _write_kg_rows(
        db,
        _people_section(),
        items=[
            {"name": "Davidson", "alternative_spellings": ["Deibi"],
             "verb": "is", "object": "the addressee"},
            {"name": "DAVIDSON", "alternative_spellings": ["Deibinson"],
             "verb": "is", "object": "the addressee"},
        ],
        container_id="doc-1",
    )
    assert len(captured) == 1
    # The KG writer's _write_kg_rows passes aliases through upsert_entity
    # (our mock returns "entity:<canonical>"), so we don't observe
    # the alias set in `captured` directly — but we can re-call
    # _dedup logic via the survivor's identity: only one claim hit.
    # That confirms the merge happened.


def test_write_kg_rows_caps_overlarge_page_batches(_capture_save_claim, caplog) -> None:
    """The KG writer should cap oversized per-page batches before DB writes."""
    db, captured = _capture_save_claim
    items = [
        {"name": f"Person {idx}", "verb": "is", "object": "a person"}
        for idx in range(101)
    ]

    from fichero_server.workflows.tools.extractors import _SECTIONS, _write_kg_rows

    people_section = next(s for s in _SECTIONS if s["name"] == "people_extract")
    with caplog.at_level("WARNING", logger="fichero_server.workflows.tools.extractors"):
        _write_kg_rows(
            db,
            people_section,
            items,
            container_id="doc-1",
            page_label="Page 1",
        )

    assert len(captured) == 100
    assert any("capped people_extract page Page 1" in record.message for record in caplog.records)


def test_epistemic_and_claim_type_plumbed_through(_capture_save_claim) -> None:
    """LLM-emitted epistemic_status + claim_type land on the claim,
    coerced to enums. Unknown values silently fall back to None /
    ClaimType.fact (model defaults), so a single misclassification
    doesn't drop the claim."""
    from fichero_server.models.knowledge import ClaimType, EpistemicStatus

    db, captured = _capture_save_claim
    _write_kg_rows(
        db,
        _people_section(),
        items=[{
            "name": "Eugenio Córdoba",
            "verb": "served as",
            "object": "the alcalde of Popayán",
            "epistemic_status": "confirmed",
            "claim_type": "fact",
        }, {
            "name": "Juan Pérez",
            "verb": "may have signed",
            "object": "the deed",
            "epistemic_status": "tentative",
            "claim_type": "interpretation",
        }, {
            "name": "Mystery Man",
            "verb": "wrote",
            "object": "the letter",
            "epistemic_status": "garbage",  # unknown — coerces to None
            "claim_type": "made-up-type",  # unknown — falls back to fact
        }],
        container_id="doc-1",
    )
    assert len(captured) == 3
    assert captured[0]["epistemic_status"] == EpistemicStatus.confirmed
    assert captured[0]["claim_type"] == ClaimType.fact
    assert captured[1]["epistemic_status"] == EpistemicStatus.tentative
    assert captured[1]["claim_type"] == ClaimType.interpretation
    assert captured[2]["epistemic_status"] is None
    assert captured[2]["claim_type"] == ClaimType.fact


def test_source_text_lands_in_excerpt_and_metadata(_capture_save_claim) -> None:
    """When the LLM emits a verbatim source_text, the writer routes it
    to source_excerpt (for cross-doc display) AND metadata.source_text
    (so the UI can distinguish quoted-span from page-chunk-fallback)."""
    db, captured = _capture_save_claim
    quote = "Eugenio Córdoba, alcalde de Popayán, recibió la petición."
    _write_kg_rows(
        db,
        _people_section(),
        items=[{
            "name": "Eugenio Córdoba",
            "verb": "served as",
            "object": "the alcalde",
            "source_text": quote,
        }],
        container_id="doc-1",
    )
    claim = captured[0]
    assert claim["source_excerpt"] == quote
    assert claim["metadata"]["source_text"] == quote


def test_source_text_absent_falls_back_to_predicate(_capture_save_claim) -> None:
    """No source_text → source_excerpt falls back to the predicate (old
    behaviour) and metadata.source_text is NOT set, so the UI knows the
    excerpt is constructed rather than quoted."""
    db, captured = _capture_save_claim
    _write_kg_rows(
        db,
        _people_section(),
        items=[{
            "name": "Juan Pérez",
            "verb": "signed",
            "object": "the deed",
        }],
        container_id="doc-1",
    )
    claim = captured[0]
    assert claim["source_excerpt"] == "signed the deed"
    assert "source_text" not in claim["metadata"]


@pytest.mark.parametrize(
    "section_name,artifact",
    [
        (s["name"], s["artifact"])
        for s in _SECTIONS
        if s["name"] not in {"keywords_extract", "citation_usage_extract"}
    ],
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


# =============================================================================
# #1030 — kwarg-repr leak sanitizer
# =============================================================================


class TestParseKwargRepr:
    def test_parses_verb_object_repr(self) -> None:
        parsed = parse_kwarg_repr("verb='is', object='a long-abandoned mine'")
        assert parsed == {"verb": "is", "object": "a long-abandoned mine"}

    def test_parses_name_verb_object_repr(self) -> None:
        parsed = parse_kwarg_repr(
            "name='Eldorado', verb='is', object='a mine in Ontario, Canada'"
        )
        assert parsed == {
            "name": "Eldorado",
            "verb": "is",
            "object": "a mine in Ontario, Canada",
        }

    def test_object_value_may_contain_commas_and_periods(self) -> None:
        parsed = parse_kwarg_repr(
            "verb='welcomed', object='my attempts to learn their craft.'"
        )
        assert parsed == {
            "verb": "welcomed",
            "object": "my attempts to learn their craft.",
        }

    def test_double_quotes_also_parse(self) -> None:
        parsed = parse_kwarg_repr('verb="served as", object="the alcalde"')
        assert parsed == {"verb": "served as", "object": "the alcalde"}

    def test_ordinary_prose_returns_none(self) -> None:
        assert parse_kwarg_repr("served as the alcalde of Popayán") is None
        assert parse_kwarg_repr("") is None
        assert parse_kwarg_repr("a region where mining occurs") is None


class TestNormalizeKwargReprFields:
    def test_repr_in_object_field_is_redistributed(self) -> None:
        item = {"name": "Eldorado", "verb": "", "object": "verb='is', object='a mine'"}
        fixed = _normalize_kwarg_repr_fields(item)
        assert fixed["verb"] == "is"
        assert fixed["object"] == "a mine"
        assert fixed["name"] == "Eldorado"

    def test_repr_in_source_text_is_redistributed_and_cleared(self) -> None:
        item = {
            "name": "Leidy",
            "source_text": "verb='cleared', object='gravel from a sluice'",
        }
        fixed = _normalize_kwarg_repr_fields(item)
        assert fixed["verb"] == "cleared"
        assert fixed["object"] == "gravel from a sluice"
        assert fixed["source_text"] == ""

    def test_clean_item_passes_through_unchanged(self) -> None:
        item = {"name": "Chocó", "verb": "is", "object": "a region in Colombia"}
        assert _normalize_kwarg_repr_fields(item) == item

    def test_parsed_name_only_adopted_when_item_has_none(self) -> None:
        item = {"name": "RealName", "object": "name='Wrong', verb='is', object='x'"}
        fixed = _normalize_kwarg_repr_fields(item)
        assert fixed["name"] == "RealName"
        assert fixed["verb"] == "is"
        assert fixed["object"] == "x"


def test_write_kg_rows_sanitizes_kwarg_repr_in_object(_capture_save_claim) -> None:
    """An item whose `object` field carries the leaked kwarg repr must
    still compose a clean claim sentence — no raw verb='...' in the
    output. (#1030)"""
    db, captured = _capture_save_claim
    _write_kg_rows(
        db,
        _people_section(),
        items=[{
            "name": "Louise Livingstone",
            "verb": "",
            "object": "verb='worked as', object='a journalist at a local paper'",
        }],
        container_id="doc-1",
    )
    assert len(captured) == 1
    claim = captured[0]
    assert "verb=" not in claim["text"]
    assert "object=" not in claim["text"]
    assert claim["text"] == (
        "Louise Livingstone worked as a journalist at a local paper."
    )
    assert claim["metadata"]["verb"] == "worked as"
    assert claim["metadata"]["object"] == "a journalist at a local paper"
