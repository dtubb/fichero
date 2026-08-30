"""Saved model ids that already carry the provider prefix must not double up
(Daniel's $vision_small report, 2026-08-27: stored
"openrouter/google/gemini-3.1-flash-lite" became
"openrouter/openrouter/google/…" on the wire and every call failed)."""

from __future__ import annotations

from fichero_server.llm import LLMConfig


def test_get_model_name_strips_existing_provider_prefix():
    config = LLMConfig(provider="openrouter", model="openrouter/google/gemini-3.1-flash-lite")
    assert config.get_model_name() == "openrouter/google/gemini-3.1-flash-lite"


def test_get_model_name_unprefixed_unchanged():
    config = LLMConfig(provider="openrouter", model="google/gemini-3.1-flash-lite")
    assert config.get_model_name() == "openrouter/google/gemini-3.1-flash-lite"


def test_ollama_alias_providers_do_not_double_prefix():
    config = LLMConfig(provider="lmstudio", model="ollama/llama3.2")
    assert config.get_model_name() == "ollama/llama3.2"
