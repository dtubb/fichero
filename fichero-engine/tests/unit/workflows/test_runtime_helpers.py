from __future__ import annotations

from types import SimpleNamespace

from fichero.workflows.runtime import apply_default_provider_model, to_workflow_def
from fichero.workflows.types import WorkflowDef


def test_to_workflow_def_accepts_object_style_nodes_and_edges():
    workflow = SimpleNamespace(
        id="wf-1",
        name="Runtime Test",
        nodes=[
            SimpleNamespace(
                id="n1",
                tool="transcribe",
                label="Node 1",
                inputs={"files": "$.nodes.files.files"},
                config={"language": "en"},
                provider_name="openai",
                model_name="gpt-5",
            )
        ],
        edges=[
            SimpleNamespace(
                source="n1",
                target="n2",
                source_port="text",
                target_port="context",
            )
        ],
    )

    wf_def = to_workflow_def(workflow)
    assert wf_def.id == "wf-1"
    assert wf_def.nodes[0].id == "n1"
    assert wf_def.nodes[0].provider_name == "openai"
    assert wf_def.edges[0].source == "n1"
    assert wf_def.edges[0].target_port == "context"


def test_to_workflow_def_accepts_camel_case_edge_aliases():
    workflow = SimpleNamespace(
        id="wf-2",
        name="Runtime Edge Alias Test",
        nodes=[
            {"id": "a", "tool": "transcribe"},
            {"id": "b", "tool": "summarize"},
        ],
        edges=[
            {
                "sourceNodeId": "a",
                "targetNodeId": "b",
                "sourcePort": "text",
                "targetPort": "context",
            }
        ],
    )

    wf_def = to_workflow_def(workflow)
    assert wf_def.edges[0].source == "a"
    assert wf_def.edges[0].target == "b"
    assert wf_def.edges[0].source_port == "text"
    assert wf_def.edges[0].target_port == "context"


def test_to_workflow_def_accepts_camel_case_node_provider_fields():
    workflow = SimpleNamespace(
        id="wf-3",
        name="Runtime Node Alias Test",
        nodes=[
            {
                "id": "n1",
                "tool": "transcribe",
                "providerName": "openai",
                "modelName": "gpt-5",
            }
        ],
        edges=[],
    )

    wf_def = to_workflow_def(workflow)
    assert wf_def.nodes[0].provider_name == "openai"
    assert wf_def.nodes[0].model_name == "gpt-5"


def test_apply_default_provider_model_leaves_node_workflows_unset(monkeypatch):
    workflow = WorkflowDef(
        id="wf-4",
        name="Transcribe",
        format="nodes",
        nodes=[{"id": "transcribe", "tool": "transcribe"}],
        edges=[],
        provider="",
        model="",
    )

    fake_db = SimpleNamespace(get_default_model=lambda: ("openrouter", "openai/gpt-4o-mini"))
    monkeypatch.setattr("fichero.app_db.get_app_db", lambda: fake_db)

    resolved = apply_default_provider_model(workflow)
    assert resolved.provider == ""
    assert resolved.model == ""


def test_apply_default_provider_model_backfills_non_node_workflows(monkeypatch):
    workflow = WorkflowDef(
        id="wf-5",
        name="Legacy",
        format="steps",
        provider="",
        model="",
    )

    fake_db = SimpleNamespace(get_default_model=lambda: ("openrouter", "openai/gpt-4o-mini"))
    monkeypatch.setattr("fichero.app_db.get_app_db", lambda: fake_db)

    resolved = apply_default_provider_model(workflow)
    assert resolved.provider == "openrouter"
    assert resolved.model == "openai/gpt-4o-mini"
