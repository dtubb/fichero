"""Tests for workflow interrupt plumbing."""

from langgraph.graph import StateGraph

from fichero_server.workflows.builder import build_graph
from fichero_server.workflows.runtime import create_compiled_app
from fichero_server.workflows.types import NodeDef, WorkflowDef


def test_create_compiled_app_forwards_interrupts_to_builder(monkeypatch, tmp_path):
    captured: dict[str, dict[str, object]] = {}

    class DummyGraph:
        def compile(self, **kwargs):
            captured["compile_kwargs"] = kwargs
            return "compiled-app"

    def fake_build_graph(*args, **kwargs):
        captured["build_kwargs"] = kwargs
        return DummyGraph()

    dummy_checkpointer = object()
    monkeypatch.setattr(
        "fichero_server.workflows.runtime.AsyncDuckDBCheckpointer.from_db_path",
        lambda db_path: dummy_checkpointer,
    )
    monkeypatch.setattr("fichero_server.workflows.runtime.build_graph", fake_build_graph)

    workflow = WorkflowDef(id="wf-1", name="Test Workflow")

    app, checkpointer = create_compiled_app(
        workflow,
        db_path=tmp_path / "test.duckdb",
        interrupt_before=["step_2"],
        interrupt_after=["step_3"],
    )

    assert app == "compiled-app"
    assert checkpointer is dummy_checkpointer
    assert captured["build_kwargs"]["interrupt_before"] == ["step_2"]
    assert captured["build_kwargs"]["interrupt_after"] == ["step_3"]


def test_build_graph_forwards_interrupts_to_compile(monkeypatch):
    captured: dict[str, object] = {}

    def fake_get_tool(tool_name: str):
        return lambda *args, **kwargs: None

    def fake_compile(
        self,
        checkpointer=None,
        *,
        interrupt_before=None,
        interrupt_after=None,
        **kwargs,
    ):
        captured["compile_kwargs"] = {
            "checkpointer": checkpointer,
            "interrupt_before": interrupt_before,
            "interrupt_after": interrupt_after,
        }
        return "compiled-graph"

    monkeypatch.setattr("fichero_server.workflows.builder.get_tool", fake_get_tool)
    monkeypatch.setattr(StateGraph, "compile", fake_compile)

    workflow = WorkflowDef(
        id="wf-2",
        name="Test Workflow",
        nodes=[NodeDef(id="node_1", tool="test_tool")],
    )

    compiled = build_graph(
        workflow,
        interrupt_before=["node_1"],
        interrupt_after=["node_1"],
    )

    assert compiled == "compiled-graph"
    assert captured["compile_kwargs"]["interrupt_before"] == ["node_1"]
    assert captured["compile_kwargs"]["interrupt_after"] == ["node_1"]
