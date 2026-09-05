"""What `_write_kg_rows` must refuse to persist (#4666).

Two defect classes from the Caciques Indios run, both checked against real
rows rather than against the helpers in isolation:

* an RTF escape reaching a claim's text, verb, object, subject or quote —
  "se\\'f1or" where the manuscript says "señor";
* a pronoun becoming an entity and then the subject of every statement on
  the page.
"""

from __future__ import annotations

import re

import pytest

from fichero_server.models import Document, DocType
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity
from fichero_server.workflows.tools.extractors import _SECTIONS, _write_kg_rows

# BOTH shapes: RTF writes `\\'f1`, and what actually reached the knowledge
# graph was the bare `'f1` inside a word, the backslash lost on the way.
RTF_ESCAPE = re.compile(r"(?:\\'|(?<=[^\W\d_])')[0-9a-fA-F]{2}(?=[^\W\d_])")

PEOPLE_SECTION = next(s for s in _SECTIONS if s.get("schema_key") == "people")


@pytest.fixture
def page(db):
    doc = Document(name="Hoja 533 Recto", path="/caciques/533r", doc_type=DocType.page)
    db.save(doc)
    return doc


def _claims_for(db, doc_id):
    return [c for c in db.query(KnowledgeClaim) if c.source_document_id == doc_id]


class TestEscapesNeverLand:
    def test_no_persisted_field_carries_an_rtf_escape(self, db, test_package, page):
        _write_kg_rows(
            db,
            PEOPLE_SECTION,
            [
                {
                    "name": "Andres Herna\\'f1dez Varela",
                    "verb": "es",
                    "object": "ca\\'f1istin de nuestro se\\'f1or",
                    "source_text": "Andres Herna\\'f1dez Varela ca\\'f1istin",
                }
            ],
            page.id,
            page_label="533r",
            source_excerpt="Andres Hernañdez Varela cañistin",
        )
        claims = _claims_for(db, page.id)
        assert claims, "the item must still be written — repaired, not dropped"
        for claim in claims:
            haystack = " ".join(
                str(v)
                for v in (
                    claim.text,
                    claim.subject_canonical,
                    claim.predicate_verb,
                    claim.object_phrase,
                    claim.svo_subject,
                    claim.svo_object,
                    claim.source_excerpt,
                    claim.metadata,
                )
            )
            assert not RTF_ESCAPE.search(haystack), haystack
        assert any("cañistin" in (c.object_phrase or "") for c in claims)
        for entity in db.query(KnowledgeEntity):
            assert not RTF_ESCAPE.search(entity.canonical_name)

    def test_the_repaired_quote_still_anchors_to_the_page(self, db, test_package, page):
        # Decoding must bring the quote INTO agreement with the page text, not
        # out of it: the same conversion runs on both sides.
        _write_kg_rows(
            db,
            PEOPLE_SECTION,
            [
                {
                    "name": "Andres",
                    "verb": "es",
                    "object": "cañistin",
                    "source_text": "Varela ca\\'f1istin",
                }
            ],
            page.id,
            page_label="533r",
            source_excerpt="Andres xptoval Hernandez Varela cañistin estantes",
        )
        claim = _claims_for(db, page.id)[0]
        assert claim.source_char_start is not None, "quote lost its anchor"
        assert claim.metadata.get("source_text") == "Varela cañistin"


class TestPronounSubjectsNeverLand:
    def test_a_leading_pronoun_is_dropped_not_made_an_entity(
        self, db, test_package, page
    ):
        _write_kg_rows(
            db,
            PEOPLE_SECTION,
            [
                {"name": "they", "verb": "dijeron", "object": "la verdad"},
                {"name": "Andres", "verb": "otorgó", "object": "poder"},
            ],
            page.id,
            page_label="533r",
            source_excerpt="…",
        )
        names = {e.canonical_name for e in db.query(KnowledgeEntity)}
        assert "they" not in names
        assert "Andres" in names
        subjects = {c.subject_canonical for c in _claims_for(db, page.id)}
        assert subjects == {"Andres"}

    def test_one_unresolved_pronoun_does_not_poison_the_rest_of_the_page(
        self, db, test_package, page
    ):
        # Before the fix the first pronoun became the running antecedent, so
        # every later pronoun on the page resolved to "they" and the browser
        # showed one subject for the whole document.
        _write_kg_rows(
            db,
            PEOPLE_SECTION,
            [
                {"name": "ellos", "verb": "dijeron", "object": "la verdad"},
                {"name": "Andres", "verb": "otorgó", "object": "poder"},
                {"name": "ellos", "verb": "firmaron", "object": "la carta"},
            ],
            page.id,
            page_label="533r",
            source_excerpt="…",
        )
        subjects = [c.subject_canonical for c in _claims_for(db, page.id)]
        assert "ellos" not in subjects
        # The pronoun that DOES have an antecedent resolves to it; the one
        # that does not is dropped. Two claims, both about Andres.
        assert subjects.count("Andres") == 2

    def test_a_real_name_that_merely_starts_with_an_article_survives(
        self, db, test_package, page
    ):
        _write_kg_rows(
            db,
            PEOPLE_SECTION,
            [{"name": "El Cerrito", "verb": "es", "object": "un pueblo"}],
            page.id,
            page_label="533r",
            source_excerpt="…",
        )
        assert "El Cerrito" in {e.canonical_name for e in db.query(KnowledgeEntity)}


