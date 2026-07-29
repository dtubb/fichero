"""Tests for files_tool per-page expansion (#891).

Locks the contract that when a selected document is a parent PDF with
page children, files_tool emits one entry per page child (each with
the parent's path + the page child's document dict).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from fichero_server.models import DocType, Document, FileType, Status


def _doc(
    *,
    doc_id: str,
    name: str,
    doc_type: DocType = DocType.file,
    file_type: FileType | None = None,
    path: str | None = None,
    parent_id: str | None = None,
    sequence: int | None = None,
    page_content: str | None = None,
) -> Document:
    return Document(
        id=doc_id,
        name=name,
        doc_type=doc_type,
        file_type=file_type,
        path=path,
        parent_id=parent_id,
        sequence=sequence,
        page_content=page_content,
        status=Status.completed,
        metadata={},
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_selected_pdf_expands_to_one_entry_per_page() -> None:
    """Selecting a parent PDF in the sidebar must emit one (path, page)
    pair per page child so fan_out creates one parallel branch per page."""
    parent = _doc(
        doc_id="pdf-1",
        name="book.pdf",
        file_type=FileType.pdf,
        path="/tmp/lib/book.pdf",
    )
    pages = [
        _doc(
            doc_id=f"page-{i}",
            name=f"book.pdf - Page {i}",
            doc_type=DocType.page,
            parent_id="pdf-1",
            sequence=i,
            page_content=f"Page {i} body text",
        )
        for i in range(1, 4)
    ]

    fake_db = MagicMock()
    fake_db.get.side_effect = lambda model, doc_id: parent if doc_id == "pdf-1" else None
    fake_db.query.return_value = pages

    from fichero_server.workflows.tools.sources import files_tool

    with patch("fichero_server.workflows.tools.sources.db_manager.get_database", return_value=fake_db):
        result = await files_tool(
            inputs={},
            state={
                "selected_doc_ids": ["pdf-1"],
                "library_path": "/tmp/lib",
            },
            llm_config=MagicMock(),
        )

    assert result["count"] == 3
    assert result["files"] == ["/tmp/lib/book.pdf"] * 3
    # documents are in sequence order with their own ids
    ids = [d["id"] for d in result["documents"]]
    assert ids == ["page-1", "page-2", "page-3"]
    # each document carries its own page_content
    contents = [d["page_content"] for d in result["documents"]]
    assert contents == ["Page 1 body text", "Page 2 body text", "Page 3 body text"]


@pytest.mark.asyncio
async def test_leaf_file_without_page_children_emits_one_entry() -> None:
    """A file with no page children (e.g. a .md or single-page PDF that
    wasn't split) should emit exactly one (path, doc) entry — preserves
    the pre-#891 contract for non-paginated files."""
    parent = _doc(
        doc_id="md-1",
        name="notes.md",
        path="/tmp/lib/notes.md",
    )

    fake_db = MagicMock()
    fake_db.get.side_effect = lambda model, doc_id: parent if doc_id == "md-1" else None
    fake_db.query.return_value = []  # no page children

    from fichero_server.workflows.tools.sources import files_tool

    with patch("fichero_server.workflows.tools.sources.db_manager.get_database", return_value=fake_db):
        result = await files_tool(
            inputs={},
            state={
                "selected_doc_ids": ["md-1"],
                "library_path": "/tmp/lib",
            },
            llm_config=MagicMock(),
        )

    assert result["count"] == 1
    assert result["files"] == ["/tmp/lib/notes.md"]
    assert result["documents"][0]["id"] == "md-1"


@pytest.mark.asyncio
async def test_page_selected_directly_emits_single_entry() -> None:
    """When the user selects a page child directly, emit one entry —
    the parent's path + the page document. Same as before the per-page
    expansion change."""
    parent = _doc(
        doc_id="pdf-1",
        name="book.pdf",
        file_type=FileType.pdf,
        path="/tmp/lib/book.pdf",
    )
    page = _doc(
        doc_id="page-42",
        name="book.pdf - Page 42",
        doc_type=DocType.page,
        parent_id="pdf-1",
        sequence=42,
        page_content="forty-two body",
    )

    fake_db = MagicMock()
    # First get returns the page; _resolve_page_to_parent will fetch parent.
    fake_db.get.side_effect = lambda model, doc_id: {
        "page-42": page, "pdf-1": parent
    }.get(doc_id)
    fake_db.query.return_value = []

    from fichero_server.workflows.tools.sources import files_tool

    with patch("fichero_server.workflows.tools.sources.db_manager.get_database", return_value=fake_db):
        result = await files_tool(
            inputs={},
            state={
                "selected_doc_ids": ["page-42"],
                "library_path": "/tmp/lib",
            },
            llm_config=MagicMock(),
        )

    assert result["count"] == 1
    assert result["files"] == ["/tmp/lib/book.pdf"]
    assert result["documents"][0]["id"] == "page-42"
    assert result["documents"][0]["page_content"] == "forty-two body"


@pytest.mark.asyncio
async def test_duplicate_selection_deduped_by_doc_id() -> None:
    """Selecting the same parent twice (or a parent + one of its pages)
    must not double-count any page in the output."""
    parent = _doc(
        doc_id="pdf-1",
        name="book.pdf",
        file_type=FileType.pdf,
        path="/tmp/lib/book.pdf",
    )
    pages = [
        _doc(
            doc_id=f"page-{i}",
            name=f"Page {i}",
            doc_type=DocType.page,
            parent_id="pdf-1",
            sequence=i,
            page_content=f"p{i}",
        )
        for i in range(1, 3)
    ]

    fake_db = MagicMock()
    fake_db.get.side_effect = lambda model, doc_id: {
        "pdf-1": parent, "page-1": pages[0]
    }.get(doc_id)
    fake_db.query.return_value = pages

    from fichero_server.workflows.tools.sources import files_tool

    with patch("fichero_server.workflows.tools.sources.db_manager.get_database", return_value=fake_db):
        result = await files_tool(
            inputs={},
            state={
                # Parent + page-1 both selected
                "selected_doc_ids": ["pdf-1", "page-1"],
                "library_path": "/tmp/lib",
            },
            llm_config=MagicMock(),
        )

    # parent expanded to page-1 + page-2; page-1 separately would be a
    # duplicate, dedup'd by seen_ids.
    ids = [d["id"] for d in result["documents"]]
    assert sorted(ids) == ["page-1", "page-2"]
