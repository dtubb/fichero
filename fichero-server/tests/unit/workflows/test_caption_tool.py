"""Contract coverage for the caption workflow tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools import caption as tool


def test_caption_prompt_uses_style_length_and_safe_fallback():
    prompt = tool.build_caption_prompt({"style": "creative", "max_length": 7})
    fallback = tool.build_caption_prompt({"style": "unknown"})
    assert "engaging, creative" in prompt and "under 7 words" in prompt
    assert "factual, objective" in fallback


@pytest.mark.asyncio
async def test_caption_forwards_length_and_vision_options(monkeypatch):
    process = AsyncMock(return_value={"text": "A quiet street"})
    monkeypatch.setattr(tool, "process_vision", process)
    result = await tool.caption(
        {"files": ["photo.jpg"], "style": "technical", "max_length": 5, "max_image_dimension": 512, "temperature": 0.2, "max_tokens": 40, "save_to_db": False},
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"}, LLMConfig(provider="test", model="test"),
    )
    assert result["text"] == "A quiet street"
    kwargs = process.await_args.kwargs
    assert "precise, technical" in kwargs["prompt"]
    assert kwargs["output_format"] == "words" and kwargs["output_options"] == {"max_words": 5}
    assert kwargs["max_image_dimension"] == 512 and kwargs["max_tokens"] == 40


@pytest.mark.asyncio
async def test_caption_uses_state_file_and_explicit_prompt(monkeypatch):
    process = AsyncMock(return_value={"error": "provider unavailable"})
    monkeypatch.setattr(tool, "process_vision", process)
    result = await tool.caption(
        {"prompt": "Use exactly this prompt", "metadata_field": "short_caption"},
        {"input_files": ["fallback.png"]}, LLMConfig(provider="test", model="test"),
    )
    assert result["error"] == "provider unavailable"
    kwargs = process.await_args.kwargs
    assert kwargs["files"] == ["fallback.png"] and kwargs["prompt"] == "Use exactly this prompt"
    assert kwargs["metadata_field"] == "short_caption"
