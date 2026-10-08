from __future__ import annotations

from types import SimpleNamespace

from fichero_server.llm import LLMConfig
from fichero_server.llm.model_profiles import ModelProfile, ModelProfileParams
from fichero_server.workflows.builder import _resolve_node_llm_config
from fichero_server.workflows.types import NodeDef


class _FakeAppDB:
    def __init__(self):
        self._cat_default = ("openai", "gpt-category")

    def get_default_model_for_category(self, _category: str):
        return self._cat_default

    def get_default_model(self):
        return None

    def list_providers(self):
        return []

    def list_models(self, _provider_id: str):
        return []


def test_workflow_default_beats_category_default_for_llm_node(monkeypatch):
    """Workflow-level model selection must override category defaults."""
    node = NodeDef(id="n1", tool="transcribe", config={})
    workflow_cfg = LLMConfig(provider="openai", model="gpt-workflow")

    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="vision"),
    )
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: _FakeAppDB())

    resolved = _resolve_node_llm_config(node, workflow_cfg)
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-workflow"


def test_category_default_applies_when_workflow_default_missing(monkeypatch):
    node = NodeDef(id="n1", tool="transcribe", config={})
    workflow_cfg = LLMConfig(provider="", model="")

    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="vision"),
    )
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: _FakeAppDB())

    resolved = _resolve_node_llm_config(node, workflow_cfg)
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-category"


def test_node_specific_aliases_resolve_before_other_fallbacks(monkeypatch):
    node = NodeDef(
        id="n1",
        tool="transcribe",
        provider_name="$medium",
        model_name="ignored-by-alias",
        config={},
    )
    workflow_cfg = LLMConfig(provider="workflow-provider", model="workflow-model")

    monkeypatch.setattr(
        "fichero_server.llm.resolve_model_alias_for_capability",
        lambda provider, model, *, required_capability: (
            "openrouter",
            "openai/gpt-4o-mini",
        ),
    )

    resolved = _resolve_node_llm_config(node, workflow_cfg)
    assert resolved.provider == "openrouter"
    assert resolved.model == "openai/gpt-4o-mini"


def test_node_profile_override_beats_alias_and_applies_params(monkeypatch):
    node = NodeDef(
        id="n1",
        tool="summarize_file",
        provider_name="$medium",
        model_name="ignored-by-profile",
        config={"model_profile_id": "fast-local"},
    )
    workflow_cfg = LLMConfig(
        provider="openai",
        model="gpt-workflow",
        temperature=0.7,
        max_tokens=2048,
        timeout=60,
    )
    profile = ModelProfile(
        id="fast-local",
        name="Fast Local",
        provider="ollama",
        model="llama3.2",
        role="text",
        local_only=True,
        params=ModelProfileParams(temperature=0.2, timeout=12),
    )
    fake_db = SimpleNamespace(
        get_model_profile=lambda profile_id: (
            profile if profile_id == "fast-local" else None
        ),
        get_model_profile_by_name=lambda _name: None,
        list_providers=lambda: [],
        list_models=lambda _provider_id: [],
    )
    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="llm"),
    )
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fake_db)

    resolved = _resolve_node_llm_config(node, workflow_cfg)

    assert resolved.provider == "ollama"
    assert resolved.model == "llama3.2"
    assert resolved.temperature == 0.2
    assert resolved.max_tokens == 2048
    assert resolved.timeout == 12


def test_workflow_profile_reference_resolves_before_category_default(monkeypatch):
    node = NodeDef(id="n1", tool="summarize_file", config={})
    workflow_cfg = LLMConfig(provider="$profile:best-local", model="")
    profile = ModelProfile(
        id="best-local",
        name="Best Local",
        provider="mock",
        model="mock",
        role="text",
        privacy="local_only",
    )
    fake_db = SimpleNamespace(
        get_model_profile=lambda profile_id: (
            profile if profile_id == "best-local" else None
        ),
        get_model_profile_by_name=lambda _name: None,
        get_default_model_for_category=lambda _category: ("openai", "gpt-category"),
        get_default_model=lambda: None,
        list_providers=lambda: [],
        list_models=lambda _provider_id: [],
    )
    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="llm"),
    )
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fake_db)

    resolved = _resolve_node_llm_config(node, workflow_cfg)

    assert resolved.provider == "mock"
    assert resolved.model == "mock"


def test_explicit_node_override_beats_configured_vision_slot(monkeypatch):
    node = NodeDef(
        id="n1",
        tool="transcribe",
        provider_name="openai",
        model_name="gpt-4o-mini",
        config={},
    )
    workflow_cfg = LLMConfig(provider="", model="")

    fake_db = SimpleNamespace(
        get_default_model_for_category=lambda _category: ("apple", "apple-vision"),
        get_default_model=lambda: ("openrouter", "openai/gpt-4o-mini"),
        list_providers=lambda: [],
        list_models=lambda _provider_id: [],
    )
    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="vision"),
    )
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fake_db)

    resolved = _resolve_node_llm_config(node, workflow_cfg)
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-4o-mini"


