"""Tests for the workflow Selection source node (#667)."""

from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.workflows.tools.sources import selection_tool


@pytest.mark.asyncio
async def test_selection_tool_errors_when_no_selected_docs():
    result = await selection_tool(
        inputs={},
        state={"selected_doc_ids": []},
        llm_config=None,
    )

    assert result["count"] == 0
    assert result["files"] == []
    assert "No documents selected" in result["error"]


@pytest.mark.asyncio
async def test_selection_tool_delegates_to_files_tool_when_selected_docs_present():
    expected = {"files": ["/tmp/a.pdf"], "documents": [{"id": "doc-1"}], "count": 1}
    with patch(
        "fichero_server.workflows.tools.sources.files_tool",
        new=AsyncMock(return_value=expected),
    ) as mocked:
        result = await selection_tool(
            inputs={},
            state={"selected_doc_ids": ["doc-1"], "library_path": "/tmp/lib"},
            llm_config=None,
        )

    mocked.assert_awaited_once()
    assert result == expected
