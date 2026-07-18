"""Contract coverage for the classify vision workflow tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero.llm import LLMConfig
from fichero.workflows.tools import classify as tool


def test_classify_prompt_switches_between_single_and_multi_label():
    single = tool.build_classify_prompt({"categories": ["letter", "map"]})
    multi = tool.build_classify_prompt({"categories": ["letter", "map"], "multi_label": True})
    assert "exactly ONE" in single and '"letter"' in single
    assert "ALL applicable" in multi and "comma-separated list" in multi


@pytest.mark.asyncio
async def test_classify_forwards_single_label_constraints(monkeypatch):
    process = AsyncMock(return_value={"text": "letter"})
    monkeypatch.setattr(tool, "process_vision", process)
    result = await tool.classify(
        {"files": ["page.png"], "categories": ["letter", "map"], "save_to_db": False},
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"}, LLMConfig(provider="test", model="test"),
    )
    assert result["text"] == "letter"
    kwargs = process.await_args.kwargs
    assert kwargs["output_format"] == "choice"
    assert kwargs["output_options"] == {"choices": ["letter", "map"], "max_items": 2}
    assert kwargs["reference_values"] == {"categories": ["letter", "map"]}
    assert kwargs["match_mode"] == "strict"


@pytest.mark.asyncio
async def test_classify_multi_label_honors_overrides_and_state_files(monkeypatch):
    process = AsyncMock(return_value={"error": "provider unavailable"})
    monkeypatch.setattr(tool, "process_vision", process)
    result = await tool.classify(
        {"categories": ["receipt"], "multi_label": True, "prompt": "Use this", "output_format": "json", "match_mode": "prefer", "metadata_field": "kind"},
        {"input_files": ["fallback.jpg"]}, LLMConfig(provider="test", model="test"),
    )
    assert result["error"] == "provider unavailable"
    kwargs = process.await_args.kwargs
    assert kwargs["files"] == ["fallback.jpg"] and kwargs["prompt"] == "Use this"
    assert kwargs["output_format"] == "json" and kwargs["match_mode"] == "prefer"
    assert kwargs["metadata_field"] == "kind"
