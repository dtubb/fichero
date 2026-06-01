from __future__ import annotations

from types import SimpleNamespace

from fichero.llm import LLMConfig
from fichero.workflows.builder import _resolve_node_llm_config
from fichero.workflows.types import NodeDef


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
        "fichero.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="vision"),
    )
    monkeypatch.setattr("fichero.app_db.get_app_db", lambda: _FakeAppDB())

    resolved = _resolve_node_llm_config(node, workflow_cfg)
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-workflow"


def test_category_default_applies_when_workflow_default_missing(monkeypatch):
    node = NodeDef(id="n1", tool="transcribe", config={})
    workflow_cfg = LLMConfig(provider="", model="")

    monkeypatch.setattr(
        "fichero.workflows.builder.get_tool_def",
        lambda _tool: SimpleNamespace(uses_llm=True, category="vision"),
    )
    monkeypatch.setattr("fichero.app_db.get_app_db", lambda: _FakeAppDB())

    resolved = _resolve_node_llm_config(node, workflow_cfg)
    assert resolved.provider == "openai"
    assert resolved.model == "gpt-category"
