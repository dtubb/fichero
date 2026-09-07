"""A pronoun is never a subject — resolve it to the actual name (#4666).

Daniel: "better to insert the actual subject and just repeat the name" than to
show "they" as the subject of a statement. `_write_kg_rows` resolves a pronoun
subject to a real name — the running antecedent (the last named subject), or,
for a FIRST-person pronoun in an authored document, the author — and drops the
item only when neither names anyone (a third-person pronoun with nothing to
repeat), because attributing it to the author would be a guess.
"""

from __future__ import annotations

from fichero_server.workflows.tools.extractors import (
    _is_first_person_subject,
    _write_kg_rows,
)


def _people_section():
    from fichero_server.models.knowledge import EntityType
    return {"name": "people", "key": "people", "entity_type": EntityType.person}


class TestFirstPersonHelper:
    def test_first_person_pronouns_are_detected(self):
        for word in ["I", "we", "We", "me", "our", "yo", "nosotros", "je", "nous"]:
            assert _is_first_person_subject(word), word

    def test_third_person_and_names_are_not_first_person(self):
        for word in ["they", "he", "she", "it", "Hindenburg", "the cacique", ""]:
            assert not _is_first_person_subject(word), word


class TestPronounSubjectResolution:
    def _claims(self, tmp_path, items, *, authors=None):
        from fichero_server.db import Database
        from fichero_server.models import Document, DocType
        from fichero_server.models.knowledge import KnowledgeClaim

        db = Database(tmp_path / "pron.fichero")
        doc = Document(id="doc-1", name="page.pdf", doc_type=DocType.file)
        if authors is not None:
            doc.source_metadata = {"authors": authors}
        db.save(doc)
        _write_kg_rows(
            db, _people_section(), items, "doc-1",
            page_label="1", source_excerpt="page text",
            provider="fixture", model="fixture-v1",
        )
        return list(db.query(KnowledgeClaim))

    def test_pronoun_after_a_named_subject_repeats_the_name(self, tmp_path):
        items = [
            {"name": "Hindenburg", "verb": "fled", "object": "the frontier", "source_text": ""},
            {"name": "they", "verb": "crossed", "object": "the border", "source_text": ""},
        ]
        claims = self._claims(tmp_path, items)
        assert len(claims) == 2
        subjects = {(c.subject_canonical or "") for c in claims}
        assert subjects == {"Hindenburg"}, (
            "the pronoun subject must repeat the named antecedent, never stay 'they'"
        )
        assert all((c.svo_subject or "").lower() != "they" for c in claims)

    def test_first_person_pronoun_resolves_to_the_author(self, tmp_path):
        items = [{"name": "I", "verb": "wrote", "object": "a letter", "source_text": ""}]
        claims = self._claims(tmp_path, items, authors=["N.C. Marshall"])
        assert len(claims) == 1
        assert claims[0].subject_canonical == "Marshall"
        assert claims[0].svo_subject == "Marshall"

    def test_third_person_with_no_antecedent_or_author_is_dropped(self, tmp_path):
        items = [{"name": "they", "verb": "arrived", "object": "at dawn", "source_text": ""}]
        claims = self._claims(tmp_path, items)
        assert claims == [], (
            "a third-person pronoun with no name to repeat must be dropped, "
            "never persisted as a bare 'they'"
        )

    def test_first_person_without_an_author_is_dropped(self, tmp_path):
        # No author to attribute to → honest drop rather than a guess.
        items = [{"name": "we", "verb": "signed", "object": "the treaty", "source_text": ""}]
        claims = self._claims(tmp_path, items)
        assert claims == []
