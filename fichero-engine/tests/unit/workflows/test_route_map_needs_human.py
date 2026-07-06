"""Unit tests for route_map needs_human_selection surfacing. (#2238)

Before the fix, route_map silently fell back to branch 0 when the value was
unknown or when needs_human_selection=True.  After the fix:
- If the route_map has a "needs_human_selection" branch AND the source node
  set needs_human_selection=True, the workflow routes there explicitly.
- If no such branch exists and the value is unknown, falls back to branch 0
  but logs at ERROR level (was WARNING) so the oversight is discoverable.
"""
from __future__ import annotations

import pytest

from fichero.workflows.types import WorkflowDef, NodeDef, EdgeDef


@pytest.mark.asyncio
async def test_needs_human_selection_routes_to_dedicated_branch(monkeypatch):
    """#2238: needs_human_selection=True must route to the dedicated branch."""
    branch_calls: list[str] = []

    async def files_tool(inputs, state, llm_config):
        return {"files": ["/tmp/doc.pdf"], "documents": []}

    async def classify_tool(inputs, state, llm_config):
        # Low-confidence mixed result → both flags set
        return {"script_type": "mixed", "needs_human_selection": True}

    async def human_review_branch(inputs, state, llm_config):
        branch_calls.append("human")
        return {"text": "human review required"}

    async def typescript_branch(inputs, state, llm_config):
        branch_calls.append("typescript")
        return {"text": "typescript branch"}

    tools = {
        "files": files_tool,
        "classify_script": classify_tool,
        "transcribe_ts": typescript_branch,
        "human_review": human_review_branch,
    }
    monkeypatch.setattr(
        "fichero.workflows.builder.get_tool",
        lambda tool_name: tools.get(tool_name),
    )

    workflow = WorkflowDef(
        name="NeedsHumanRoute",
        nodes=[
            NodeDef(id="files", tool="files", config={}),
            NodeDef(id="classify", tool="classify_script", config={}),
            NodeDef(id="branch-ts", tool="transcribe_ts", config={}),
            NodeDef(id="branch-human", tool="human_review", config={}),
        ],
        edges=[
            EdgeDef(source="files", target="classify", source_port="files", target_port="files"),
            EdgeDef(
                source="classify",
                target="",
                route_key="$.nodes.classify.script_type",
                route_map={
                    "typescript": "branch-ts",
                    "needs_human_selection": "branch-human",
                },
            ),
        ],
    )

    from fichero.workflows.builder import build_graph

    final_state = await build_graph(workflow, enable_parallel=False).ainvoke(
        {"workflow_id": "wf-2238", "library_path": ""}
    )

    assert branch_calls == ["human"], (
        "#2238: needs_human_selection=True must route to the 'needs_human_selection' branch"
    )
    assert "branch-human" in final_state["completed_nodes"]
    assert "branch-ts" not in final_state.get("completed_nodes", set())