class TestNoDuplicateStatements:
    """Daniel, 2026-09-04: "NO DUPLICATES; right now it's not so good."

    `save_claim` has deduped by SVO identity since #1803, but behind two gates
    that let the same statement through anyway: it skipped any prior row whose
    provider/model differed, and it only looked at all when the caller knew a
    page label.
    """

    def _write(self, db, page, *, model, items=None):
        _write_kg_rows(
            db,
            PEOPLE_SECTION,
            items
            or [{"name": "Andres", "verb": "otorgó", "object": "poder al cacique"}],
            page.id,
            page_label="533r",
            source_excerpt="Andres otorgó poder al cacique",
            provider="apple",
            model=model,
        )

    def test_the_same_page_run_twice_writes_one_statement(
        self, db, test_package, page
    ):
        self._write(db, page, model="afm")
        self._write(db, page, model="afm")
        assert len(_claims_for(db, page.id)) == 1

    def test_a_second_model_corroborates_rather_than_duplicating(
        self, db, test_package, page
    ):
        self._write(db, page, model="afm")
        self._write(db, page, model="qwen3")
        claims = _claims_for(db, page.id)
        assert len(claims) == 1, "a second model must not mean a second row"
        # Attribution is kept, not thrown away — that was the reason the old
        # code duplicated instead of merging.
        assert "apple/qwen3" in (claims[0].metadata.get("also_extracted_by") or [])
        assert claims[0].mention_count >= 2

    def test_the_corroborating_run_keeps_its_anchor(self, db, test_package, page):
        """A corroboration you cannot follow back to a page is a count (#4672).

        The first version of the merge recorded a "provider/model" label and
        dropped the second run's page and character span on the floor — so the
        row could say two models agreed and could not say where the second one
        read it. This is the one field of the ontological layer that CANNOT be
        backfilled: the anchor is gone the moment the merge discards it.
        """
        self._write(db, page, model="afm")
        self._write(db, page, model="qwen3")
        claim = _claims_for(db, page.id)[0]

        corroborations = claim.metadata.get("corroborations") or []
        assert corroborations, "the corroborating run left no anchor"
        second = corroborations[0]
        assert second["model"] == "qwen3"
        assert second["provider"] == "apple"
        assert second["document_id"] == page.id
        assert second["page_label"] == "533r"

    def test_the_same_model_on_another_page_still_leaves_an_anchor(
        self, db, test_package, page
    ):
        """The page-scoped miss that falls through to the document merge.

        Dedup tries the page first and, missing, matches on exact SVO within
        the document — so a statement repeated on another page of the same
        document MERGES. The old early-out skipped recording anything when the
        provider and model were unchanged, so that second page's anchor was
        discarded on the strength of the label alone. One model reading the
        same thing twice is two attestations, and the row must be able to say
        where the second one was.
        """
        item = [{"name": "Andres", "verb": "otorgó", "object": "poder al cacique"}]
        for label in ("533r", "534r"):
            _write_kg_rows(
                db,
                PEOPLE_SECTION,
                item,
                page.id,
                page_label=label,
                source_excerpt="Andres otorgó poder al cacique",
                provider="apple",
                model="afm",
            )
        claim = _claims_for(db, page.id)[0]
        pages = {
            row.get("page_label")
            for row in (claim.metadata.get("corroborations") or [])
        }
        assert "534r" in pages, claim.metadata

    def test_an_identical_re_run_records_nothing(self, db, test_package, page):
        # Same model, same page: the ordinary idempotent re-extraction has
        # nothing to add, and a corroboration list that grows on every re-run
        # is a log, not evidence.
        self._write(db, page, model="afm")
        self._write(db, page, model="afm")
        claim = _claims_for(db, page.id)[0]
        assert not claim.metadata.get("corroborations")

    def test_a_whole_document_extraction_also_dedupes(self, db, test_package, page):
        # No page label: the non-paginated path, which used to skip the dedup
        # check entirely and re-write its rows on every pass.
        for _ in range(2):
            _write_kg_rows(
                db,
                PEOPLE_SECTION,
                [{"name": "Andres", "verb": "otorgó", "object": "poder al cacique"}],
                page.id,
                page_label=None,
                source_excerpt="Andres otorgó poder al cacique",
                provider="apple",
                model="afm",
            )
        assert len(_claims_for(db, page.id)) == 1

    def test_a_genuinely_different_statement_still_lands(
        self, db, test_package, page
    ):
        self._write(db, page, model="afm")
        self._write(
            db,
            page,
            model="afm",
            items=[{"name": "Andres", "verb": "firmó", "object": "la carta"}],
        )
        assert len(_claims_for(db, page.id)) == 2
