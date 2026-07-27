from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fichero.llm import LLMConfig, resolve_model_alias_for_capability
from fichero.llm.model_profiles import ModelProfile
from fichero.workflows.types import NodeDef, WorkflowDef
from fichero.workflows.validation import (
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
        "fichero.db.app.get_app_db",
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
        "fichero.db.app.get_app_db",
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
        "fichero.db.app.get_app_db",
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
        "fichero.db.app.get_app_db",
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
        "fichero.db.app.get_app_db",
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
        "fichero.db.app.get_app_db",
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
        "fichero.db.app.get_app_db",
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
    monkeypatch.setattr("fichero.db.app.get_app_db", lambda: fake_db)
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


def test_spanish_script_subworkflow_parent_is_valid_and_passes_preflight(monkeypatch):
    # The flat multipass preset was retired in #2251 and merged into the
    # subworkflow + child pair.  This test now validates the user-facing parent
    # preset ("Transcribe Spanish Script (19th-20th C.)") which delegates
    # transcription to the child via a sub_workflow node.  Vision-tier alias
    # resolution is tested separately in
    # test_spanish_script_v2_child_resolves_distinct_vision_tiers.
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero.db.app.get_app_db",
        lambda: _fake_db(
            category_defaults={"vision": ("apple", "apple-vision")},
            models_by_provider={"apple": [_model("apple-vision", ["vision"])]},
        ),
    )
    path = (
        Path(__file__).parents[3]
        / "src/fichero/resources/default_workflows/transcribe_spanish_script_v2_subworkflow.json"
    )
    data = json.loads(path.read_text())
    workflow = WorkflowDef(**data)

    # The parent delegates via a sub_workflow node — no direct transcribe nodes.
    sub_nodes = [node for node in workflow.nodes if node.tool == "sub_workflow"]
    assert sub_nodes, "parent preset must have at least one sub_workflow node"
    assert any(
        "Spanish Script" in node.config.get("workflow_ref", "")
        for node in sub_nodes
    ), "sub_workflow node must reference the Spanish Script child"

    assert validate_workflow_preflight(
        workflow,
        LLMConfig(provider="", model=""),
    ) == []


def test_spanish_script_v2_child_resolves_distinct_vision_tiers(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero.db.app.get_app_db",
        lambda: _fake_db(
            settings={
                "default_vision_small_provider": "apple",
                "default_vision_small_model": "apple-vision-small",
                "default_vision_medium_provider": "apple",
                "default_vision_medium_model": "apple-vision-medium",
                "default_vision_large_provider": "mlx",
                "default_vision_large_model": "local-vision-large",
            },
            models_by_provider={
                "apple": [
                    _model("apple-vision-small", ["vision"]),
                    _model("apple-vision-medium", ["vision"]),
                ],
                "mlx": [_model("local-vision-large", ["vision"])],
            },
        ),
    )
    path = (
        Path(__file__).parents[3]
        / "src/fichero/resources/default_workflows/transcribe_spanish_script_v2_child.json"
    )
    workflow = WorkflowDef(**json.loads(path.read_text()))
    node_aliases = {
        node.id: node.config.get("provider_name")
        for node in workflow.nodes
        if node.tool in {"transcribe", "transcribe_review"}
    }

    assert node_aliases == {
        "transcribe-draft": "$vision_small",
        "transcribe-review-medium": "$vision_medium",
        "transcribe-final-large": "$vision_large",
    }
    assert resolve_model_alias_for_capability(
        "$vision_small",
        "",
        required_capability="vision",
    ) == ("apple", "apple-vision-small")
    assert resolve_model_alias_for_capability(
        "$vision_medium",
        "",
        required_capability="vision",
    ) == ("apple", "apple-vision-medium")
    assert resolve_model_alias_for_capability(
        "$vision_large",
        "",
        required_capability="vision",
    ) == ("mlx", "local-vision-large")
    assert validate_workflow_preflight(
        workflow,
        LLMConfig(provider="", model=""),
    ) == []


def test_paleography_ensemble_without_optional_translation_passes_preflight(monkeypatch):
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)
    monkeypatch.setattr(
        "fichero.db.app.get_app_db",
        lambda: _fake_db(
            settings={
                "default_vision_small_provider": "apple",
                "default_vision_small_model": "apple-vision-small",
                "default_vision_medium_provider": "apple",
                "default_vision_medium_model": "apple-vision-medium",
                "default_vision_large_provider": "apple",
                "default_vision_large_model": "apple-vision-large",
                "default_small_provider": "apple",
                "default_small_model": "apple-text-small",
                "default_medium_provider": "apple",
                "default_medium_model": "apple-text-medium",
                "default_large_provider": "apple",
                "default_large_model": "apple-text-large",
            },
            models_by_provider={
                "apple": [
                    _model("apple-vision-small", ["vision"]),
                    _model("apple-vision-medium", ["vision"]),
                    _model("apple-vision-large", ["vision"]),
                    _model("apple-text-small", ["text"]),
                    _model("apple-text-medium", ["text"]),
                    _model("apple-text-large", ["text"]),
                ],
            },
        ),
    )
    path = (
        Path(__file__).parents[3]
        / "src/fichero/resources/default_workflows/transcribe_paleography_ensemble.json"
    )
    data = json.loads(path.read_text())
    # WorkflowDef.version is a str; the shipped preset stores it as an int
    # (coerced on the seeding path). Mirror that coercion for direct loads.
    if "version" in data:
        data["version"] = str(data["version"])
    workflow = WorkflowDef(**data)

    assert all(node.tool != "translate" for node in workflow.nodes)

    assert validate_workflow_preflight(
        workflow,
        LLMConfig(provider="", model=""),
    ) == []


def test_spanish_script_v2_child_rejects_cloud_vision_tier_under_local_only(monkeypatch):
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")
    monkeypatch.setattr(
        "fichero.db.app.get_app_db",
        lambda: _fake_db(
            settings={
                "default_vision_small_provider": "apple",
                "default_vision_small_model": "apple-vision-small",
                "default_vision_medium_provider": "apple",
                "default_vision_medium_model": "apple-vision-medium",
                "default_vision_large_provider": "openai",
                "default_vision_large_model": "gpt-4o",
            },
            models_by_provider={
                "apple": [
                    _model("apple-vision-small", ["vision"]),
                    _model("apple-vision-medium", ["vision"]),
                ],
                "openai": [_model("gpt-4o", ["vision"])],
            },
        ),
    )
    path = (
        Path(__file__).parents[3]
        / "src/fichero/resources/default_workflows/transcribe_spanish_script_v2_child.json"
    )
    workflow = WorkflowDef(**json.loads(path.read_text()))

    errors = validate_workflow_preflight(
        workflow,
        LLMConfig(provider="", model=""),
    )

    assert len(errors) == 1
    assert "Final Reconcile" in errors[0]
    assert "Local-only AI mode is enabled" in errors[0]
    assert "openai/gpt-4o" in errors[0]
