"""Names and statements are read from the expanded text, never from abbreviation markup (#5651,
`source.reading.abbreviation-markup-parsed`).

Found on `Corpus Spanish 2026-10-06`, page 0074: the page's text held the transcription's markup
(`dha$.dicha`, `$ant:Miguel`), spaCy parsed the markup, and one statement's subject read `$ant`. Built
here on that page, imported through `format.import`; spaCy is stubbed to record the text it is handed.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_readings import (
    ordered_lines,
    readings_of_segment,
    text_for_names,
    working_pass,
)
from fichero_server.importers import nlp_draft
from fichero_server.knowledge import spacy_ner
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.workflows.tools.extract_entities_only import _transcription_text

PAGE = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus" / "transkribus_spanish-notarial_0074.page.xml"
PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


@pytest.fixture
def page(db, tmp_path):
    doc = Document(name="0074.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path=str(tmp_path / "0074.jpg"), status=Status.completed)
    db.save(doc)
    registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(PAGE)}, PERSON)
    doc = db.get(Document, doc.id)
    # The page's text as the import leaves it: its lines, markup and all (#5651).
    assert "dha$.dicha" in doc.page_content and "$ant:" in doc.page_content
    return doc


def _spacy_sees(db, doc, monkeypatch) -> str:
    seen: list[str] = []
    monkeypatch.setattr(spacy_ner, "is_pipeline_available", lambda _lang: True)
    result = nlp_draft.run_nlp_draft(
        db, doc, language="es",
        ner_fn=lambda text, language: seen.append(text) or [],
        svo_fn=lambda text, language: seen.append(text) or [],
        filter_fn=lambda proposals, text: (proposals, []),
    )
    assert result.error is None, result.error
    assert seen, "spaCy was never handed the page"
    return "\n".join(seen)


def test_no_markup_reaches_spacy(db, page, monkeypatch):
    """WHY: a statement whose subject is `$ant` is the defect. spaCy is handed the expanded text:
    `dicha`, `Reverendo`, `Parroquial`, and never a `$`."""
    text = _spacy_sees(db, page, monkeypatch)
    assert "$" not in text
    assert "la dicha Anna Maria" in text and "Reverendo Miguel Carreras" in text and "Parroquial" in text


def test_a_lines_expanded_reading_is_what_names_are_read_from(db, page, monkeypatch):
    """WHY: where a person (or a model) has given a line its expanded reading, that reading is the
    better text for names than the markup parsed: it is what somebody read, not a rule's guess."""
    rows = ordered_lines(db, working_pass(db, page.id).pass_id)
    row = next(r for r in rows if any(i.content.startswith("hizieron donacion")
                                      for i in readings_of_segment(db, r.id)))
    registry.invoke(db, "representation.create", {
        "document_id": page.id, "segment_id": row.id, "kind": "transcription", "level": "expanded",
        "content": "hicieron donación a la dicha Ana María su"}, PERSON)

    text = _spacy_sees(db, page, monkeypatch)
    assert "hicieron donación a la dicha Ana María su" in text
    assert "$" not in text and "dha" not in text.split()


def test_the_entity_workflow_reads_the_same_text(db, page):
    """WHY: the extract-names workflow is the other door to the same defect (#5651); it reads the page
    through `_transcription_text`, which must hand the model the expanded text too."""
    text = _transcription_text(page, db)
    assert "$" not in text and "la dicha Anna Maria" in text


def test_a_page_without_markup_is_read_exactly_as_before(db, tmp_path):
    """WHY: the change is for marked corpora; any other page's text reaches spaCy untouched."""
    doc = Document(name="ledger.jpg", doc_type=DocType.file, file_type=FileType.image,
                   path=str(tmp_path / "ledger.jpg"), status=Status.completed,
                   page_content="Paid $5 to the cooper.\nAnd 3 to the smith.")
    db.save(doc)
    assert text_for_names(db, doc.id, doc.page_content) == doc.page_content
