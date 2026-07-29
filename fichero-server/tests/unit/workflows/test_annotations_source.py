"""Coverage for the annotations-as-input workflow source."""

from __future__ import annotations

import asyncio

from fichero_server.models import Document
from fichero_server.models.knowledge import Annotation, AnnotationKind
from fichero_server.workflows.tools import annotations_source as tool


def test_source_without_library_path_is_empty():
    result = asyncio.run(tool.annotations_source_tool({}, {}, object()))

    assert result == {"files": [], "documents": [], "count": 0}


def test_source_without_selected_documents_is_empty(monkeypatch):
    result = asyncio.run(
        tool.annotations_source_tool(
            {}, {"library_path": "/tmp/lib", "selected_doc_ids": []}, object()
        )
    )

    assert result["count"] == 0


def test_source_skips_unknown_documents(monkeypatch):
    class DB:
        def get(self, *_args):
            return None

    monkeypatch.setattr("fichero_server.db.db_manager.get_database", lambda _path: DB())

    result = asyncio.run(
        tool.annotations_source_tool(
            {}, {"library_path": "/tmp/lib", "selected_doc_ids": ["missing"]}, object()
        )
    )

    assert result == {"files": [], "documents": [], "count": 0}


def test_source_emits_text_crop_with_annotation_metadata(monkeypatch):
    document = Document(id="doc-1", name="notes.txt", path="notes.txt")
    annotation = Annotation(
        id="ann-1", document_id=document.id, kind=AnnotationKind.highlight, text="marked"
    )

    class DB:
        def get(self, _model, key):
            return document if key == document.id else None

        def query(self, _model, **filters):
            assert filters == {"document_id": document.id}
            return [annotation]

    monkeypatch.setattr("fichero_server.db.db_manager.get_database", lambda _path: DB())
    monkeypatch.setattr("fichero_server.workflows.tools._annotation_input.crop_text", lambda _doc, _annotation: "cropped text")

    result = asyncio.run(
        tool.annotations_source_tool(
            {}, {"library_path": "/tmp/lib", "selected_doc_ids": [document.id]}, object()
        )
    )

    assert result["count"] == 1
    assert result["documents"][0]["annotation_id"] == "ann-1"
    assert result["documents"][0]["crop_kind"] == "text"
    assert result["documents"][0]["annotation_text"] == "marked"
    assert result["files"][0].endswith(".txt")
