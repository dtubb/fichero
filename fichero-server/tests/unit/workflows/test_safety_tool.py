"""Contract coverage for the safety vision workflow tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools import safety as tool


@pytest.mark.parametrize(
    ("threshold", "expected"),
    [
        ("strict", "Be conservative"),
        ("moderate", "general audiences"),
        ("permissive", "explicit or severe"),
        ("unknown", "general audiences"),
    ],
)
def test_safety_prompt_describes_threshold_and_categories(threshold, expected):
    prompt = tool.build_safety_prompt({"categories": ["violence", "hate"], "threshold": threshold})

    assert "violence, hate" in prompt
    assert expected in prompt
    assert '"safe": <true/false>' in prompt


@pytest.mark.asyncio
async def test_safety_forwards_custom_inputs_to_vision_processor(monkeypatch):
    processed = {"text": "safe", "artifacts": ["artifact-1"]}
    process = AsyncMock(return_value=processed)
    monkeypatch.setattr(tool, "process_vision", process)

    result = await tool.safety(
        {
            "files": ["/tmp/image.png"],
            "documents": [{"id": "doc-1"}],
            "categories": ["adult"],
            "threshold": "strict",
            "context": "archival image",
            "metadata": {"source": "scan"},
            "max_image_dimension": 1024,
            "temperature": 0.3,
            "max_tokens": 77,
            "output_format": "markdown",
            "reference_values": ["reference"],
            "match_mode": "require",
            "save_to_db": False,
            "save_to_file": True,
            "metadata_field": "review",
        },
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"},
        LLMConfig(provider="test", model="test"),
    )

    assert result is processed
    kwargs = process.await_args.kwargs
    assert kwargs["files"] == ["/tmp/image.png"]
    assert kwargs["documents"] == [{"id": "doc-1"}]
    assert "adult" in kwargs["prompt"] and "Be conservative" in kwargs["prompt"]
    assert kwargs["vision_mode"] == "llm"
    assert kwargs["max_image_dimension"] == 1024
    assert kwargs["output_format"] == "markdown"
    assert kwargs["save_to_db"] is False
    assert kwargs["save_to_file_flag"] is True
    assert kwargs["metadata_field"] == "review"


@pytest.mark.asyncio
async def test_safety_uses_state_files_and_explicit_prompt(monkeypatch):
    process = AsyncMock(return_value={"error": "vision unavailable", "artifacts": []})
    monkeypatch.setattr(tool, "process_vision", process)

    result = await tool.safety(
        {"prompt": "Use exactly this prompt"},
        {"input_files": ["state.png"]},
        LLMConfig(provider="test", model="test"),
    )

    assert result["error"] == "vision unavailable"
    assert process.await_args.kwargs["files"] == ["state.png"]
    assert process.await_args.kwargs["prompt"] == "Use exactly this prompt"
    assert process.await_args.kwargs["temperature"] == 0.1
    assert process.await_args.kwargs["max_tokens"] == 1024
