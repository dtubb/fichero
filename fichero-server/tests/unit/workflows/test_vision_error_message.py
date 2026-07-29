"""Vision-capability failure messages name the node and suggest a fix (#4187).

The report described hitting a bare "Model apple/apple-intelligence is not marked as
vision-capable" from a run — no clue which node failed or what to pick
instead. The preflight path (validation.py) already prefixed the node label;
the build-graph path (builder._resolve_node_llm_config) did not. These tests
pin both halves of the message fix: node context on the build-graph path,
and honest suggestions (configured + enabled + vision-capable only).

Message-only — the tri-state validation rule itself is untouched and stays
pinned by test_vision_alias_preflight.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.llm import LLMConfig, validate_model_capability
from fichero_server.workflows.builder import _resolve_node_llm_config
from fichero_server.workflows.types import NodeDef


def _provider(provider_type: str, enabled: bool = True):
    return SimpleNamespace(
        id=f"{provider_type}-provider",
        enabled=enabled,
        provider_type=SimpleNamespace(value=provider_type),
    )


def _model(model_id: str, capabilities: list[str], enabled: bool = True):
    return SimpleNamespace(model_id=model_id, capabilities=capabilities, enabled=enabled)


def _fake_db(models_by_provider):
    providers = [_provider(provider_type) for provider_type in models_by_provider]
    return SimpleNamespace(
        get_setting=lambda key: None,
        get_default_model_for_category=lambda category: None,
        list_providers=lambda: providers,
        list_models=lambda provider_id: models_by_provider.get(
            provider_id.removesuffix("-provider"), []
        ),
    )


def _patch_db(monkeypatch, models_by_provider):
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db", lambda: _fake_db(models_by_provider)
    )


# ---------------------------------------------------------------------------
# Suggestions in validate_model_capability
# ---------------------------------------------------------------------------


def test_vision_failure_suggests_configured_vision_models(monkeypatch):
    _patch_db(
        monkeypatch,
        {
            "openai": [
                _model("gpt-4.1-mini", ["text"]),
                _model("gpt-4o", ["vision"]),
            ],
        },
    )

    with pytest.raises(ValueError) as excinfo:
        validate_model_capability(
            "openai", "gpt-4.1-mini", required_capability="vision"
        )

    message = str(excinfo.value)
    assert "not marked as vision-capable" in message
    assert "openai/gpt-4o" in message
    # The failing model must not be suggested back.
    assert "Configured vision-capable models" in message
    assert message.count("gpt-4.1-mini") == 1


def test_vision_suggestion_inherits_provider_capability_for_blank_rows(monkeypatch):
    # Tri-state parity: a model with NO saved capabilities inherits its
    # provider's catalog vision support, so it IS a valid suggestion.
    _patch_db(
        monkeypatch,
        {
            "openai": [_model("gpt-4.1-mini", ["text"])],
            "openrouter": [_model("openai/gpt-4o", [])],
        },
    )

    with pytest.raises(ValueError) as excinfo:
        validate_model_capability(
            "openai", "gpt-4.1-mini", required_capability="vision"
        )

    assert "openrouter/openai/gpt-4o" in str(excinfo.value)


def test_vision_failure_with_no_configured_option_says_so(monkeypatch):
    _patch_db(monkeypatch, {"openai": [_model("gpt-4.1-mini", ["text"])]})

    with pytest.raises(ValueError) as excinfo:
        validate_model_capability(
            "openai", "gpt-4.1-mini", required_capability="vision"
        )

    message = str(excinfo.value)
    assert "No configured model is marked vision-capable" in message
    assert "Settings" in message


def test_disabled_rows_are_never_suggested(monkeypatch):
    _patch_db(
        monkeypatch,
        {
            "openai": [
                _model("gpt-4.1-mini", ["text"]),
                _model("gpt-4o", ["vision"], enabled=False),
            ],
        },
    )

    with pytest.raises(ValueError) as excinfo:
        validate_model_capability(
            "openai", "gpt-4.1-mini", required_capability="vision"
        )

    assert "No configured model is marked vision-capable" in str(excinfo.value)


def test_text_capability_failure_gets_no_vision_suggestions(monkeypatch):
    # The suggestion block is vision-only; text failures keep the base
    # message unchanged.
    _patch_db(monkeypatch, {"openai": [_model("vision-only", ["vision"])]})

    with pytest.raises(ValueError) as excinfo:
        validate_model_capability("openai", "vision-only", required_capability="text")

    message = str(excinfo.value)
    assert "not marked as text-capable" in message
    assert "Configured vision-capable" not in message


# ---------------------------------------------------------------------------
# Node context on the build-graph path
# ---------------------------------------------------------------------------


def test_build_graph_resolution_error_names_node_and_tool(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    _patch_db(monkeypatch, {"openai": [_model("gpt-4.1-mini", ["text"])]})
    node = NodeDef(
        id="vision-1",
        tool="transcribe",
        label="Transcribe pages",
        provider_name="openai",
        model_name="gpt-4.1-mini",
    )

    with pytest.raises(ValueError) as excinfo:
        _resolve_node_llm_config(node, LLMConfig(provider="", model=""))

    message = str(excinfo.value)
    assert message.startswith("Node 'Transcribe pages' (transcribe):")
    assert "not marked as vision-capable" in message


def test_build_graph_node_context_falls_back_to_id_then_tool(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    _patch_db(monkeypatch, {"openai": [_model("gpt-4.1-mini", ["text"])]})
    node = NodeDef(
        id="vision-1",
        tool="transcribe",
        provider_name="openai",
        model_name="gpt-4.1-mini",
    )

    with pytest.raises(ValueError) as excinfo:
        _resolve_node_llm_config(node, LLMConfig(provider="", model=""))

    assert str(excinfo.value).startswith("Node 'vision-1' (transcribe):")
