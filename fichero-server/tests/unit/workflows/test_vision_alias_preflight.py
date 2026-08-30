from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fichero_server.llm import LLMConfig, resolve_model_alias_for_capability
from fichero_server.llm.model_profiles import ModelProfile
from fichero_server.workflows.types import NodeDef, WorkflowDef
from fichero_server.workflows.validation import (
    validate_workflow_llm_preflight,
    validate_workflow_preflight,
)


def _workflow_for(node: NodeDef) -> WorkflowDef:
    return WorkflowDef(id="wf", name="Workflow", nodes=[node], edges=[])


def _provider(provider_type: str, provider_id: str | None = None):
    return SimpleNamespace(
        id=provider_id or f"{provider_type}-provider",
        enabled=True,
        provider_type=SimpleNamespace(value=provider_type),
    )


def _model(model_id: str, capabilities: list[str]):
    return SimpleNamespace(model_id=model_id, capabilities=capabilities, enabled=True)


def _fake_db(*, settings=None, category_defaults=None, models_by_provider=None):
    settings = settings or {}
    category_defaults = category_defaults or {}
    models_by_provider = models_by_provider or {}
    providers = [_provider(provider_type) for provider_type in models_by_provider]

    return SimpleNamespace(
        get_setting=lambda key: settings.get(key),
        get_default_model_for_category=lambda category: category_defaults.get(category),
        list_providers=lambda: providers,
        list_models=lambda provider_id: models_by_provider.get(
            provider_id.removesuffix("-provider"), []
        ),
    )


def test_vision_small_resolves_from_env_without_provider_call(monkeypatch):
    monkeypatch.setenv("FICHERO_VISION_SMALL_PROVIDER", "apple")
    monkeypatch.setenv("FICHERO_VISION_SMALL_MODEL", "apple-vision")
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _fake_db(models_by_provider={"apple": [_model("apple-vision", ["vision"])]}),
    )
    node = NodeDef(id="vision", tool="transcribe", provider_name="$vision_small")

    errors = validate_workflow_llm_preflight(
        _workflow_for(node),
        LLMConfig(provider="", model=""),
    )

    assert errors == []


def test_vision_small_resolves_from_app_settings(monkeypatch):
    monkeypatch.delenv("FICHERO_VISION_SMALL_PROVIDER", raising=False)
    monkeypatch.delenv("FICHERO_VISION_SMALL_MODEL", raising=False)
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _fake_db(
            settings={
                "default_vision_small_provider": "apple",
                "default_vision_small_model": "apple-vision",
            },
            models_by_provider={"apple": [_model("apple-vision", ["vision"])]},
        ),
    )
    node = NodeDef(id="vision", tool="transcribe", provider_name="$vision_small")

    errors = validate_workflow_llm_preflight(
        _workflow_for(node),
        LLMConfig(provider="", model=""),
    )

    assert errors == []


