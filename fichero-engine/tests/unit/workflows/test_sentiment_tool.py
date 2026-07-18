"""Contract coverage for the sentiment workflow tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero.llm import LLMConfig
from fichero.workflows.tools import sentiment as tool


def test_sentiment_prompts_select_choice_or_detailed_json_shapes():
    assert "Return ONLY one of: positive, negative" in tool.build_sentiment_prompt({"granularity": "binary"})
    detailed = tool.build_sentiment_prompt({"granularity": "detailed", "include_emotions": True})
    assert '"confidence": <0.0-1.0>' in detailed
    assert '"emotions":' in detailed


@pytest.mark.asyncio
async def test_sentiment_uses_choice_defaults_and_reference_values(monkeypatch):
    process = AsyncMock(return_value={"text": "positive"})
    monkeypatch.setattr(tool, "process_text", process)
    result = await tool.sentiment(
        {"text": "good", "granularity": "five_point", "save_to_db": False},
        {}, LLMConfig(provider="test", model="test"),
    )
    assert result == {"text": "positive"}
    kwargs = process.await_args.kwargs
    assert kwargs["output_format"] == "choice"
    assert kwargs["reference_values"] == {"sentiment": ["very_positive", "positive", "neutral", "negative", "very_negative"]}
    assert kwargs["match_mode"] == "strict"


@pytest.mark.asyncio
async def test_sentiment_uses_json_for_emotions_and_preserves_overrides(monkeypatch):
    process = AsyncMock(return_value={"error": "provider unavailable"})
    monkeypatch.setattr(tool, "process_text", process)
    result = await tool.sentiment(
        {"text": "angry", "include_emotions": True, "prompt": "Use this", "output_format": "markdown", "reference_values": ["custom"], "match_mode": "prefer", "metadata_field": "mood"},
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"}, LLMConfig(provider="test", model="test"),
    )
    assert result["error"] == "provider unavailable"
    kwargs = process.await_args.kwargs
    assert kwargs["prompt"] == "Use this" and kwargs["output_format"] == "markdown"
    assert kwargs["reference_values"] == ["custom"] and kwargs["match_mode"] == "prefer"
    assert kwargs["metadata_field"] == "mood"
