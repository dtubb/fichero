from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero_server.llm import LLMConfig, translate_text


@pytest.mark.asyncio
async def test_translate_text_routes_to_deepl(monkeypatch):
    called = {}

    async def _fake_deepl(*, text: str, source_lang: str | None, target_lang: str, config: LLMConfig) -> str:
        called["text"] = text
        called["source_lang"] = source_lang
        called["target_lang"] = target_lang
        called["provider"] = config.provider
        return "Hello world"

    monkeypatch.setattr("fichero_server.llm._translate_with_deepl", _fake_deepl)

    out = await translate_text(
        "Hallo wereld",
        source_lang="nl",
        target_lang="en",
        config=LLMConfig(provider="deepl", model="deepl-default"),
    )
    assert out == "Hello world"
    assert called == {
        "text": "Hallo wereld",
        "source_lang": "nl",
        "target_lang": "en",
        "provider": "deepl",
    }


@pytest.mark.asyncio
async def test_translate_text_refuses_deepl_when_local_only_enabled(monkeypatch):
    from fichero_server.llm import LocalOnlyViolationError

    monkeypatch.setattr("fichero_server.llm.is_local_only", lambda: True)

    with pytest.raises(LocalOnlyViolationError, match="translation call to remote provider deepl"):
        await translate_text(
            "Hallo wereld",
            source_lang="nl",
            target_lang="en",
            config=LLMConfig(provider="deepl", model="deepl-default"),
        )


@pytest.mark.asyncio
async def test_translate_text_uses_chat_for_non_deepl(monkeypatch):
    chat_mock = AsyncMock(return_value="Hello world")
    monkeypatch.setattr("fichero_server.llm.chat", chat_mock)

    out = await translate_text(
        "Hallo wereld",
        source_lang="nl",
        target_lang="en",
        config=LLMConfig(provider="openai", model="gpt-4o-mini"),
    )

    assert out == "Hello world"
    prompt = chat_mock.await_args.args[0]
    assert "from nl into en" in prompt
    assert "Hallo wereld" in prompt


@pytest.mark.asyncio
async def test_translate_tool_saves_translation_artifact(monkeypatch):
    from fichero_server.workflows.tools.translate import translate

    monkeypatch.setattr(
        "fichero_server.workflows.tools.translate.translate_text",
        AsyncMock(return_value="Hello world"),
    )
    save_artifact = AsyncMock(return_value="artifact-123")
    monkeypatch.setattr(
        "fichero_server.workflows.tools.translate.save_artifact",
        save_artifact,
    )
    monkeypatch.setattr(
        "fichero_server.workflows.tools.translate.save_to_file",
        AsyncMock(return_value=None),
    )

    state = {"library_path": "/tmp/lib.fichero", "task_id": "task-1"}
    inputs = {
        "text": "Hallo wereld",
        "source_lang": "nl",
        "target_lang": "en",
        "documents": [{"id": "doc-1", "path": "/tmp/a.txt"}],
        "save_to_db": True,
    }
    llm_config = LLMConfig(provider="deepl", model="deepl-default")

    result = await translate(inputs, state, llm_config)
    assert result["text"] == "Hello world"
    assert result["artifacts"] == ["artifact-123"]
    assert result["results"][0]["artifact_id"] == "artifact-123"
    save_artifact.assert_awaited_once()