@pytest.mark.asyncio
async def test_unknown_value_no_needs_human_branch_still_falls_back(monkeypatch):
    """#2238: when no 'needs_human_selection' branch exists, unknown value still fallbacks."""
    branch_calls: list[str] = []

    async def files_tool(inputs, state, llm_config):
        return {"files": ["/tmp/doc.pdf"], "documents": []}

    async def classify_tool(inputs, state, llm_config):
        return {"script_type": "totally-unknown", "needs_human_selection": False}

    async def first_branch(inputs, state, llm_config):
        branch_calls.append("first")
        return {"text": "first"}

    async def second_branch(inputs, state, llm_config):
        branch_calls.append("second")
        return {"text": "second"}

    tools = {
        "files": files_tool,
        "classify_script": classify_tool,
        "transcribe_a": first_branch,
        "transcribe_b": second_branch,
    }
    monkeypatch.setattr(
        "fichero.workflows.builder.get_tool",
        lambda tool_name: tools.get(tool_name),
    )

    workflow = WorkflowDef(
        name="UnknownFallback",
        nodes=[
            NodeDef(id="files", tool="files", config={}),
            NodeDef(id="classify", tool="classify_script", config={}),
            NodeDef(id="branch-a", tool="transcribe_a", config={}),
            NodeDef(id="branch-b", tool="transcribe_b", config={}),
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

    from fichero.workflows.builder import build_graph

    final_state = await build_graph(workflow, enable_parallel=False).ainvoke(
        {"workflow_id": "wf-2238-b", "library_path": ""}
    )

    assert branch_calls == ["first"], (
        "#2238: unknown value with no needs_human_selection branch must fall back to first"
    )


@pytest.mark.asyncio
async def test_needs_human_true_no_dedicated_branch_routes_by_value(monkeypatch):
    """#2238: when needs_human_selection=True but no dedicated branch, route by value normally."""
    branch_calls: list[str] = []

    async def files_tool(inputs, state, llm_config):
        return {"files": ["/tmp/doc.pdf"], "documents": []}

    async def classify_tool(inputs, state, llm_config):
        # Low confidence but value IS in route_map — no dedicated human branch
        return {"script_type": "typescript", "needs_human_selection": True}

    async def typescript_branch(inputs, state, llm_config):
        branch_calls.append("typescript")
        return {"text": "typescript"}

    async def manuscript_branch(inputs, state, llm_config):
        branch_calls.append("manuscript")
        return {"text": "manuscript"}

    tools = {
        "files": files_tool,
        "classify_script": classify_tool,
        "transcribe_ts": typescript_branch,
        "transcribe_ms": manuscript_branch,
    }
    monkeypatch.setattr(
        "fichero.workflows.builder.get_tool",
        lambda tool_name: tools.get(tool_name),
    )

    workflow = WorkflowDef(
        name="NeedsHumanNoBranch",
        nodes=[
            NodeDef(id="files", tool="files", config={}),
            NodeDef(id="classify", tool="classify_script", config={}),
            NodeDef(id="branch-ts", tool="transcribe_ts", config={}),
            NodeDef(id="branch-ms", tool="transcribe_ms", config={}),
        ],
        edges=[
            EdgeDef(source="files", target="classify", source_port="files", target_port="files"),
            EdgeDef(
                source="classify",
                target="",
                route_key="$.nodes.classify.script_type",
                route_map={"typescript": "branch-ts", "manuscript": "branch-ms"},
            ),
        ],
    )

    from fichero.workflows.builder import build_graph

    final_state = await build_graph(workflow, enable_parallel=False).ainvoke(
        {"workflow_id": "wf-2238-c", "library_path": ""}
    )

    # No dedicated human branch → routes by value ("typescript" → branch-ts)
    assert branch_calls == ["typescript"], (
        "#2238: without dedicated branch, needs_human_selection=True must not block routing"
    )
    assert "branch-ts" in final_state["completed_nodes"]


@pytest.mark.asyncio
async def test_parallel_route_map_honours_needs_human_branch(monkeypatch):
    """Parallel route_map must honour needs_human_selection before fan-out."""
    branch_calls: list[str] = []

    async def files_tool(inputs, state, llm_config):
        return {"files": ["/tmp/doc-1.pdf", "/tmp/doc-2.pdf"], "documents": []}

    async def classify_tool(inputs, state, llm_config):
        return {"script_type": "mixed", "needs_human_selection": True}

    async def transcribe_branch(inputs, state, llm_config):
        branch_calls.append(f"parallel:{inputs.get('file')}")
        return {"text": "parallel branch"}

    async def human_review_branch(inputs, state, llm_config):
        branch_calls.append("human")
        return {"text": "human review required"}

    tools = {
        "files": files_tool,
        "classify_script": classify_tool,
        "transcribe": transcribe_branch,
        "human_review": human_review_branch,
    }
    monkeypatch.setattr(
        "fichero.workflows.builder.get_tool",
        lambda tool_name: tools.get(tool_name),
    )

    workflow = WorkflowDef(
        name="ParallelNeedsHumanRoute",
        nodes=[
            NodeDef(id="files", tool="files", config={}),
            NodeDef(id="classify", tool="classify_script", config={}),
            NodeDef(id="branch-parallel", tool="transcribe", config={}),
            NodeDef(id="branch-human", tool="human_review", config={}),
        ],
        edges=[
            EdgeDef(source="files", target="classify", source_port="files", target_port="files"),
            EdgeDef(
                source="classify",
                target="",
                route_key="$.nodes.classify.script_type",
                route_map={
                    "typescript": "branch-parallel",
                    "needs_human_selection": "branch-human",
                },
            ),
        ],
    )

    from fichero.workflows.builder import build_graph

    final_state = await build_graph(workflow, enable_parallel=True).ainvoke(
        {"workflow_id": "wf-2238-parallel", "library_path": ""}
    )

    assert branch_calls == ["human"]
    assert "branch-human" in final_state["completed_nodes"]
    assert "branch-parallel" not in final_state.get("completed_nodes", set())
