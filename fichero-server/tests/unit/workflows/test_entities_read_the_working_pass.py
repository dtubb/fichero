"""The extract-names step reads the page's text from its working pass, and never skips a page in silence.

Found live on the demo app (2026-10-10): the recipe's "Extract entities" step processed a page in 4 ms
and wrote nothing, though the page reads "Testamento de Pedro Ruiz, Medellin, 1951." Its text lived only
as readings on its working pass's lines; the step read `metadata["transcription"]`, `page_content` and a
transcription artifact, found none, skipped the page without a word and reported done.

Built here on the Spanish notarial corpus page imported through `format.import`, with its page text
blanked so the words exist ONLY as line readings. The model is stubbed: it names a person exactly when
the person's name is in the text it is handed.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from tests.integration._seedlib import seed

import fichero_server.api.main  # noqa: F401  (registers every action)
import fichero_server.workflows.tools  # noqa: F401
import fichero_server.workflows.tools.extract_all as extract_all_module
import fichero_server.workflows.tools.extract_entities_only as module
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.db import Database, EmbedOutcome, db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import DocType, Document, FileType, KnowledgeEntity, Status
from fichero_server.workflows.runtime import build_initial_state

PAGE = Path(__file__).parents[1] / "formats" / "fixtures" / "corpus" / "transkribus_spanish-notarial_0074.page.xml"
PERSON = ActionContext(actor="historian", library_path=None, is_bootstrap=True)


@pytest.fixture
def library(tmp_path, monkeypatch):
    monkeypatch.setattr("fichero_server.llm.resolve_model_alias", lambda provider, model: ("fake", "fake-model"))
    monkeypatch.setattr(Database, "embed", lambda *a, **k: EmbedOutcome(embedded=False, reason="no_embeddable_text"))
    monkeypatch.setattr("fichero_server.knowledge.entity_vectors.find_similar", lambda *a, **k: [])
    monkeypatch.setattr("fichero_server.knowledge.entity_vectors.index_entity", lambda *a, **k: None)
    seen: list[str] = []

    async def model(**kwargs):
        seen.append(kwargs["prompt"])
        people = [{"name": "Anna Maria"}] if "Anna Maria" in kwargs["prompt"] else []
        return extract_all_module._EntitiesOnly(people=people, places=[], organizations=[], dates=[], events=[])

    monkeypatch.setattr(module, "chat_structured_with_fallback", model)
    path = tmp_path / "lines.fichero"
    seed(path)
    db = db_manager.get_database(path)
    folder = Document(name="Corpus", doc_type=DocType.folder)
    db.save(folder)
    yield path, db, folder, seen
    db_manager.close_database(path)


def _page(db, folder, tmp_path, name: str, *, imported: bool) -> Document:
    doc = Document(name=name, parent_id=folder.id, doc_type=DocType.file, file_type=FileType.image,
                   path=str(tmp_path / name), status=Status.completed)
    db.save(doc)
    if imported:
        registry.invoke(db, "format.import", {"document_id": doc.id, "path": str(PAGE)}, PERSON)
    doc = db.get(Document, doc.id)
    doc.page_content = ""          # the words live ONLY on the working pass's lines
    doc.metadata = {key: value for key, value in (doc.metadata or {}).items() if key != "transcription"}
    db.save(doc)
    return doc


def _run(path: Path, folder_id: str) -> dict:
    state = build_initial_state({"selected_doc_ids": [folder_id]}, library_path=str(path))
    state["task_id"] = "entities-read-the-working-pass"
    return asyncio.run(module.extract_entities_only(
        inputs={}, state=state, llm_config=LLMConfig(provider="$small", model="$small")))


def test_a_page_whose_text_is_only_line_readings_has_its_names_found(library, tmp_path):
    """WHY: the step skipped such a page as blank and reported done with nothing done. The text is
    read through the working pass (`document_text`), as written with its markup read (#5651)."""
    path, db, folder, seen = library
    page = _page(db, folder, tmp_path, "0074.jpg", imported=True)

    result = _run(path, folder.id)

    assert result["count"] == 1 and result["summary"]["documents_left_out"] == 0
    assert seen and "la dicha Anna Maria" in seen[0] and "$" not in seen[0]
    assert any(e.canonical_name == "Anna Maria" for e in db.query(KnowledgeEntity))
    assert page.page_content == ""


def test_a_page_with_no_text_at_all_is_named_as_left_out_with_why(library, tmp_path):
    """WHY: a page with nothing to read must not vanish from the run: the summary names it and why,
    so a step that read nothing cannot say it is done."""
    path, db, folder, _seen = library
    _page(db, folder, tmp_path, "0074.jpg", imported=True)
    blank = _page(db, folder, tmp_path, "blank.jpg", imported=False)

    result = _run(path, folder.id)

    assert result["summary"]["documents_left_out"] == 1
    (left,) = result["summary"]["left_out"]
    assert left["document_id"] == blank.id and left["why"] == module.NO_TEXT
