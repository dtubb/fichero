"""Unit tests for files_tool's page→parent promotion behaviour (#670)."""

from __future__ import annotations

import logging

from fichero_server.models import DocType, Document
from fichero_server.workflows.tools.sources import _resolve_page_to_parent


class _StubDB:
    """Minimal db.get(Document, id) shim for the helper's parent lookup."""

    def __init__(self, docs: list[Document]):
        self._docs = {d.id: d for d in docs}

    def get(self, _model, doc_id):
        return self._docs.get(doc_id)


class TestResolvePageToParent:
    def test_page_without_parent_returns_none(self):
        page = Document(name="p1", doc_type=DocType.page, path=None)
        db = _StubDB([page])
        assert _resolve_page_to_parent(page, db) is None

    def test_page_with_parent_but_parent_has_no_path_returns_none(self, caplog):
        parent = Document(id="P", name="p", doc_type=DocType.folder, path=None)
        page = Document(
            id="pg", name="page 1", doc_type=DocType.page, path=None,
            parent_id="P", sequence=0,
        )
        db = _StubDB([parent, page])
        with caplog.at_level(logging.WARNING):
            assert _resolve_page_to_parent(page, db) is None
        assert any("no path" in rec.message for rec in caplog.records)

    def test_page_with_sequence_attaches_requested_page_metadata(self):
        parent = Document(
            id="pdf", name="doc.pdf", doc_type=DocType.file,
            path="/lib/doc.pdf", metadata={"existing": "keep"},
        )
        page = Document(
            id="pg", name="page 3", doc_type=DocType.page, path=None,
            parent_id="pdf", sequence=2,
        )
        db = _StubDB([parent, page])
        resolved = _resolve_page_to_parent(page, db)
        assert resolved is not None
        assert resolved.path == "/lib/doc.pdf"
        # Existing parent metadata preserved
        assert resolved.metadata["existing"] == "keep"
        # Page hint attached
        assert resolved.metadata["requested_page"] == 2

    def test_parent_not_mutated_by_resolve(self):
        # Critical: the DB-cached parent must not be mutated in place —
        # other callers would see the page metadata as if it belonged to
        # the parent file.
        parent = Document(
            id="pdf", name="doc.pdf", doc_type=DocType.file,
            path="/lib/doc.pdf", metadata={},
        )
        page = Document(
            id="pg", name="page 5", doc_type=DocType.page, path=None,
            parent_id="pdf", sequence=4,
        )
        db = _StubDB([parent, page])
        _ = _resolve_page_to_parent(page, db)
        assert "requested_page" not in parent.metadata

    def test_page_without_sequence_still_returns_parent_no_metadata(self):
        parent = Document(
            id="pdf", name="doc.pdf", doc_type=DocType.file,
            path="/lib/doc.pdf",
        )
        page = Document(
            id="pg", name="chunk", doc_type=DocType.chunk, path=None,
            parent_id="pdf", sequence=None,
        )
        db = _StubDB([parent, page])
        resolved = _resolve_page_to_parent(page, db)
        assert resolved is parent  # Same instance — no copy needed
        assert "requested_page" not in (resolved.metadata or {})

    def test_resolution_logged_with_page_context(self, caplog):
        parent = Document(id="pdf", name="doc.pdf", doc_type=DocType.file, path="/lib/doc.pdf")
        page = Document(
            id="pg", name="page 1", doc_type=DocType.page, path=None,
            parent_id="pdf", sequence=0,
        )
        db = _StubDB([parent, page])
        with caplog.at_level(logging.INFO):
            _resolve_page_to_parent(page, db)
        messages = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
        assert any("resolved through parent" in m for m in messages)
        assert any("selected page document" in m for m in messages)
