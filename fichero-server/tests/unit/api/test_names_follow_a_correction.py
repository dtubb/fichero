"""A corrected page's names and claims follow the corrected text (#5361).

WHY: the NLP draft refused to read a page twice, so after a person corrected "Quito" to
"Quibdó" the old entity and its claims stayed, pointing at words no longer on the page. Now a
correction takes back the page's untouched draft rows (the audited purge) and reads the page
again. If this regresses, corrections never reach the knowledge graph. What a person checked must
survive, marked as read from text that has since changed; a page whose text did not change, or
the library-open resume, must never re-read (that would redo a whole library on every open).
"""

from __future__ import annotations

import pytest

import fichero_server.api.routes.kg.nlp_draft_purge  # noqa: F401  (registers the purge action)
import fichero_server.api.routes.entity.entities  # noqa: F401
import fichero_server.api.routes.claim.links  # noqa: F401
import fichero_server.api.routes.kg.entity_curation  # noqa: F401
from fichero_server.actions import page_text_cache
from fichero_server.importers import derivatives, nlp_draft
from fichero_server.knowledge.spacy_ner import EntitySpan
from fichero_server.models import DocType, Document, FileType, Status
from fichero_server.models.knowledge import ClaimCurationState, KnowledgeClaim, KnowledgeEntity


def _first_word_is_a_place(text, language=None):
    word = text.split()[0]
    return [EntitySpan(text=word, fichero_type="location", start=0, end=len(word), label="GPE")]


@pytest.fixture(autouse=True)
def stub_spacy(monkeypatch):
    real = nlp_draft.run_nlp_draft
    monkeypatch.setattr(
        nlp_draft,
        "run_nlp_draft",
        lambda db, doc: real(
            db, doc, ner_fn=_first_word_is_a_place, svo_fn=lambda t, language=None: [],
            filter_fn=lambda p, t: (p, []),
        ),
    )


def _page(db, text):
    doc = Document(name="p.md", doc_type=DocType.file, file_type=FileType.text,
                   status=Status.pending, page_content=text, language="es")
    db.save(doc)
    return doc


def _correct(db, doc_id, text):
    doc = db.get(Document, doc_id)
    doc.page_content = text
    db.save(doc)


def _places(db):
    return {e.canonical_name for e in db.query(KnowledgeEntity)}


def test_a_correction_replaces_the_draft_read_from_the_old_text(db, test_package):
    doc = _page(db, "Quito 1810, venta de esclavo.")
    derivatives._nlp_stage(doc.id, test_package)
    assert _places(db) == {"Quito"}

    _correct(db, doc.id, "Quibdó 1810, venta de esclavo.")
    derivatives._nlp_stage(doc.id, test_package, after_correction=True)

    assert _places(db) == {"Quibdó"}
    texts = [c.text for c in db.query(KnowledgeClaim, source_document_id=doc.id)]
    assert texts and all("Quito" not in t for t in texts)


def test_a_checked_claim_survives_and_is_marked(db, test_package):
    doc = _page(db, "Quito 1810.")
    derivatives._nlp_stage(doc.id, test_package)
    [checked] = db.query(KnowledgeClaim, source_document_id=doc.id)
    checked.curation_state = ClaimCurationState.curated
    db.save(checked)

    _correct(db, doc.id, "Quibdó 1810.")
    derivatives._nlp_stage(doc.id, test_package, after_correction=True)

    kept = db.get(KnowledgeClaim, checked.id)
    assert kept is not None and "text_changed_at" in kept.metadata


def test_unchanged_text_and_the_open_time_resume_never_reread(db, test_package):
    doc = _page(db, "Quito 1810.")
    derivatives._nlp_stage(doc.id, test_package)
    before = {c.id for c in db.query(KnowledgeClaim, source_document_id=doc.id)}

    derivatives._nlp_stage(doc.id, test_package, after_correction=True)  # same text
    assert {c.id for c in db.query(KnowledgeClaim, source_document_id=doc.id)} == before

    _correct(db, doc.id, "Quibdó 1810.")
    derivatives._nlp_stage(doc.id, test_package)  # the resume path, not a correction
    assert _places(db) == {"Quito"}


def test_nothing_is_reread_where_the_library_does_not_read_names(db, test_package, monkeypatch):
    doc = _page(db, "Quito 1810.")
    derivatives._nlp_stage(doc.id, test_package)
    _correct(db, doc.id, "Quibdó 1810.")
    monkeypatch.setattr(nlp_draft, "auto_nlp_enabled", lambda: False)

    page_text_cache.reread_names_after_commit(db, doc.id)

    assert _places(db) == {"Quito"}

    monkeypatch.setattr(nlp_draft, "auto_nlp_enabled", lambda: True)
    page_text_cache.reread_names_after_commit(db, doc.id)
    assert _places(db) == {"Quibdó"}
