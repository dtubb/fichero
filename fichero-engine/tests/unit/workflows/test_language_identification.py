"""Coverage for deterministic language-identification workflow output."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero.llm import LLMConfig
from fichero.multilingual import LanguageDetectionResult
from fichero.workflows.tools import language_identification as tool


def test_split_text_preserves_paragraphs_and_splits_oversized_content():
    assert tool._split_text("", 10) == []
    assert tool._split_text("one\n\ntwo", 20) == ["one\n\ntwo"]
    assert tool._split_text("abcdefgh", 3) == ["abc", "def", "gh"]


@pytest.mark.asyncio
async def test_language_identification_aggregates_chunks_and_honors_limit(monkeypatch):
    detections = iter(
        [
            LanguageDetectionResult("en", 0.8, True),
            LanguageDetectionResult("es", 0.9, True),
            LanguageDetectionResult("en", 0.4, False),
        ]
    )
    monkeypatch.setattr(tool, "detect_language", lambda _chunk: next(detections))

    result = await tool.language_identification(
        {
            "text": "first\n\nsecond\n\nthird",
            "chunk_size_chars": 6,
            "max_languages": 1,
            "save_to_db": False,
        },
        {},
        LLMConfig(provider="test", model="test"),
    )

    payload = result["value"]
    assert payload["primary_language"] == "en"
    assert payload["chunks_analyzed"] == 3
    assert payload["languages"][0]["code"] == "en"
    assert payload["languages"][0]["language"] == "English"
    assert payload["languages"][0]["confidence"] == pytest.approx(0.6)
    assert payload["languages"][0]["chunk_count"] == 2
    assert "| en | 0.600 | 2 |" in result["text"]


@pytest.mark.asyncio
async def test_language_identification_returns_explicit_empty_input_error():
    result = await tool.language_identification(
        {"text": "  "}, {}, LLMConfig(provider="test", model="test")
    )

    assert result == {
        "text": "",
        "value": None,
        "texts": [],
        "values": [],
        "results": [],
        "artifacts": [],
        "error": "No text provided",
    }


@pytest.mark.asyncio
async def test_language_identification_persists_first_document_artifact(monkeypatch):
    saved = AsyncMock(return_value="artifact-1")
    monkeypatch.setattr(tool, "save_artifact", saved)
    monkeypatch.setattr(
        tool,
        "detect_language",
        lambda _chunk: LanguageDetectionResult("fr", 0.9, True),
    )

    result = await tool.language_identification(
        {"text": "bonjour", "documents": [{"id": "doc-1", "path": "/tmp/a.txt"}]},
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"},
        LLMConfig(provider="test", model="test"),
    )

    assert result["artifacts"] == ["artifact-1"]
    assert saved.await_args.kwargs["document_id"] == "doc-1"
    assert saved.await_args.kwargs["metadata_field"] == "language_detection"