def test_text_alias_on_vision_node_fails_preflight(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    node = NodeDef(id="vision", tool="transcribe", provider_name="$small")

    errors = validate_workflow_llm_preflight(
        _workflow_for(node),
        LLMConfig(provider="", model=""),
    )

    assert len(errors) == 1
    assert "$small is a text-tier model alias" in errors[0]
    assert "$vision_small" in errors[0]


def test_vision_alias_on_text_llm_node_fails_preflight(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    node = NodeDef(id="text", tool="summarize_file", provider_name="$vision_small")

    errors = validate_workflow_llm_preflight(
        _workflow_for(node),
        LLMConfig(provider="", model=""),
    )

    assert len(errors) == 1
    assert "$vision_small is a vision-tier model alias" in errors[0]
    assert "$small" in errors[0]


def test_vision_alias_on_audio_llm_node_fails_preflight(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    node = NodeDef(id="audio", tool="audio_transcribe", provider_name="$vision_small")

    errors = validate_workflow_llm_preflight(
        _workflow_for(node),
        LLMConfig(provider="", model=""),
    )

    assert len(errors) == 1
    assert "$vision_small is a vision-tier model alias" in errors[0]
    assert "audio workflow nodes" in errors[0]


def test_audio_capable_saved_model_satisfies_audio_node(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _fake_db(
            models_by_provider={"apple": [_model("apple-speech", ["audio"])]},
        ),
    )
    node = NodeDef(
        id="audio",
        tool="audio_transcribe",
        provider_name="apple",
        model_name="apple-speech",
    )

    errors = validate_workflow_llm_preflight(_workflow_for(node))

    assert errors == []


def test_video_capable_saved_model_satisfies_video_node(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _fake_db(
            models_by_provider={"apple": [_model("apple-video", ["video"])]},
        ),
    )
    node = NodeDef(
        id="video",
        tool="video_describe",
        provider_name="apple",
        model_name="apple-video",
    )

    errors = validate_workflow_llm_preflight(_workflow_for(node))

    assert errors == []


def test_text_only_saved_model_cannot_satisfy_audio_node(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _fake_db(
            models_by_provider={"openai": [_model("gpt-4.1-mini", ["text"])]},
        ),
    )
    node = NodeDef(
        id="audio",
        tool="audio_transcribe",
        provider_name="openai",
        model_name="gpt-4.1-mini",
    )

    errors = validate_workflow_llm_preflight(_workflow_for(node))

    assert len(errors) == 1
    assert "not marked as audio-capable" in errors[0]


def test_text_only_provider_cannot_satisfy_vision_node(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    node = NodeDef(
        id="vision",
        tool="transcribe",
        provider_name="deepseek",
        model_name="deepseek-chat",
    )

    errors = validate_workflow_llm_preflight(_workflow_for(node))

    assert len(errors) == 1
    assert "does not support vision" in errors[0]


def test_text_only_saved_model_cannot_satisfy_vision_node(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _fake_db(
            models_by_provider={"openai": [_model("gpt-4.1-mini", ["text"])]},
        ),
    )
    node = NodeDef(
        id="vision",
        tool="transcribe",
        provider_name="openai",
        model_name="gpt-4.1-mini",
    )

    errors = validate_workflow_llm_preflight(_workflow_for(node))

    assert len(errors) == 1
    assert "not marked as vision-capable" in errors[0]


def test_vision_large_cloud_provider_rejected_under_local_only(monkeypatch):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _fake_db(
            settings={
                "default_vision_large_provider": "openai",
                "default_vision_large_model": "gpt-4o",
            },
            models_by_provider={"openai": [_model("gpt-4o", ["vision"])]},
        ),
    )
    node = NodeDef(id="vision", tool="transcribe", provider_name="$vision_large")

    errors = validate_workflow_llm_preflight(
        _workflow_for(node),
        LLMConfig(provider="", model=""),
    )

    assert len(errors) == 1
    assert "Local-only AI mode is enabled" in errors[0]
    assert "openai/gpt-4o" in errors[0]


def test_private_model_profile_rejects_cloud_provider_in_preflight(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    profile = ModelProfile(
        id="private-cloud",
        name="Private Cloud",
        provider="openai",
        model="gpt-4o-mini",
        role="text",
        privacy="private",
    )
    fake_db = _fake_db()
    fake_db.get_model_profile = lambda profile_id: (
        profile if profile_id == "private-cloud" else None
    )
    fake_db.get_model_profile_by_name = lambda _name: None
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fake_db)
    node = NodeDef(
        id="text",
        tool="summarize_file",
        config={"model_profile_id": "private-cloud"},
    )

    errors = validate_workflow_llm_preflight(
        _workflow_for(node),
        LLMConfig(provider="", model=""),
    )

    assert len(errors) == 1
    assert "refusing cloud provider openai/gpt-4o-mini" in errors[0]
    assert "Private Cloud" in errors[0]


def test_paleography_review_preset_is_single_model_and_passes_preflight(monkeypatch):
    """The 2026-08-26 redesign: Paleographer Review replaces the ensemble.
    Single model per run (no provider_name/$vision_* aliases anywhere — the
    user picks the model at run time), so preflight must pass with only a
    plain vision default configured."""
    import json
    from pathlib import Path

    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: _fake_db(
            settings={
                "default_vision_provider": "apple",
                "default_vision_model": "apple-vision",
            }
        ),
    )

    preset_path = (
        Path(__file__).resolve().parents[3]
        / "src/fichero_server/resources/default_workflows/transcribe_paleography_review.json"
    )
    preset = json.loads(preset_path.read_text())

    for node in preset["nodes"]:
        assert "provider_name" not in node.get("config", {}), (
            f"node {node['id']} pins a provider — the redesign forbids it"
        )

    from fichero_server.workflows.validation import validate_workflow_llm_preflight

    workflow = WorkflowDef(
        id="paleographer-review", name=preset["name"],
        nodes=[NodeDef(**n) for n in preset["nodes"]],
        edges=preset["edges"],
    )
    errors = validate_workflow_llm_preflight(
        workflow, LLMConfig(provider="", model="")
    )
    assert errors == [], errors
