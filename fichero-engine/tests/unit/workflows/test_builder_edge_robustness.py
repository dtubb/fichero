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

from fichero.workflows.builder import build_graph, _make_node_function, SystemicErrorDetected
from fichero.llm import LLMConfig
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


def test_build_graph_handles_route_map_edge():
    """A route_map edge (no single target) builds without crashing."""
    workflow = WorkflowDef(
        name="RouteTest",
        nodes=[
            NodeDef(id="files", tool="files", config={}),
            NodeDef(id="classify", tool="classify_script", config={}),
            NodeDef(id="transcribe-ts", tool="transcribe", config={}),
            NodeDef(id="transcribe-ms", tool="transcribe", config={}),
        ],
        edges=[
            EdgeDef(source="files", target="classify", source_port="files", target_port="files"),
            EdgeDef(
                source="classify",
                target="",
                route_key="$.nodes.classify.script_type",
                route_map={"typescript": "transcribe-ts", "manuscript": "transcribe-ms"},
            ),
        ],
    )
    app = build_graph(workflow, enable_parallel=False)
    assert app is not None


def test_route_map_entry_nodes_excludes_branch_targets():
    """Nodes reachable only via route_map must not be detected as entry nodes
    (which would connect them directly to START and run all branches)."""
    from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef

    workflow = WorkflowDef(
        name="RouteEntryTest",
        nodes=[
            NodeDef(id="files", tool="files", config={}),
            NodeDef(id="classify", tool="classify_script", config={}),
            NodeDef(id="transcribe-ts", tool="transcribe", config={}),
            NodeDef(id="transcribe-ms", tool="transcribe", config={}),
        ],
        edges=[
            EdgeDef(source="files", target="classify", source_port="files", target_port="files"),
            EdgeDef(
                source="classify",
                target="",
                route_key="$.nodes.classify.script_type",
                route_map={"typescript": "transcribe-ts", "manuscript": "transcribe-ms"},
            ),
        ],
    )
    entry_nodes = workflow.get_entry_nodes()
    # Only files-source should be an entry node; classify is wired from files,
    # transcribe-ts/ms are wired via route_map.
    assert "files" in entry_nodes
    assert "classify" not in entry_nodes
    assert "transcribe-ts" not in entry_nodes
    assert "transcribe-ms" not in entry_nodes


def test_route_map_invalid_target_skipped():
    """A route_map edge whose targets are not in the node list is filtered out."""
    workflow = WorkflowDef(
        name="RouteBadTarget",
        nodes=[
            NodeDef(id="files", tool="files", config={}),
            NodeDef(id="classify", tool="classify_script", config={}),
        ],
        edges=[
            EdgeDef(source="files", target="classify", source_port="files", target_port="files"),
            EdgeDef(
                source="classify",
                target="",
                route_key="$.nodes.classify.script_type",
                route_map={"typescript": "nonexistent-node"},
            ),
        ],
    )
    # Should build without crashing; the bad route_map edge is dropped.
    app = build_graph(workflow, enable_parallel=False)
    assert app is not None


