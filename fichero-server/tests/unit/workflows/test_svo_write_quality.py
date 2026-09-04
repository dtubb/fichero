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

RTF_ESCAPE = re.compile(r"\\'[0-9a-fA-F]{2}")

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
