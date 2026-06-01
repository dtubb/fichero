from __future__ import annotations

from types import SimpleNamespace

from fichero.workflows.runtime import to_workflow_def


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
