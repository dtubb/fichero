"""Regression test: _propagate_to_page_children works for single-page PDFs.

#2249 — the old guard `if per_page_texts and len(per_page_texts) > 1:` silently
skipped propagation for single-page PDFs, writing the combined transcript to
the parent doc instead of the page child.  The fix drops the `> 1` check so
the helper is called whenever per_page_texts is non-empty.

This test drives _propagate_to_page_children directly with a 1-element list
and verifies that the single page-child's page_content is updated — the
observable effect that was previously skipped.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from fichero.models import DocType, Document
from fichero.workflows.tools.vision_base import _propagate_to_page_children


class _StubDB:
    """Minimal DB stub: get() by id, query() by keyword attrs, save()/embed() no-op."""

    def __init__(self, docs: list[Document]):
        self._docs = {d.id: d for d in docs}
        self.saved: list[Document] = []
        self.embedded: list[Document] = []

    def get(self, _model, doc_id):
        return self._docs.get(doc_id)

    def query(self, _model, **kwargs):
        results = list(self._docs.values())
        for k, v in kwargs.items():
            results = [d for d in results if getattr(d, k, None) == v]
        return results

    def save(self, doc):
        self.saved.append(doc)

    def embed(self, doc):
        self.embedded.append(doc)


@pytest.mark.asyncio
async def test_propagate_single_page_writes_page_content():
    """#2249: a 1-element per_page_texts list must reach the page child.

    Before the fix the caller guarded with `len(per_page_texts) > 1`, skipping
    this call entirely for single-page PDFs.  After the fix, propagation runs
    for any non-empty list.  This test verifies the helper itself handles the
    single-element case correctly — if the caller guards it out the helper
    would never run and this test would become meaningless, catching a
    regression in the caller as a false pass.  The caller-level guard is
    removed, so calling the helper with len==1 is now the live code path.
    """
    parent = Document(
        id="parent-pdf",
        name="scan.pdf",
        doc_type=DocType.file,
        path="/lib/scan.pdf",
    )
    page = Document(
        id="page-1",
        name="Page 1",
        doc_type=DocType.page,
        path=None,
        parent_id="parent-pdf",
        sequence=1,
    )
    db = _StubDB([parent, page])

    with patch("fichero.db.db_manager") as mock_db_manager:
        mock_db_manager.get_database.return_value = db
        await _propagate_to_page_children(
            parent_id="parent-pdf",
            page_texts=["Single page OCR text"],
            library_path="/lib",
        )

    # page_content must be set on the page child
    assert page.page_content == "Single page OCR text", (
        "#2249: single-page PDF must have its page child updated, not skipped"
    )
    # db.save and db.embed must both have been called for the page child
    assert any(d.id == "page-1" for d in db.saved), (
        "#2249: page child must be saved after propagation"
    )
    assert any(d.id == "page-1" for d in db.embedded), (
        "#2249: page child must be re-embedded after propagation"
    )


@pytest.mark.asyncio
async def test_propagate_blank_single_page_skips_save():
    """#2249 edge: blank text on the only page must not write page_content."""
    parent = Document(
        id="p", name="blank.pdf", doc_type=DocType.file, path="/lib/blank.pdf"
    )
    page = Document(
        id="pg", name="Page 1", doc_type=DocType.page, path=None,
        parent_id="p", sequence=1,
    )
    db = _StubDB([parent, page])

    with patch("fichero.db.db_manager") as mock_db_manager2:
        mock_db_manager2.get_database.return_value = db
        await _propagate_to_page_children(
            parent_id="p",
            page_texts=[""],
            library_path="/lib",
        )

    # Blank text → is_blank=True → no save, no embed, page_content untouched
    assert not db.saved, "#2249: blank page must not trigger a DB save"
    assert not db.embedded, "#2249: blank page must not be re-embedded"


@pytest.mark.asyncio
async def test_propagate_non_blank_written_blank_skipped():
    """#2214: non-blank pages get page_content; blank pages are skipped entirely.

    Verifies the core semantics: real transcribed text propagates to the page
    child, but empty/blank OCR output does not overwrite the page with an
    empty string (which would be indistinguishable from "never transcribed" to
    some callers, and incorrectly marks the page as processed).
    """
    parent = Document(
        id="par", name="mixed.pdf", doc_type=DocType.file, path="/lib/mixed.pdf"
    )
    page_text = Document(
        id="pg-text", name="Page 1", doc_type=DocType.page, path=None,
        parent_id="par", sequence=1,
    )
    page_blank = Document(
        id="pg-blank", name="Page 2", doc_type=DocType.page, path=None,
        parent_id="par", sequence=2,
    )
    db = _StubDB([parent, page_text, page_blank])

    with patch("fichero.db.db_manager") as mock_db_mgr:
        mock_db_mgr.get_database.return_value = db
        await _propagate_to_page_children(
            parent_id="par",
            page_texts=["Real OCR text", ""],
            library_path="/lib",
        )

    # Non-blank page: page_content set AND embedded AND saved
    assert page_text.page_content == "Real OCR text", (
        "#2214: non-blank page must have page_content set"
    )
    assert any(d.id == "pg-text" for d in db.saved), "#2214: non-blank page must be saved"
    assert any(d.id == "pg-text" for d in db.embedded), "#2214: non-blank page must be embedded"

    # Blank page: no save, no embed, page_content untouched (None)
    assert not any(d.id == "pg-blank" for d in db.saved), (
        "#2214: blank page must NOT be saved"
    )
    assert not any(d.id == "pg-blank" for d in db.embedded), (
        "#2214: blank page must NOT be embedded"
    )
