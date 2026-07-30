"""#4325(b): preflight checks credential PRESENCE per resolved provider.

A missing API key must be a pre-run preflight message that names the provider,
never a node-construction crash mid-run. Local/built-in providers (apple,
mock, ollama, lmstudio, omlx) and unknown/custom provider names are never
gated.
"""

from __future__ import annotations

from types import SimpleNamespace

from fichero_server.llm import LLMConfig
from fichero_server.workflows.types import NodeDef, WorkflowDef
from fichero_server.workflows.validation import validate_workflow_llm_preflight


def _workflow_for(node: NodeDef) -> WorkflowDef:
    return WorkflowDef(id="wf", name="Workflow", nodes=[node], edges=[])


def _provider(provider_type: str):
    return SimpleNamespace(
        id=f"{provider_type}-provider",
        enabled=True,
        provider_type=SimpleNamespace(value=provider_type),
    )


def _model(model_id: str, capabilities: list[str]):
    return SimpleNamespace(model_id=model_id, capabilities=capabilities, enabled=True)


def _fake_db(models_by_provider=None):
    models_by_provider = models_by_provider or {}
    providers = [_provider(provider_type) for provider_type in models_by_provider]
    return SimpleNamespace(
        get_setting=lambda key: None,
        get_default_model_for_category=lambda category: None,
        list_providers=lambda: providers,
        list_models=lambda provider_id: models_by_provider.get(
            provider_id.removesuffix("-provider"), []
        ),
    )


def _common_env(monkeypatch, *, api_key):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _fake_db(
            models_by_provider={
                "openai": [_model("gpt-5", ["text", "vision"])],
                "apple": [_model("apple-intelligence", ["text"])],
            }
        ),
    )
    monkeypatch.setattr("fichero_server.llm.get_api_key", lambda provider: api_key)


def test_missing_key_fails_preflight_naming_the_provider(monkeypatch):
    _common_env(monkeypatch, api_key=None)
    node = NodeDef(
        id="summarize",
        tool="summarize_file",
        provider_name="openai",
        model_name="gpt-5",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert len(errors) == 1
    assert "OpenAI" in errors[0]
    assert "API key" in errors[0]
    assert "summarize" in errors[0]


def test_present_key_passes_preflight(monkeypatch):
    _common_env(monkeypatch, api_key="sk-test")
    node = NodeDef(
        id="summarize",
        tool="summarize_file",
        provider_name="openai",
        model_name="gpt-5",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert errors == []


def test_on_device_provider_never_requires_a_key(monkeypatch):
    _common_env(monkeypatch, api_key=None)
    node = NodeDef(
        id="summarize",
        tool="summarize_file",
        provider_name="apple",
        model_name="apple-intelligence",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert errors == []


def test_unknown_custom_provider_is_not_gated(monkeypatch):
    """Custom/off-catalog provider names (e.g. a self-hosted OpenAI-compatible
    endpoint) are not credential-gated — presence can't be known here."""
    _common_env(monkeypatch, api_key=None)
    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias_for_capability",
        lambda provider, model, required_capability=None: (provider, model),
    )
    node = NodeDef(
        id="summarize",
        tool="summarize_file",
        provider_name="my-custom-endpoint",
        model_name="whatever",
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="", model="")
    )

    assert errors == []


def test_keyless_fresh_install_passes_preflight_for_every_default_workflow(
    monkeypatch,
):
    """#4325 acceptance: zero API keys + factory AI defaults → every shipped
    default workflow passes LLM preflight (tier aliases resolve on-device)."""
    from fichero_server.db.app import FACTORY_AI_DEFAULTS
    from fichero_server.workflows.default_workflows import _load_preset_files
    from fichero_server.workflows.runtime import to_workflow_def
    from fichero_server.models import Workflow

    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    for tier in ("small", "medium", "large", "vision_small", "vision_medium", "vision_large"):
        monkeypatch.delenv(f"FICHERO_{tier.upper()}_PROVIDER", raising=False)
        monkeypatch.delenv(f"FICHERO_{tier.upper()}_MODEL", raising=False)
    fresh_db = SimpleNamespace(
        get_setting=lambda key: FACTORY_AI_DEFAULTS.get(key),
        get_default_model_for_category=lambda category: None,
        list_providers=lambda: [_provider("apple")],
        list_models=lambda provider_id: [
            _model("apple-intelligence", ["text"]),
            _model("apple-vision", ["vision"]),
            _model("apple-speech", ["audio", "transcription"]),
        ],
    )
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fresh_db)
    monkeypatch.setattr("fichero_server.llm.get_api_key", lambda provider: None)

    # The ONLY preset allowed to fail keyless preflight: Translate (DeepL)
    # exists specifically to use the DeepL cloud API — keyless, it must fail
    # AT PREFLIGHT with the provider named (the second #4325 acceptance
    # criterion), not mid-run.
    keyed_presets = {"Translate (DeepL)"}

    failures: dict[str, list[str]] = {}
    for preset in _load_preset_files():
        workflow = to_workflow_def(
            Workflow(
                id=f"keyless-{preset['name']}",
                name=preset["name"],
                nodes=preset.get("nodes", []),
                edges=preset.get("edges", []),
                config=preset.get("config", {}),
            )
        )
        errors = validate_workflow_llm_preflight(
            workflow, LLMConfig(provider="", model="")
        )
        if preset["name"] in keyed_presets:
            assert errors, f"{preset['name']}: expected keyless preflight failure"
            assert any("DeepL" in e and "API key" in e for e in errors), errors
        elif errors:
            failures[preset["name"]] = errors

    assert not failures, failures


def test_workflow_level_cloud_default_is_gated_too(monkeypatch):
    """Nodes inheriting the workflow-level provider/model get the same check."""
    _common_env(monkeypatch, api_key=None)
    node = NodeDef(id="summarize", tool="summarize_file")

    errors = validate_workflow_llm_preflight(
        _workflow_for(node), LLMConfig(provider="openai", model="gpt-5")
    )

    assert len(errors) == 1
    assert "OpenAI" in errors[0]
