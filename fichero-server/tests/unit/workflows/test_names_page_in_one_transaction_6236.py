"""#6236, #6212: the names step writes each page's names in one short transaction, never one for the step.

WHY: every name autocommitted two or three statements (its row, its page, its mentions) and scheduled its vector
two or three times; one transaction for a whole step instead (55k new rows) ran an 8 GB Mac out of memory. The
match rules must come out the same: the next name on a page still matches the names written before it.
"""
# ruff: noqa: F811  (the imported `library` fixture is used by name)
from __future__ import annotations

import contextlib

import pytest

import fichero_server.workflows.tools.extract_all as extract_all_module
from fichero_server.db import Database, db_manager
from fichero_server.models import DocType, Document, FileType, KnowledgeEntity, Status
from fichero_server.models.knowledge import EntityMatchCandidate
from tests.integration._seedlib import seed
from tests.unit.workflows.test_entities_read_the_working_pass import _run, library, module  # noqa: F401

NAMES = ["Pedro Ruiz", "Pedro Ruíz", "Juan de Mena", "Juan de Mesa", "Anna Maria"]
PAGES = [  # a name reused across pages, one written alike (stage 1.6) and one merely similar (a proposal)
    "Pedro Ruiz vecino de Quibdó firmó ante Juan de Mena.",
    "Pedro Ruíz dijo que Anna Maria era su hija.",
    "Juan de Mesa y Pedro Ruiz, testigos.",
]


def _pages(db, folder, where):
    for i, text in enumerate(PAGES):
        db.save(Document(name=f"p{i}.jpg", parent_id=folder.id, doc_type=DocType.file, file_type=FileType.image,
                         path=str(where / f"p{i}.jpg"), page_content=text, status=Status.completed))


@pytest.fixture
def names(library, monkeypatch, tmp_path):
    async def model(**kwargs):
        people = [{"name": n} for n in NAMES if n in kwargs["prompt"]]
        return extract_all_module._EntitiesOnly(people=people, places=[], organizations=[], dates=[], events=[])

    monkeypatch.setattr(module, "chat_structured_with_fallback", model)
    path, db, folder, _seen = library
    _pages(db, folder, tmp_path)
    return path, db, folder


def _graph(db) -> tuple:
    entities = sorted(
        (e.canonical_name, tuple(sorted(e.aliases)), len(e.source_document_ids),
         tuple(sorted((s.source_excerpt, s.source_char_start) for s in e.source_supports)))
        for e in db.query(KnowledgeEntity))
    names = {e.id: e.canonical_name for e in db.query(KnowledgeEntity)}
    pairs = sorted(tuple(sorted((names[c.survivor_entity_id], names[c.candidate_entity_id])))
                   for c in db.query(EntityMatchCandidate))
    return entities, pairs


def test_each_page_writes_its_names_in_one_transaction_and_the_step_in_none(names, monkeypatch):
    path, db, folder = names
    opened: list[int] = []  # one entry per outermost transaction
    saves_outside: list[str] = []
    saved_in: set[int] = set()  # which transaction each name was written in
    real_transaction, real_save = Database.transaction, Database.save

    @contextlib.contextmanager
    def counting(self):
        if not self.in_transaction:
            opened.append(1)
        with real_transaction(self):
            yield

    def watching(self, obj, *a, **k):
        if type(obj).__name__ == "KnowledgeEntity" and obj.canonical_name in NAMES:
            if self.in_transaction:
                saved_in.add(len(opened))
            else:
                saves_outside.append(obj.canonical_name)
        return real_save(self, obj, *a, **k)

    monkeypatch.setattr(Database, "transaction", counting)
    monkeypatch.setattr(Database, "save", watching)
    result = _run(path, folder.id)

    assert not result.get("error") and result["summary"]["documents_processed"] == 3
    assert saves_outside == [], f"names written outside a page's transaction: {saves_outside}"
    assert len(saved_in) == len(PAGES), f"three pages' names went into {len(saved_in)} transaction(s)"


def test_the_names_and_proposals_are_the_same_as_written_name_by_name(names, monkeypatch, tmp_path):
    path, db, folder = names
    _run(path, folder.id)
    batched = _graph(db)

    monkeypatch.setattr(module, "_one_page_of_writes", lambda db: contextlib.nullcontext())
    path_before = tmp_path / "name-by-name.fichero"  # the same pages in a second library, written as before
    seed(path_before)
    db_before = db_manager.get_database(path_before)
    try:
        folder_before = Document(name="Corpus", doc_type=DocType.folder)
        db_before.save(folder_before)
        _pages(db_before, folder_before, tmp_path)
        _run(path_before, folder_before.id)
        assert _graph(db_before) == batched
    finally:
        db_manager.close_database(path_before)
    entities, pairs = batched
    ours = [e for e in entities if e[0] in NAMES]  # the seed library has its own names
    assert [(e[0], e[1], e[2]) for e in ours] == [
        ("Anna Maria", (), 1), ("Juan de Mena", (), 1), ("Juan de Mesa", (), 1), ("Pedro Ruiz", ("Pedro Ruíz",), 3)]
    assert ("Juan de Mena", "Juan de Mesa") in pairs