def test_generic_default_applies_when_category_default_missing(monkeypatch):
    node = NodeDef(id="n1", tool="transcribe", config={})
    workflow_cfg = LLMConfig(provider="", model="")

    fake_db = SimpleNamespace(
        get_default_model_for_category=lambda _category: None,
        get_default_model=lambda: ("anthropic", "claude-sonnet-4"),
        list_providers=lambda: [],
        list_models=lambda _provider_id: [],
    )
    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="vision"),
    )
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fake_db)

    resolved = _resolve_node_llm_config(node, workflow_cfg)
    assert resolved.provider == "anthropic"
    assert resolved.model == "claude-sonnet-4"


def test_transcribe_node_without_override_uses_vision_category_default(monkeypatch):
    node = NodeDef(id="n1", tool="transcribe", config={})
    workflow_cfg = LLMConfig(provider="", model="")

    fake_db = SimpleNamespace(
        get_default_model_for_category=lambda _category: ("apple", "apple-vision"),
        get_default_model=lambda: ("openrouter", "openai/gpt-4o-mini"),
        list_providers=lambda: [],
        list_models=lambda _provider_id: [],
    )
    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="vision"),
    )
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fake_db)

    resolved = _resolve_node_llm_config(node, workflow_cfg)
    assert resolved.provider == "apple"
    assert resolved.model == "apple-vision"


def test_no_model_anywhere_refuses_rather_than_take_the_first_provider(monkeypatch):
    """`ai.where.no-first-provider-fallback` (#5368): with no model on the node, the workflow or
    Settings, the node refuses, naming what to set. An enabled provider with a model (here a
    cloud one) is never picked for it; this used to be the last resort (#704, #2243)."""
    import pytest

    node = NodeDef(id="n1", tool="summarize", config={})
    workflow_cfg = LLMConfig(provider="", model="")

    providers = [
        SimpleNamespace(
            id="openai-provider",
            enabled=True,
            provider_type=SimpleNamespace(value="openai"),
            api_base=None,
        ),
    ]
    fake_db = SimpleNamespace(
        get_default_model_for_category=lambda _category: None,
        get_default_model=lambda: None,
        list_providers=lambda: providers,
        list_models=lambda _provider_id: [SimpleNamespace(model_id="gpt-4o-mini", enabled=True)],
    )
    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="text"),
    )
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fake_db)

    with pytest.raises(ValueError, match="No model is set for this step.*Settings > AI"):
        _resolve_node_llm_config(node, workflow_cfg)


def test_a_reader_that_calls_no_model_is_not_refused_for_lacking_one(monkeypatch):
    """`ai.where.no-first-provider-fallback` (#5368): only a step that calls a model is refused for having none.
    Transcribe set to Apple Vision, or to Kraken reading its own lines, runs with no model anywhere; Kraken
    with a vision model reading its lines and no Kraken reader still asks for one."""
    import pytest

    fake_db = SimpleNamespace(get_default_model_for_category=lambda _c: None, get_default_model=lambda: None)
    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: fake_db)
    workflow_cfg = LLMConfig(provider="", model="")
    for config in ({"vision_mode": "apple"}, {"vision_mode": "kraken", "kraken_model": "kraken-mccatmus"},
                   {"vision_mode": "kraken"}):
        assert _resolve_node_llm_config(NodeDef(id="n1", tool="transcribe", config=config), workflow_cfg) is workflow_cfg
    model_reads = NodeDef(id="n1", tool="transcribe", config={"vision_mode": "kraken", "lines_read_by": "model"})
    with pytest.raises(ValueError, match="No model is set for this step"):
        _resolve_node_llm_config(model_reads, workflow_cfg)


def test_non_llm_tool_keeps_workflow_config(monkeypatch):
    node = NodeDef(id="n1", tool="files", config={})
    workflow_cfg = LLMConfig(provider="openai", model="gpt-4o-mini")

    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=False, category="source"),
    )

    resolved = _resolve_node_llm_config(node, workflow_cfg)
    assert resolved is workflow_cfg
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-4o-mini"


def test_provider_lookup_failure_falls_back_to_workflow_config(monkeypatch):
    node = NodeDef(id="n1", tool="transcribe", config={})
    workflow_cfg = LLMConfig(provider="openai", model="gpt-workflow")

    monkeypatch.setattr(
        "fichero_server.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="vision"),
    )
    monkeypatch.setattr(
        "fichero_server.db.app.get_app_db",
        lambda: (_ for _ in ()).throw(RuntimeError("db unavailable")),
    )

    resolved = _resolve_node_llm_config(node, workflow_cfg)
    assert resolved is workflow_cfg
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-workflow"
