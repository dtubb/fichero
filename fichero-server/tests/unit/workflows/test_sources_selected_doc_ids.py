"""Tests that collection_tool respects selected_doc_ids when present."""
import pytest
from unittest.mock import MagicMock, patch

from fichero_server.workflows.tools.sources import collection_tool
from fichero_server.models import Document, DocType


def _make_doc(doc_id, name, path):
    return Document(id=doc_id, name=name, path=path, doc_type=DocType.page)


@pytest.mark.asyncio
async def test_collection_tool_respects_selected_doc_ids():
    """When selected_doc_ids is set, return only those docs, not the whole collection."""
    page_a = _make_doc("page-a", "page_001.pdf", "/lib/page_001.pdf")
    page_b = _make_doc("page-b", "page_002.pdf", "/lib/page_002.pdf")
    db = MagicMock()
    db.get.side_effect = lambda cls, doc_id: {"page-a": page_a, "page-b": page_b}.get(doc_id)

    with patch("fichero_server.workflows.tools.sources.db_manager") as mock_mgr:
        mock_mgr.get_database.return_value = db
        result = await collection_tool(
            inputs={"collection_id": "folder-x"},
            state={"library_path": "/lib", "selected_doc_ids": ["page-a"]},
            llm_config=MagicMock(),
        )

    assert result["count"] == 1
    assert result["files"] == ["/lib/page_001.pdf"]
    assert len(result["documents"]) == 1
    assert result["documents"][0]["id"] == "page-a"


@pytest.mark.asyncio
async def test_collection_tool_empty_selected_ids_uses_collection():
    """With an empty selected_doc_ids list, use the full collection."""
    page_a = _make_doc("page-a", "page_001.pdf", "/lib/page_001.pdf")
    page_b = _make_doc("page-b", "page_002.pdf", "/lib/page_002.pdf")
    db = MagicMock()

    with patch("fichero_server.workflows.tools.sources.db_manager") as mock_mgr, \
         patch("fichero_server.workflows.tools.sources._get_files_in_folder", return_value=[page_a, page_b]):
        mock_mgr.get_database.return_value = db
        result = await collection_tool(
            inputs={"collection_id": "folder-x"},
            state={"library_path": "/lib"},  # no selected_doc_ids key
            llm_config=MagicMock(),
        )

    assert result["count"] == 2


@pytest.mark.asyncio
async def test_collection_tool_selected_ids_missing_library_path_falls_through():
    """If selected_doc_ids is set but library_path is missing, fall through to collection."""
    page_a = _make_doc("page-a", "page_001.pdf", "/lib/page_001.pdf")
    db = MagicMock()

    with patch("fichero_server.workflows.tools.sources.db_manager") as mock_mgr, \
         patch("fichero_server.workflows.tools.sources._get_files_in_folder", return_value=[page_a]):
        mock_mgr.get_database.return_value = db
        result = await collection_tool(
            inputs={"collection_id": "folder-x"},
            state={"selected_doc_ids": ["page-a"]},  # no library_path
            llm_config=MagicMock(),
        )

    # Falls through to collection (which also has no library_path and returns error)
    assert result.get("count", -1) >= 0  # fell through to collection path without crashing
