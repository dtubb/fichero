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
