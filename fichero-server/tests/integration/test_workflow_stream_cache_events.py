"""Integration tests for workflow stream cache-hit event payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fichero_server.db import Database
from fichero_server.llm import LLMConfig
from fichero_server.workflows.builder import _make_parallel_node_function
from fichero_server.workflows.types import NodeDef


@pytest.mark.asyncio
async def test_file_complete_event_marks_cached_on_second_run(tmp_path: Path) -> None:
    """A cached re-run should emit file_complete with cached=True (#708)."""
    library_path = tmp_path
    db_path = library_path / "fichero.duckdb"
    Database(db_path)  # Initialize DB file used by node cache.

    source_file = library_path / "sample.txt"
    source_file.write_text("hello workflow cache\n", encoding="utf-8")

    captured_events: list[tuple[str, dict[str, Any]]] = []

    async def event_callback(event_type: str, data: dict[str, Any]) -> None:
        captured_events.append((event_type, dict(data)))

    async def fake_tool(
        *,
        inputs: dict[str, Any],
        state: dict[str, Any],
        llm_config: LLMConfig,
    ) -> dict[str, Any]:
        return {
            "text": f"processed:{inputs['files'][0]}:{llm_config.model}",
            "value": "ok",
            "cached": False,
        }

    node = NodeDef(id="describe_1", tool="describe", config={})
    llm_config = LLMConfig(provider="test-provider", model="test-model")
    parallel_node = _make_parallel_node_function(
        node_def=node,
        tool_fn=fake_tool,
        llm_config=llm_config,
        workflow_config={"workflow_id": "wf-cache-708", "skip_cache": False},
        event_callback=event_callback,
    )

    base_state = {
        "parallel_file": str(source_file),
        "parallel_document": {"id": "doc-1", "path": str(source_file)},
        "parallel_index": 0,
        "parallel_total": 1,
        "library_path": str(library_path),
        "outputs": {},
        "workflow_id": "wf-cache-708",
    }

    first_result = await parallel_node(dict(base_state))
    second_result = await parallel_node(dict(base_state))

    assert first_result["parallel_results"]["describe_1"][0]["success"] is True
    assert second_result["parallel_results"]["describe_1"][0]["cached"] is True

    file_complete_events = [
        payload for event, payload in captured_events if event == "file_complete"
    ]
    assert len(file_complete_events) >= 2
    assert file_complete_events[0].get("cached") is not True
    assert file_complete_events[1].get("cached") is True


@pytest.mark.asyncio
async def test_parallel_file_events_include_page_identity_metadata(tmp_path: Path) -> None:
    """Page fan-out events keep per-page identity even when the path is shared."""
    library_path = tmp_path
    db_path = library_path / "fichero.duckdb"
    Database(db_path)

    source_file = library_path / "parent.pdf"
    source_file.write_text("pdf bytes placeholder\n", encoding="utf-8")

    captured_events: list[tuple[str, dict[str, Any]]] = []

    async def event_callback(event_type: str, data: dict[str, Any]) -> None:
        captured_events.append((event_type, dict(data)))

    async def fake_tool(
        *,
        inputs: dict[str, Any],
        state: dict[str, Any],
        llm_config: LLMConfig,
    ) -> dict[str, Any]:
        return {"text": "ok", "cached": False}

    node = NodeDef(id="transcribe_1", tool="transcribe", config={})
    llm_config = LLMConfig(provider="test-provider", model="test-model")
    parallel_node = _make_parallel_node_function(
        node_def=node,
        tool_fn=fake_tool,
        llm_config=llm_config,
        workflow_config={"workflow_id": "wf-page-progress", "skip_cache": True},
        event_callback=event_callback,
    )

    base_state = {
        "parallel_file": str(source_file),
        "parallel_document": {
            "id": "page-2",
            "parent_id": "pdf-1",
            "name": "Page 2",
            "path": str(source_file),
            "sequence": 2,
        },
        "parallel_index": 1,
        "parallel_total": 3,
        "library_path": str(library_path),
        "outputs": {},
        "workflow_id": "wf-page-progress",
    }

    await parallel_node(dict(base_state))

    page_events = [
        payload for event, payload in captured_events if event in {"file_start", "file_complete"}
    ]
    assert len(page_events) == 2
    for payload in page_events:
        assert payload["document_id"] == "pdf-1"
        assert payload["page_id"] == "page-2"
        assert payload["display_name"] == "Page 2"
        assert payload["sequence"] == 2
