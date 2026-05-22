"""
Tests for builder edge robustness — legacy/broken workflow state must not
crash graph construction.

Scenario: a workflow persisted with an older edge schema (e.g., preset JSON
that used ``source_node_id`` before the UI decoder converged on ``source``)
deserializes with empty endpoints. Before this fix, build_graph crashed at
``node_names[edge.source]`` with KeyError(""). After: empty/invalid edges
are dropped with a warning and the remaining graph builds.
"""

from __future__ import annotations

import pytest

from fichero.workflows.builder import build_graph
from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef


def _files_only_workflow_with_bad_edges() -> WorkflowDef:
    """Files node + one edge with empty source/target + one valid self-loop-free edge."""
    return WorkflowDef(
        name="Legacy",
        nodes=[
            NodeDef(id="files", tool="files", config={}),
            NodeDef(id="transcribe", tool="transcribe", config={}),
        ],
        edges=[
            EdgeDef(source="", target="", source_port="output", target_port="input"),
            EdgeDef(source="files", target="transcribe", source_port="files", target_port="files"),
        ],
    )


def test_build_graph_drops_edges_with_empty_endpoints():
    """Empty-string endpoint edges are filtered out; the remaining graph builds."""
    workflow = _files_only_workflow_with_bad_edges()
    app = build_graph(workflow, enable_parallel=False)
    assert app is not None


def test_build_graph_drops_edges_referencing_unknown_nodes():
    """An edge pointing at a node ID that doesn't exist is dropped, not crashed on."""
    workflow = WorkflowDef(
        name="Dangling",
        nodes=[NodeDef(id="files", tool="files", config={})],
        edges=[
            EdgeDef(source="files", target="missing-node",
                    source_port="files", target_port="files"),
        ],
    )
    app = build_graph(workflow, enable_parallel=False)
    assert app is not None


@pytest.mark.asyncio
async def test_parallel_aggregate_auto_wires_downstream_inputs(monkeypatch):
    """#1166: nodes after a parallel transcribe aggregate receive text + records."""

    captured_extract_inputs: dict = {}

    async def files_tool(inputs, state, llm_config):
        return {
            "files": ["/tmp/page-1.jpg"],
            "documents": [{"id": "doc-1", "path": "/tmp/page-1.jpg"}],
            "count": 1,
        }

    async def transcribe_tool(inputs, state, llm_config):
        return {
            "text": "transcribed page text",
            "page_records": [{"doc_id": "doc-1", "text": "transcribed page text"}],
        }

    async def extract_all_tool(inputs, state, llm_config):
        captured_extract_inputs.update(inputs)
        return {"text": "extracted entities", "value": {}}

    tools = {
        "files": files_tool,
        "transcribe": transcribe_tool,
        "extract_all": extract_all_tool,
    }
    monkeypatch.setattr(
        "fichero.workflows.builder.get_tool",
        lambda tool_name: tools.get(tool_name),
    )

    workflow = WorkflowDef(
        name="Parallel Transcribe To Extract",
        nodes=[
            NodeDef(id="files-source", tool="files", config={}),
            NodeDef(id="transcribe", tool="transcribe", config={}),
            NodeDef(id="extract_all", tool="extract_all", config={}),
        ],
        edges=[
            EdgeDef(
                source="files-source",
                target="transcribe",
                source_port="files",
                target_port="files",
            ),
            EdgeDef(
                source="transcribe",
                target="extract_all",
                source_port="text",
                target_port="text",
            ),
            EdgeDef(
                source="transcribe",
                target="extract_all",
                source_port="records",
                target_port="records",
            ),
        ],
    )

    app = build_graph(workflow, enable_parallel=True)
    await app.ainvoke(
        {
            "workflow_id": "workflow-1",
            "library_path": "",
            "selected_doc_ids": ["doc-1"],
        }
    )

    assert captured_extract_inputs["text"] == "transcribed page text"
    assert captured_extract_inputs["records"] == [
        {"doc_id": "doc-1", "text": "transcribed page text"}
    ]
