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


def test_deepl_default_base_routes_pro_and_free_keys():
    """DeepL free keys (":fx" suffix) live on api-free; pro keys on api.deepl.com.

    The free host was the unconditional default, so a valid PRO key 403'd
    every Translate (DeepL) run (found live 2026-09-03).
    """
    from fichero_server.llm import _deepl_default_base

    assert _deepl_default_base("abcd-1234:fx") == "https://api-free.deepl.com"
    assert _deepl_default_base("abcd-1234:fx ") == "https://api-free.deepl.com"
    assert _deepl_default_base("abcd-1234-5678") == "https://api.deepl.com"


# =============================================================================
# DeepL as a first-class provider (Daniel, 2026-09-03): the key is entered in
# Settings > AI > Providers like every other provider key. The environment
# variable survives only as a fallback so existing setups keep working.
# =============================================================================


@pytest.fixture
def _clean_deepl_key(monkeypatch):
    """Isolate DeepL key resolution: no keychain, no cache, no leaked supply."""
    from fichero_server.llm import clear_api_key_cache
    from fichero_server.security import provider_keys as supply

    monkeypatch.setattr(
        "fichero_server.security.keychain.get_api_key", lambda provider: None
    )
    supply.forget_api_key("deepl")
    clear_api_key_cache()
    yield
    supply.forget_api_key("deepl")
    clear_api_key_cache()


def test_deepl_key_from_settings_wins_over_environment(monkeypatch, _clean_deepl_key):
    """A key supplied by the app (Settings' provider screen) outranks the env."""
    from fichero_server.llm import clear_api_key_cache, get_api_key
    from fichero_server.security import provider_keys as supply

    monkeypatch.setenv("DEEPL_API_KEY", "env-key:fx")
    supply.supply_api_key("deepl", "settings-key")
    clear_api_key_cache()

    assert get_api_key("deepl") == "settings-key"


def test_deepl_key_falls_back_to_environment(monkeypatch, _clean_deepl_key):
    """No key in Settings yet -> DEEPL_API_KEY still works (existing setups)."""
    from fichero_server.llm import clear_api_key_cache, get_api_key

    monkeypatch.setenv("DEEPL_API_KEY", "env-key:fx")
    clear_api_key_cache()

    assert get_api_key("deepl") == "env-key:fx"


def test_deepl_capability_is_translation_not_text():
    """A translation engine must not land in the text/vision model pickers:
    the tier vocabulary they filter on has no 'translation' entry, and the
    unknown-model floor would otherwise save deepl-default as 'text'.
    """
    from fichero_server.api.routes.ai.providers import (
        _derive_capabilities_from_registry,
    )

    assert _derive_capabilities_from_registry("deepl", "deepl-default") == [
        "translation"
    ]


@pytest.mark.asyncio
async def test_deepl_model_catalog_offers_the_translate_engine():
    """DeepL publishes no /models endpoint and the vendored LiteLLM snapshot
    has never heard of it, so without an explicit branch Settings offers an
    EMPTY model list and the provider cannot be finished (and the key never
    stored)."""
    from fichero_server.api.routes.ai.provider_models import list_models_for_provider

    response = await list_models_for_provider(
        "deepl", search=None, vision_only=False, sort_by="name"
    )

    assert response.count == 1
    model = response.items[0]
    assert model.model_id == "deepl-default"
    assert model.mode == "translation"
    # Billed per character — a per-token number here would be a lie.
    assert model.input_cost_per_million is None
    assert model.output_cost_per_million is None
