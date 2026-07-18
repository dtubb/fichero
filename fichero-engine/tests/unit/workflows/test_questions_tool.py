"""Contract coverage for the questions workflow tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero.llm import LLMConfig
from fichero.workflows.tools import questions as tool


def test_prompt_uses_requested_type_and_falls_back_for_unknown_type():
    factual = tool.build_questions_prompt({"question_type": "factual", "count": 3})
    unknown = tool.build_questions_prompt({"question_type": "unknown", "count": 1})

    assert factual.startswith("Generate 3 questions")
    assert "factual recall" in factual
    assert unknown.startswith("Generate 1 questions")
    assert "mix of factual" in unknown


@pytest.mark.asyncio
async def test_questions_forwards_custom_inputs_to_text_processor(monkeypatch):
    processed = {"text": "questions", "artifacts": ["artifact-1"]}
    process = AsyncMock(return_value=processed)
    monkeypatch.setattr(tool, "process_text", process)

    result = await tool.questions(
        {
            "text": "Source",
            "documents": [{"id": "doc-1"}],
            "context": "Context",
            "metadata": {"page": 2},
            "question_type": "analytical",
            "count": 4,
            "temperature": 0.2,
            "max_tokens": 99,
            "output_format": "markdown",
            "reference_values": ["reference"],
            "match_mode": "require",
            "save_to_db": False,
            "save_to_file": True,
            "metadata_field": "quiz",
        },
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"},
        LLMConfig(provider="test", model="test"),
    )

    assert result is processed
    kwargs = process.await_args.kwargs
    assert kwargs["prompt"].startswith("Generate 4 questions")
    assert "analytical questions" in kwargs["prompt"]
    assert kwargs["library_path"] == "/tmp/library.fichero"
    assert kwargs["task_id"] == "task-1"
    assert kwargs["documents"] == [{"id": "doc-1"}]
    assert kwargs["temperature"] == 0.2
    assert kwargs["max_tokens"] == 99
    assert kwargs["output_format"] == "markdown"
    assert kwargs["save_to_db"] is False
    assert kwargs["save_to_file_flag"] is True
    assert kwargs["metadata_field"] == "quiz"


@pytest.mark.asyncio
async def test_questions_preserves_explicit_prompt_and_processor_error(monkeypatch):
    process = AsyncMock(return_value={"error": "provider unavailable", "artifacts": []})
    monkeypatch.setattr(tool, "process_text", process)

    result = await tool.questions(
        {"text": "Source", "prompt": "Use exactly this prompt"},
        {},
        LLMConfig(provider="test", model="test"),
    )

    assert result["error"] == "provider unavailable"
    assert process.await_args.kwargs["prompt"] == "Use exactly this prompt"
    assert process.await_args.kwargs["temperature"] == 0.5
    assert process.await_args.kwargs["max_tokens"] == 2048
