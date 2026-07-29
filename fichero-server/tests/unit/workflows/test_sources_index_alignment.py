"""Regression tests for index-alignment bugs in collection_tool and folder_tool.

#2240 — collection_tool (non-selected): filter paths AND docs by doc.path so
        file_paths[i] always corresponds to doc_data[i].  Old code filtered
        file_paths but included ALL docs in doc_data, breaking attribution when
        some docs had path=None.

#2242 — collection_tool (selected_doc_ids): two page children of the same PDF
        (same path, different doc IDs) must appear as separate entries.  Old
        dict-keyed-by-path collapsed them to one entry.

#2239 — folder_tool: (a) paths must be absolute, not library-relative;
        (b) a PDF with existing page children must be expanded to per-page
        entries so vision receives one entry per page child.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from fichero_server.models import Document, DocType, FileType
from fichero_server.llm import LLMConfig

_LLM_CFG = LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")
_LIB = "/Users/test/Library"


class _StubDB:
    """Minimal DB stub for collection_tool / folder_tool tests."""

    def __init__(self, docs: list[Document]):
        self._docs = {d.id: d for d in docs}

    def get(self, _model, doc_id):
        return self._docs.get(doc_id)

    def query(self, _model, **kwargs):
        results = list(self._docs.values())
        for k, v in kwargs.items():
            results = [d for d in results if getattr(d, k, None) == v]
        return results


# ---------------------------------------------------------------------------
# #2240 — collection_tool non-selected: index alignment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collection_tool_nonselected_file_paths_doc_data_aligned():
    """#2240: file_paths[i] and doc_data[i] must refer to the same document.

    When _get_files_in_folder returns a mix of docs with and without path
    (e.g. a page child slipped through), the old code produced:
      file_paths = [abs_path_A]         # only doc_A (has path)
      doc_data   = [doc_A.dump(), doc_B.dump()]  # ALL docs
    so file_paths[0] pointed to doc_A but doc_data[1] was doc_B — broken.
    """
    from fichero_server.workflows.tools.sources import collection_tool

    doc_with_path = Document(
        id="A", name="scan.pdf", doc_type=DocType.file,
        file_type=FileType.pdf, path="files/fi/abc_scan.pdf",
    )
    doc_without_path = Document(
        id="B", name="Page 1", doc_type=DocType.page,
        path=None, parent_id="A",
    )
    db = _StubDB([doc_with_path, doc_without_path])

    # Both docs are returned by _get_files_in_folder in a realistic scenario
    files_from_folder = [doc_with_path, doc_without_path]

    with (
        patch("fichero_server.workflows.tools.sources.db_manager") as mock_dbm,
        patch(
            "fichero_server.workflows.tools.sources._get_files_in_folder",
            return_value=files_from_folder,
        ),
        patch(
            "fichero_server.workflows.tools.sources._resolve_abs_path",
            side_effect=lambda doc, lib: f"{lib}/{doc.path}",
        ),
    ):
        mock_dbm.get_database.return_value = db
        result = await collection_tool(
            inputs={"collection_id": "col-1"},
            state={"library_path": _LIB},
            llm_config=_LLM_CFG,
        )

    files = result["files"]
    docs = result["documents"]

    assert len(files) == len(docs), (
        f"#2240: file_paths ({len(files)}) and doc_data ({len(docs)}) must be same length"
    )
    # Only doc_with_path has a path — doc_without_path must be excluded from both
    assert len(files) == 1, "#2240: only docs with path should be included"
    assert docs[0]["id"] == "A", "#2240: doc_data[0] must match file_paths[0]'s document"
    assert "scan.pdf" in files[0], "#2240: file_paths[0] should reference scan.pdf"


# ---------------------------------------------------------------------------
# #2242 — collection_tool selected: multi-page same PDF keeps both entries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_collection_tool_selected_two_pages_same_pdf_both_entries():
    """#2242: selecting page 1 and page 2 of the same PDF must produce 2 entries.

    Old dict[path → doc] collapsed both pages to 1 entry because they share the
    parent's path.  New list-of-pairs keyed by doc.id preserves both.
    """
    from fichero_server.workflows.tools.sources import collection_tool

    parent = Document(
        id="pdf", name="book.pdf", doc_type=DocType.file,
        file_type=FileType.pdf, path="files/fi/book.pdf",
    )
    page1 = Document(
        id="pg1", name="Page 1", doc_type=DocType.page,
        path=None, parent_id="pdf", sequence=1,
    )
    page2 = Document(
        id="pg2", name="Page 2", doc_type=DocType.page,
        path=None, parent_id="pdf", sequence=2,
    )
    db = _StubDB([parent, page1, page2])

    def _fake_resolve_page_to_parent(doc, _db):
        """Return a copy of the parent with the same path."""
        p = Document(
            id=parent.id, name=parent.name, doc_type=parent.doc_type,
            path=parent.path, file_type=parent.file_type,
        )
        return p

    with (
        patch("fichero_server.workflows.tools.sources.db_manager") as mock_dbm,
        patch(
            "fichero_server.workflows.tools.sources._resolve_page_to_parent",
            side_effect=_fake_resolve_page_to_parent,
        ),
        patch(
            "fichero_server.workflows.tools.sources._resolve_abs_path",
            side_effect=lambda doc, lib: f"{lib}/{doc.path}",
        ),
    ):
        mock_dbm.get_database.return_value = db
        result = await collection_tool(
            inputs={"collection_id": "col-1"},
            # selected_doc_ids selects both page children
            state={
                "library_path": _LIB,
                "selected_doc_ids": ["pg1", "pg2"],
            },
            llm_config=_LLM_CFG,
        )

    files = result["files"]
    docs = result["documents"]

    assert len(files) == 2, (
        f"#2242: two page selections of same PDF must produce 2 file entries, got {len(files)}"
    )
    assert len(docs) == 2, (
        f"#2242: doc_data must also have 2 entries, got {len(docs)}"
    )
    doc_ids = {d["id"] for d in docs}
    assert doc_ids == {"pg1", "pg2"}, (
        f"#2242: both page-child doc IDs must be preserved; got {doc_ids}"
    )


# ---------------------------------------------------------------------------
# #2239 — folder_tool: absolute paths + per-page fan-out
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_folder_tool_paths_are_absolute_not_library_relative():
    """#2239: folder_tool must return absolute paths, not library-relative ones.

    Stored paths are library-relative (e.g. 'files/fi/abc.pdf').  Downstream
    vision tools open the path directly, which fails unless it's absolute.
    """
    from fichero_server.workflows.tools.sources import folder_tool

    pdf_doc = Document(
        id="pdf1", name="scan.pdf", doc_type=DocType.file,
        file_type=FileType.pdf, path="files/fi/abc_scan.pdf",
    )
    db = _StubDB([pdf_doc])

    with (
        patch("fichero_server.workflows.tools.sources.db_manager") as mock_dbm,
        patch(
            "fichero_server.workflows.tools.sources._get_files_in_folder",
            return_value=[pdf_doc],
        ),
        patch(
            "fichero_server.workflows.tools.sources._resolve_abs_path",
            side_effect=lambda doc, lib: f"{lib}/{doc.path}",
        ),
    ):
        mock_dbm.get_database.return_value = db
        result = await folder_tool(
            inputs={"folder_id": "folder-1"},
            state={"library_path": _LIB},
            llm_config=_LLM_CFG,
        )

    files = result["files"]
    assert len(files) == 1
    assert files[0].startswith(_LIB), (
        f"#2239: path must be absolute (start with library root); got {files[0]!r}"
    )
    assert not files[0].startswith("files/"), (
        f"#2239: path must not be library-relative; got {files[0]!r}"
    )


@pytest.mark.asyncio
async def test_folder_tool_pdf_with_page_children_expands_to_per_page_entries():
    """#2239: a PDF that already has page children must expand to N per-page entries.

    Before the fix, folder_tool emitted one entry per PDF parent.  vision tools
    then processed the whole PDF rather than routing through per-page fan-out,
    defeating the per-page attribution contract.
    """
    from fichero_server.workflows.tools.sources import folder_tool

    pdf_doc = Document(
        id="pdf1", name="book.pdf", doc_type=DocType.file,
        file_type=FileType.pdf, path="files/fi/book.pdf",
    )
    page1 = Document(
        id="pg1", name="Page 1", doc_type=DocType.page, path=None,
        parent_id="pdf1", sequence=1,
    )
    page2 = Document(
        id="pg2", name="Page 2", doc_type=DocType.page, path=None,
        parent_id="pdf1", sequence=2,
    )
    _StubDB([pdf_doc, page1, page2])

    def _fake_db_query(_model, **kwargs):
        all_docs = [pdf_doc, page1, page2]
        results = all_docs
        for k, v in kwargs.items():
            results = [d for d in results if getattr(d, k, None) == v]
        return results

    stub_db = MagicMock()
    stub_db.query.side_effect = _fake_db_query

    with (
        patch("fichero_server.workflows.tools.sources.db_manager") as mock_dbm,
        patch(
            "fichero_server.workflows.tools.sources._get_files_in_folder",
            return_value=[pdf_doc],
        ),
        patch(
            "fichero_server.workflows.tools.sources._resolve_abs_path",
            side_effect=lambda doc, lib: f"{lib}/{doc.path}",
        ),
    ):
        mock_dbm.get_database.return_value = stub_db
        result = await folder_tool(
            inputs={"folder_id": "folder-1"},
            state={"library_path": _LIB},
            llm_config=_LLM_CFG,
        )

    files = result["files"]
    docs = result["documents"]

    assert len(files) == 2, (
        f"#2239: PDF with 2 page children must expand to 2 file entries, got {len(files)}"
    )
    assert len(docs) == 2, f"#2239: doc_data must also have 2 entries, got {len(docs)}"
    doc_ids = {d["id"] for d in docs}
    assert doc_ids == {"pg1", "pg2"}, (
        f"#2239: entries must refer to page children, not parent PDF; got {doc_ids}"
    )
    # All file paths point to the same PDF (the page children share the parent's path)
    assert all(f.endswith("book.pdf") for f in files), (
        "#2239: all expanded entries must reference the PDF path"
    )


@pytest.mark.asyncio
async def test_folder_tool_pdf_without_page_children_keeps_parent_entry():
    """#2239: a PDF with no page children must stay as a single parent entry."""
    from fichero_server.workflows.tools.sources import folder_tool

    pdf_doc = Document(
        id="pdf1", name="solo.pdf", doc_type=DocType.file,
        file_type=FileType.pdf, path="files/fi/solo.pdf",
    )

    stub_db = MagicMock()
    stub_db.query.return_value = []  # no page children

    with (
        patch("fichero_server.workflows.tools.sources.db_manager") as mock_dbm,
        patch(
            "fichero_server.workflows.tools.sources._get_files_in_folder",
            return_value=[pdf_doc],
        ),
        patch(
            "fichero_server.workflows.tools.sources._resolve_abs_path",
            side_effect=lambda doc, lib: f"{lib}/{doc.path}",
        ),
    ):
        mock_dbm.get_database.return_value = stub_db
        result = await folder_tool(
            inputs={"folder_id": "folder-1"},
            state={"library_path": _LIB},
            llm_config=_LLM_CFG,
        )

    assert len(result["files"]) == 1, (
        "#2239: PDF without page children must remain as 1 entry"
    )
    assert result["documents"][0]["id"] == "pdf1"
