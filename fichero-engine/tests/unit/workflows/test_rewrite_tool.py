"""Contract coverage for the rewrite workflow tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero.llm import LLMConfig
from fichero.workflows.tools import rewrite as tool


def test_rewrite_prompt_uses_style_language_and_safe_unknown_fallback():
    formal = tool.build_rewrite_prompt({"style": "formal", "target_language": "Spanish"})
    fallback = tool.build_rewrite_prompt({"style": "unknown"})

    assert "formal, professional" in formal
    assert "Write the output in Spanish." in formal
    assert "Do not add new information" in formal
    assert "as concise as possible" in fallback


@pytest.mark.asyncio
async def test_rewrite_forwards_custom_processing_configuration(monkeypatch):
    process = AsyncMock(return_value={"text": "rewritten", "artifacts": ["a1"]})
    monkeypatch.setattr(tool, "process_text", process)

    result = await tool.rewrite(
        {
            "text": "Source", "documents": [{"id": "doc-1"}], "style": "academic",
            "target_language": "French", "temperature": 0.2, "max_tokens": 88,
            "output_format": "json", "max_words": 10, "reference_values": ["ref"],
            "match_mode": "require", "context": "context", "metadata": {"page": 2},
            "save_to_db": False, "save_to_file": True, "metadata_field": "edited",
            "chunk_size_chars": 200,
        },
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"},
        LLMConfig(provider="test", model="test"),
    )

    assert result["text"] == "rewritten"
    kwargs = process.await_args.kwargs
    assert "academic style" in kwargs["prompt"] and "French" in kwargs["prompt"]
    assert kwargs["documents"] == [{"id": "doc-1"}]
    assert kwargs["temperature"] == 0.2 and kwargs["max_tokens"] == 88
    assert kwargs["output_options"] == {"max_words": 10}
    assert kwargs["save_to_db"] is False and kwargs["save_to_file_flag"] is True
    assert kwargs["metadata_field"] == "edited" and kwargs["chunk_size_chars"] == 200


@pytest.mark.asyncio
async def test_rewrite_preserves_explicit_prompt_and_defaults(monkeypatch):
    process = AsyncMock(return_value={"error": "provider unavailable", "artifacts": []})
    monkeypatch.setattr(tool, "process_text", process)

    result = await tool.rewrite(
        {"text": "Source", "prompt": "Use exactly this prompt"},
        {},
        LLMConfig(provider="test", model="test"),
    )

    assert result["error"] == "provider unavailable"
    kwargs = process.await_args.kwargs
    assert kwargs["prompt"] == "Use exactly this prompt"
    assert kwargs["temperature"] == 0.5 and kwargs["max_tokens"] == 4096
    assert kwargs["output_format"] == "text" and kwargs["chunk_size_chars"] is None
