"""Coverage for workflow image-edit chain persistence."""

from __future__ import annotations

from fichero_server.models import Document, ImageEditChain
from fichero_server.workflows.tools import image_edit_chains as chains


def test_candidate_document_ids_deduplicates_all_workflow_sources():
    ids = chains._candidate_document_ids(
        {"documents": [{"id": "a"}, {"id": "a"}, {"id": "ignored"}]},
        {"documents": [{"id": "b"}], "selected_doc_ids": ["a", "c"]},
    )

    assert ids == ["a", "ignored", "b", "c"]


def test_append_persists_new_and_existing_chains(monkeypatch):
    first = Document(id="doc-1", name="one.jpg")
    second = Document(id="doc-2", name="two.jpg")
    existing = ImageEditChain(document_id=first.id, operations=[{"op": "old"}])

    class DB:
        def __init__(self):
            self.saved = []

        def get(self, _model, doc_id):
            return {first.id: first, second.id: second}.get(doc_id)

        def query(self, _model, **filters):
            return [existing] if filters["document_id"] == first.id else []

        def save(self, value):
            self.saved.append(value)

    db = DB()
    monkeypatch.setattr(chains.db_manager, "get_database", lambda _path: db)

    records = chains.append_image_edit_operations(
        {"documents": [{"id": first.id}]},
        {"library_path": "/tmp/lib", "selected_doc_ids": [first.id, second.id]},
        lambda doc: {"op": "rotate", "document": doc.id},
    )

    assert [record["document_id"] for record in records] == [first.id, second.id]
    assert existing.operations[1]["op"] == "rotate"
    assert len(db.saved) == 2
    assert db.saved[1].document_id == second.id


def test_append_without_library_path_is_noop():
    assert chains.append_image_edit_operations({}, {}, lambda _doc: {}) == []
