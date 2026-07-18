"""Contract coverage for the translation workflow tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero.llm import LLMConfig
from fichero.workflows.tools import translate as tool


@pytest.mark.asyncio
async def test_translate_returns_explicit_error_for_empty_text():
    result = await tool.translate({}, {}, LLMConfig(provider="test", model="test"))

    assert result["error"] == "No text provided"
    assert result["artifacts"] == [] and result["output_files"] == []


@pytest.mark.asyncio
async def test_translate_forwards_languages_parses_and_matches_references(monkeypatch):
    translate_text = AsyncMock(return_value="bonjour")
    monkeypatch.setattr(tool, "translate_text", translate_text)
    monkeypatch.setattr(tool, "parse_output", lambda *_args: {"translation": "bonjour"})
    monkeypatch.setattr(tool, "apply_reference_matching", lambda value, refs: {**value, "refs": refs})

    result = await tool.translate(
        {"text": "hello", "source_lang": "en", "target_lang": "fr", "output_format": "json", "reference_values": ["Bonjour"], "save_to_db": False},
        {},
        LLMConfig(provider="test", model="test"),
    )

    assert result["value"] == {"translation": "bonjour", "refs": ["Bonjour"]}
    assert translate_text.await_args.args == ("hello",)
    assert translate_text.await_args.kwargs["source_lang"] == "en"
    assert translate_text.await_args.kwargs["target_lang"] == "fr"


@pytest.mark.asyncio
async def test_translate_persists_first_document_and_optional_output_file(monkeypatch):
    monkeypatch.setattr(tool, "translate_text", AsyncMock(return_value="hola"))
    monkeypatch.setattr(tool, "parse_output", lambda *_args: {"translation": "hola"})
    artifact = AsyncMock(return_value="artifact-1")
    output = AsyncMock(return_value="/tmp/hola.txt")
    monkeypatch.setattr(tool, "save_artifact", artifact)
    monkeypatch.setattr(tool, "save_to_file", output)

    result = await tool.translate(
        {"text": "hello", "documents": [{"id": "doc-1", "path": "/tmp/source.txt"}], "save_to_file": True, "metadata_field": "translated"},
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"},
        LLMConfig(provider="test", model="test"),
    )

    assert result["artifacts"] == ["artifact-1"]
    assert result["output_files"] == ["/tmp/hola.txt"]
    assert artifact.await_args.kwargs["custom_metadata"] == {"source_lang": "auto", "target_lang": "en"}
    assert output.await_args.kwargs["document_id"] == "doc-1"
