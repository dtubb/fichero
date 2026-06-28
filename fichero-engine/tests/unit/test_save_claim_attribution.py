"""Tests for save_claim's #1123 Phase D heuristic attribution detection.

`save_claim` now auto-derives speaker_name / quotation_kind / audience
from the claim text + source excerpt when callers don't pass explicit
values. These tests pin the detector behaviour: known patterns map
cleanly, ambiguous text returns None (honest absence), and explicit
caller-supplied values always win over the heuristic.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fichero.db import Database
from fichero.knowledge_models import KnowledgeClaim, QuotationKind
from fichero.models import Document, DocType
from fichero.workflows.tools._entity_writer import (
    _detect_audience,
    _detect_quotation_kind,
    _detect_speaker,
    _source_authority_weight,
    save_claim,
)


# =============================================================================
# Pure-function detectors
# =============================================================================


class TestDetectQuotationKind:
    def test_reporting_verb_with_quotes_is_verbatim(self):
        # Reporting verb + quote chars in excerpt → verbatim warrant.
        assert (
            _detect_quotation_kind("said", '"I saw the alcalde," he said.')
            == QuotationKind.verbatim
        )

    def test_reporting_verb_with_smart_quotes(self):
        # The detector matches smart quotes too — historical OCR output
        # often comes through with curly quotes.
        assert (
            _detect_quotation_kind(
                "declared",
                "He declared “the deed is void” to the cabildo.",
            )
            == QuotationKind.verbatim
        )

    def test_reporting_verb_without_quotes_is_indirect(self):
        assert (
            _detect_quotation_kind("testified", "He testified to the events.")
            == QuotationKind.indirect
        )

    def test_non_reporting_verb_returns_none(self):
        # "owned" isn't a reporting verb → quotation_kind not applicable.
        assert _detect_quotation_kind("owned", "Pedro owned the mine.") is None

    def test_empty_verb_returns_none(self):
        assert _detect_quotation_kind(None, "anything") is None
        assert _detect_quotation_kind("", "anything") is None

    def test_case_insensitive_verb(self):
        assert (
            _detect_quotation_kind("SAID", '"x"') == QuotationKind.verbatim
        )


class TestDetectSpeaker:
    def test_simple_x_said(self):
        assert (
            _detect_speaker(None, "Pedro said the deed was filed in 1933.")
            == "Pedro"
        )

    def test_titled_witness(self):
        # The witness Pedro testified that the petitioner Maria filed...
        # The detector picks up the "the witness Pedro" phrase.
        speaker = _detect_speaker(
            None, "The witness Pedro testified that the deed was filed."
        )
        assert speaker is not None
        assert "Pedro" in speaker

    def test_according_to_pattern(self):
        speaker = _detect_speaker(
            None, "According to Maria, the petition was filed in 1820."
        )
        assert speaker == "Maria"

    def test_in_the_words_of(self):
        speaker = _detect_speaker(
            None, "In the words of Don Antonio, the mine was abandoned."
        )
        assert speaker is not None
        assert "Antonio" in speaker

    def test_no_speaker_pattern_returns_none(self):
        # No "X said" pattern → no speaker. Don't fabricate one.
        assert _detect_speaker(None, "The deed was filed in 1933.") is None

    def test_falls_back_to_claim_text(self):
        # When excerpt is missing, fall back to the composed claim text.
        assert (
            _detect_speaker("Pedro stated the deed was void.", None)
            == "Pedro"
        )

    def test_both_none_returns_none(self):
        assert _detect_speaker(None, None) is None


class TestDetectAudience:
    def test_cabildo_pattern(self):
        aud = _detect_audience(
            None,
            "The petition was addressed to the Cabildo of Popayán in 1820.",
        )
        assert aud is not None
        assert "Cabildo of Popayán" in aud

    def test_audiencia_pattern(self):
        aud = _detect_audience(
            None,
            "The decree was directed to the Audiencia of Quito.",
        )
        assert aud is not None
        assert "Audiencia" in aud

    def test_to_the_court(self):
        aud = _detect_audience(
            None, "Submitted to the Court of Madrid for review."
        )
        assert aud is not None
        assert "Court" in aud

    def test_lowercase_audience_rejected(self):
        # "to the place" is a generic preposition phrase, not an
        # institutional audience. Must NOT match.
        assert (
            _detect_audience(None, "Pedro travelled to the place by mule.")
            is None
        )

    def test_no_pattern_returns_none(self):
        assert _detect_audience(None, "Pedro signed the deed.") is None

    def test_both_none_returns_none(self):
        assert _detect_audience(None, None) is None


# =============================================================================
# save_claim auto-derivation (integration with DuckDB round-trip)
# =============================================================================


def _setup_db(tmp: str):
    db = Database(Path(tmp) / "test.fichero")
    doc = Document(name="src", doc_type=DocType.file)
    db.save(doc)
    return db, doc


class TestSaveClaimAutoAttribution:
    """The full pipeline: a save_claim() call with no explicit
    attribution arguments should populate speaker_name / quotation_kind /
    audience / source_language / confidence_source automatically.
    """

    def test_full_auto_population(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, doc = _setup_db(tmp)
            claim_id = save_claim(
                db,
                text="Pedro said the petition was filed.",
                source_document_id=doc.id,
                source_excerpt=(
                    'Pedro said, "I filed the petition," addressed to '
                    "the Cabildo of Popayán."
                ),
                predicate_verb="said",
                language="es",
                confidence_origin="llm",
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded is not None
            # quotation_kind: reporting verb + quote chars → verbatim
            assert loaded.quotation_kind == QuotationKind.verbatim
            # speaker: "Pedro said" matched
            assert loaded.speaker_name == "Pedro"
            # audience: "to the Cabildo of Popayán" matched
            assert loaded.audience is not None
            assert "Cabildo" in loaded.audience
            # source_language: defaulted from `language`
            assert loaded.source_language == "es"
            # confidence_source: explicit override
            assert loaded.confidence_source == "llm"
            # predicate_canonical: "said" is a canonical verb
            assert loaded.predicate_canonical == "said"

    def test_explicit_speaker_overrides_heuristic(self):
        # When the caller passes an explicit speaker_name, the
        # heuristic is bypassed — even if the text could imply
        # a different speaker.
        with tempfile.TemporaryDirectory() as tmp:
            db, doc = _setup_db(tmp)
            claim_id = save_claim(
                db,
                text="Pedro said the deed was void.",
                source_document_id=doc.id,
                source_excerpt="Pedro said the deed was void.",
                predicate_verb="said",
                speaker_name="the witness Pedro González (explicit)",
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded.speaker_name == "the witness Pedro González (explicit)"

    def test_explicit_quotation_kind_overrides_heuristic(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, doc = _setup_db(tmp)
            claim_id = save_claim(
                db,
                text="Pedro said the deed was void.",
                source_document_id=doc.id,
                source_excerpt='Pedro said, "the deed was void."',
                predicate_verb="said",
                # Heuristic would set verbatim; explicit override picks
                # free_indirect because the human reviewer judged so.
                quotation_kind=QuotationKind.free_indirect,
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded.quotation_kind == QuotationKind.free_indirect

    def test_heuristic_confidence_origin(self):
        # When the extractor flagged SVO synthesis, confidence_origin
        # should be "heuristic" — surfaces in the inspector so users
        # can audit which claims came from the LLM directly vs which
        # were filled in by our local SVO fallback.
        with tempfile.TemporaryDirectory() as tmp:
            db, doc = _setup_db(tmp)
            claim_id = save_claim(
                db,
                text="Pedro owned the mine.",
                source_document_id=doc.id,
                predicate_verb="owned",
                confidence_origin="heuristic",
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded.confidence_source == "heuristic"

    def test_no_signals_no_fabrication(self):
        # A claim with no speaker pattern, no audience pattern, and a
        # non-reporting verb should leave all the new fields null —
        # honest absence over a fabricated guess.
        with tempfile.TemporaryDirectory() as tmp:
            db, doc = _setup_db(tmp)
            claim_id = save_claim(
                db,
                text="The mine produced 100 quintales of silver in 1820.",
                source_document_id=doc.id,
                source_excerpt="100 quintales of silver, 1820.",
                predicate_verb="produced",
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded.speaker_name is None
            assert loaded.quotation_kind is None
            assert loaded.audience is None

    def test_missing_source_document_warns_without_substitution(self, caplog):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")

            caplog.set_level(logging.WARNING, logger="fichero.workflows.tools._entity_writer")
            claim_id = save_claim(
                db,
                text="Pedro owned the mine.",
                source_document_id="missing-doc",
                predicate_verb="owned",
            )

            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded is not None
            assert loaded.source_document_id == "missing-doc"
            assert loaded.corroborating_source_ids == ["missing-doc"]
            assert "Missing source document missing-doc" in caplog.text
            assert "using no substitute document" in caplog.text

    def test_missing_source_authority_warns_before_neutral_weight(self, caplog):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.fichero")

            caplog.set_level(logging.WARNING, logger="fichero.workflows.tools._entity_writer")
            assert _source_authority_weight(db, "missing-doc") == 1.0

            assert "Missing source document missing-doc" in caplog.text
            assert "source authority" in caplog.text


class TestSaveClaimRecordedAt:
    """#1657: save_claim must forward claim_recorded_at to KnowledgeClaim."""

    def test_claim_recorded_at_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, doc = _setup_db(tmp)
            claim_id = save_claim(
                db,
                text="Pedro owned the mine.",
                source_document_id=doc.id,
                claim_recorded_at="1923-02-05",
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded is not None
            assert loaded.claim_recorded_at == "1923-02-05"

    def test_claim_recorded_at_none_when_not_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            db, doc = _setup_db(tmp)
            claim_id = save_claim(
                db,
                text="Pedro owned the mine.",
                source_document_id=doc.id,
            )
            loaded = db.get(KnowledgeClaim, claim_id)
            assert loaded is not None
            assert loaded.claim_recorded_at is None
