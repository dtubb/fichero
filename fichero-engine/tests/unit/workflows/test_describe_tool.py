"""Contract coverage for the describe vision workflow tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero.llm import LLMConfig
from fichero.workflows.tools import describe as tool


@pytest.mark.parametrize(
    ("level", "expected"),
    [("brief", "one-sentence"), ("detailed", "handwriting versus print"), ("comprehensive", "colors, textures")],
)
def test_describe_prompt_selects_detail_level_and_focus(level, expected):
    prompt = tool.build_describe_prompt({"detail_level": level, "focus": "the seal"})

    assert expected in prompt
    assert "Focus particularly on: the seal" in prompt


@pytest.mark.asyncio
async def test_describe_forwards_custom_vision_inputs(monkeypatch):
    process = AsyncMock(return_value={"text": "description", "artifacts": ["a1"]})
    monkeypatch.setattr(tool, "process_vision", process)

    result = await tool.describe(
        {
            "files": ["scan.jpg"], "documents": [{"id": "doc-1"}],
            "detail_level": "brief", "focus": "signature", "vision_mode": "apple",
            "max_image_dimension": 512, "temperature": 0.4, "max_tokens": 80,
            "output_format": "json", "choices": ["a"], "max_words": 20, "max_items": 2,
            "reference_values": ["ref"], "match_mode": "require", "context": "archive",
            "metadata": {"page": 1}, "save_to_db": False, "save_to_file": True,
            "metadata_field": "caption",
        },
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"},
        LLMConfig(provider="test", model="test"),
    )

    assert result["artifacts"] == ["a1"]
    kwargs = process.await_args.kwargs
    assert kwargs["vision_mode"] == "apple"
    assert kwargs["max_image_dimension"] == 512
    assert "one-sentence" in kwargs["prompt"] and "signature" in kwargs["prompt"]
    assert kwargs["output_options"] == {"choices": ["a"], "max_words": 20, "max_items": 2}
    assert kwargs["save_to_db"] is False and kwargs["save_to_file_flag"] is True
    assert kwargs["metadata_field"] == "caption"


@pytest.mark.asyncio
async def test_describe_uses_state_files_explicit_prompt_and_defaults(monkeypatch):
    process = AsyncMock(return_value={"error": "provider unavailable", "artifacts": []})
    monkeypatch.setattr(tool, "process_vision", process)

    result = await tool.describe(
        {"prompt": "Use exactly this prompt"}, {"input_files": ["fallback.png"]}, LLMConfig(provider="test", model="test")
    )

    assert result["error"] == "provider unavailable"
    kwargs = process.await_args.kwargs
    assert kwargs["files"] == ["fallback.png"]
    assert kwargs["prompt"] == "Use exactly this prompt"
    assert kwargs["vision_mode"] == "llm"
    assert kwargs["max_image_dimension"] == 2048
    assert kwargs["output_format"] == "text"
    assert kwargs["metadata_field"] == "description"
