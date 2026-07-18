"""Contract coverage for the timeline workflow tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero.llm import LLMConfig
from fichero.workflows.tools import timeline as tool


@pytest.mark.parametrize(
    ("date_format", "expected"),
    [("iso", "YYYY-MM-DD"), ("natural", "March 15, 1847"), ("year_only", "only years")],
)
def test_timeline_prompt_selects_date_format_and_limit(date_format, expected):
    prompt = tool.build_timeline_prompt({"date_format": date_format, "max_events": 7})

    assert "Maximum 7 events" in prompt
    assert expected in prompt
    assert '"total_events": <number>' in prompt


@pytest.mark.asyncio
async def test_timeline_forwards_custom_processing_configuration(monkeypatch):
    process = AsyncMock(return_value={"text": "timeline", "artifacts": ["a1"]})
    monkeypatch.setattr(tool, "process_text", process)

    result = await tool.timeline(
        {
            "text": "Source", "documents": [{"id": "doc-1"}], "date_format": "natural",
            "max_events": 4, "temperature": 0.7, "max_tokens": 99, "output_format": "markdown",
            "reference_values": ["ref"], "match_mode": "require", "context": "context",
            "metadata": {"page": 1}, "save_to_db": False, "save_to_file": True,
            "metadata_field": "chronology",
        },
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"},
        LLMConfig(provider="test", model="test"),
    )

    assert result["artifacts"] == ["a1"]
    kwargs = process.await_args.kwargs
    assert "Maximum 4 events" in kwargs["prompt"] and "natural language dates" in kwargs["prompt"]
    assert kwargs["documents"] == [{"id": "doc-1"}]
    assert kwargs["temperature"] == 0.7 and kwargs["max_tokens"] == 99
    assert kwargs["save_to_db"] is False and kwargs["save_to_file_flag"] is True
    assert kwargs["metadata_field"] == "chronology"


@pytest.mark.asyncio
async def test_timeline_preserves_explicit_prompt_and_defaults(monkeypatch):
    process = AsyncMock(return_value={"error": "provider unavailable", "artifacts": []})
    monkeypatch.setattr(tool, "process_text", process)

    result = await tool.timeline(
        {"text": "Source", "prompt": "Use exactly this prompt"},
        {},
        LLMConfig(provider="test", model="test"),
    )

    assert result["error"] == "provider unavailable"
    kwargs = process.await_args.kwargs
    assert kwargs["prompt"] == "Use exactly this prompt"
    assert kwargs["temperature"] == 0.2 and kwargs["max_tokens"] == 4096
    assert kwargs["output_format"] == "json" and kwargs["metadata_field"] == "timeline"