@pytest.mark.asyncio
async def test_route_map_unknown_value_falls_back_to_first_branch(monkeypatch):
    """Unknown route values must not stall the workflow; they follow the first route_map branch."""

    branch_calls: list[str] = []

    async def files_tool(inputs, state, llm_config):
        return {"files": ["/tmp/doc.txt"], "documents": [{"id": "doc-1", "path": "/tmp/doc.txt"}]}

    async def classify_tool(inputs, state, llm_config):
        return {"script_type": "unexpected-branch"}

    async def first_branch(inputs, state, llm_config):
        branch_calls.append("first")
        return {"text": "first branch"}

    async def second_branch(inputs, state, llm_config):
        branch_calls.append("second")
        return {"text": "second branch"}

    tools = {
        "files": files_tool,
        "classify_script": classify_tool,
        "transcribe": first_branch,
        "summarize": second_branch,
    }
    monkeypatch.setattr(
        "fichero.workflows.builder.get_tool",
        lambda tool_name: tools.get(tool_name),
    )

    workflow = WorkflowDef(
        name="RouteFallback",
        nodes=[
            NodeDef(id="files", tool="files", config={}),
            NodeDef(id="classify", tool="classify_script", config={}),
            NodeDef(id="branch-a", tool="transcribe", config={}),
            NodeDef(id="branch-b", tool="summarize", config={}),
        ],
        edges=[
            EdgeDef(source="files", target="classify", source_port="files", target_port="files"),
            EdgeDef(
                source="classify",
                target="",
                route_key="$.nodes.classify.script_type",
                route_map={"typescript": "branch-a", "manuscript": "branch-b"},
            ),
        ],
    )

    final_state = await build_graph(workflow, enable_parallel=False).ainvoke(
        {"workflow_id": "wf-1", "library_path": ""}
    )

    assert branch_calls == ["first"]
    assert final_state["outputs"]["branch-a"]["text"] == "first branch"
    assert "branch-b" not in final_state["outputs"]
    assert "branch-a" in final_state["completed_nodes"]


@pytest.mark.asyncio
async def test_node_skips_when_already_completed():
    calls = {"count": 0}

    async def tool_fn(inputs, state, llm_config):
        calls["count"] += 1
        return {"text": "should not run"}

    node_fn = _make_node_function(
        NodeDef(id="done-node", tool="transcribe", config={}),
        tool_fn,
        LLMConfig(provider="openai", model="gpt-4o-mini"),
        workflow_config={},
        incoming_edges=[],
    )

    result = await node_fn({"outputs": {}, "completed_nodes": ["done-node"]})
    assert result == {}
    assert calls["count"] == 0


@pytest.mark.asyncio
async def test_node_defers_until_all_upstream_outputs_exist():
    calls = {"count": 0}

    async def tool_fn(inputs, state, llm_config):
        calls["count"] += 1
        return {"text": "ready"}

    node_fn = _make_node_function(
        NodeDef(id="consumer", tool="transcribe", config={}),
        tool_fn,
        LLMConfig(provider="openai", model="gpt-4o-mini"),
        workflow_config={},
        incoming_edges=[
            {"source": "source-a", "source_port": "text", "target_port": "left"},
            {"source": "source-b", "source_port": "text", "target_port": "right"},
        ],
    )

    deferred = await node_fn({"outputs": {"source-a": {"text": "A"}}, "completed_nodes": []})
    assert deferred == {}
    assert calls["count"] == 0


@pytest.mark.asyncio
async def test_quality_gate_abort_raises_and_blocks_downstream(monkeypatch):
    downstream_calls: list[str] = []

    async def source_tool(inputs, state, llm_config):
        return {"text": "garbled OCR"}

    async def downstream_tool(inputs, state, llm_config):
        downstream_calls.append("downstream")
        return {"text": "should not run"}

    monkeypatch.setattr(
        "fichero.workflows.builder.get_tool",
        lambda tool_name: {
            "transcribe": source_tool,
            "summarize": downstream_tool,
        }.get(tool_name),
    )
    monkeypatch.setattr(
        "fichero.workflows.builder.assess_result_quality",
        lambda result: (True, "all pages unreadable"),
    )

    workflow = WorkflowDef(
        name="QualityGateStop",
        nodes=[
            NodeDef(id="ocr", tool="transcribe", config={"quality_gate": True}),
            NodeDef(id="summary", tool="summarize", config={}),
        ],
        edges=[
            EdgeDef(source="ocr", target="summary", source_port="text", target_port="text"),
        ],
    )

    with pytest.raises(SystemicErrorDetected, match="unreadable output"):
        await build_graph(workflow, enable_parallel=False).ainvoke(
            {"workflow_id": "wf-2", "library_path": ""}
        )

    assert downstream_calls == []
