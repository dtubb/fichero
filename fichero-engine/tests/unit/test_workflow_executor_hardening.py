from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest
from fichero.execution import runner
from fichero.llm import LLMConfig
from fichero.models import Workflow
from fichero.workflows.builder import SystemicErrorDetected, _make_node_function
from fichero.workflows.types import InputMapping, NodeDef


class _FakeActivityStore:
    def __init__(self) -> None:
        self.last_update_kwargs = None

    async def save_workflow_run(self, **_kwargs):
        return None

    async def update_workflow_run(self, **kwargs):
        self.last_update_kwargs = kwargs
        return None


class _FakeActivityTracker:
    def __init__(self) -> None:
        self.store = _FakeActivityStore()

    def workflow_started(self, **_kwargs):
        return None

    def workflow_completed(self, **_kwargs):
        return None

    def workflow_failed(self, **_kwargs):
        return None

    def workflow_cancelled(self, **_kwargs):
        return None

    def node_started(self, **_kwargs):
        return None

    def node_completed(self, **_kwargs):
        return None


class _FakeGraph:
    def draw_mermaid(self):
        return "graph TD"


class _FakePreviewApp:
    def get_graph(self):
        return _FakeGraph()


class _FakeCheckpointer:
    async def aget_tuple(self, _config):
        return SimpleNamespace(checkpoint={"id": "ckpt-1", "channel_values": {}})


class _SystemicFailingRunApp:
    async def astream_events(self, *_args, **_kwargs):
        raise SystemicErrorDetected(
            message="Step 'Explode' failed: boom",
            error_count=1,
            total_count=1,
            errors=[{"node": "explode", "error": "boom"}],
        )
        yield  # pragma: no cover


class _SingleEventRunApp:
    async def astream_events(self, *_args, **_kwargs):
        yield {"event": "on_chain_start", "name": "files", "data": {}}


def _workflow(workflow_id: str = "wf-hardening") -> Workflow:
    return Workflow(
        id=workflow_id,
        name="Hardening Workflow",
        format="nodes",
        nodes=[{"id": "files", "tool": "files", "label": "Files"}],
        edges=[],
    )


@pytest.mark.asyncio
async def test_node_tool_exception_raises_systemic_error():
    async def fail_tool(inputs: dict, state: dict, llm_config: LLMConfig) -> dict:
        raise RuntimeError("boom")

    node_fn = _make_node_function(
        NodeDef(id="explode", tool="files", label="Explode", config={}),
        fail_tool,
        LLMConfig(provider="openai", model="gpt-4o-mini"),
        workflow_config={},
        incoming_edges=[],
    )

    with pytest.raises(SystemicErrorDetected, match="Step 'Explode' failed: boom"):
        await node_fn({"outputs": {}, "completed_nodes": []})


@pytest.mark.asyncio
async def test_unresolved_input_mapping_fails_cleanly_when_tool_requires_value():
    async def require_text(inputs: dict, state: dict, llm_config: LLMConfig) -> dict:
        if not inputs.get("text"):
            raise ValueError("missing required input: text")
        return {"text": inputs["text"]}

    node_fn = _make_node_function(
        NodeDef(
            id="consumer",
            tool="summarize",
            label="Consumer",
            config={},
            input_mappings=[
                InputMapping(port_id="text", source_path="$.nodes.missing.text"),
            ],
        ),
        require_text,
        LLMConfig(provider="openai", model="gpt-4o-mini"),
        workflow_config={},
        incoming_edges=[],
    )

    with pytest.raises(
        SystemicErrorDetected, match="Step 'Consumer' failed: missing required input: text"
    ):
        await node_fn({"outputs": {}, "completed_nodes": []})


@pytest.mark.asyncio
async def test_background_runner_marks_systemic_failures_failed(tmp_path, monkeypatch):
    thread_id = "thread-systemic"
    workflow_id = "wf-systemic"
    events = runner.WorkflowEventHub()
    runner._set_workflow_state(thread_id, {"events": events})

    tracker = _FakeActivityTracker()
    monkeypatch.setattr(runner, "get_activity_tracker", lambda _path: tracker)
    monkeypatch.setattr(runner, "build_graph", lambda *_args, **_kwargs: _FakePreviewApp())
    monkeypatch.setattr(
        runner,
        "create_compiled_app",
        lambda *_args, **_kwargs: (_SystemicFailingRunApp(), _FakeCheckpointer()),
    )
    monkeypatch.setattr(
        "fichero.db.manager.db_manager.get_database",
        lambda _library_path: SimpleNamespace(path=tmp_path / "library.duckdb"),
    )
    monkeypatch.setattr("fichero.db.manager.db_manager.close_current_thread", lambda: None)

    await runner._run_workflow_in_background(
        thread_id,
        _workflow(workflow_id),
        ExecuteWorkflowRequest(workflow_id=workflow_id, inputs={}),
        SimpleNamespace(path=tmp_path / "library.duckdb"),
    )

    state = runner._get_workflow_state(thread_id)
    assert state is not None
    assert state["status"] == "failed"
    assert "Explode" in state["error"]

    update_kwargs = tracker.store.last_update_kwargs
    assert update_kwargs is not None
    assert update_kwargs["status"] == "failed"
    assert "Explode" in update_kwargs["error"]

    sub = events.subscribe()
    seen = []
    while True:
        event = sub.get_nowait()
        if event is None:
            break
        seen.append(event.event)
    assert "systemic_error" in seen
    runner._remove_workflow_state(thread_id)


@pytest.mark.asyncio
async def test_background_runner_cancellation_marks_run_cancelled(tmp_path, monkeypatch):
    thread_id = "thread-cancelled"
    workflow_id = "wf-cancelled"
    events = runner.WorkflowEventHub()
    runner._set_workflow_state(thread_id, {"events": events, "cancel_requested": True})

    tracker = _FakeActivityTracker()
    monkeypatch.setattr(runner, "get_activity_tracker", lambda _path: tracker)
    monkeypatch.setattr(runner, "build_graph", lambda *_args, **_kwargs: _FakePreviewApp())
    monkeypatch.setattr(
        runner,
        "create_compiled_app",
        lambda *_args, **_kwargs: (_SingleEventRunApp(), _FakeCheckpointer()),
    )
    monkeypatch.setattr(
        "fichero.db.manager.db_manager.get_database",
        lambda _library_path: SimpleNamespace(path=tmp_path / "library.duckdb"),
    )
    monkeypatch.setattr("fichero.db.manager.db_manager.close_current_thread", lambda: None)

    await runner._run_workflow_in_background(
        thread_id,
        _workflow(workflow_id),
        ExecuteWorkflowRequest(workflow_id=workflow_id, inputs={}),
        SimpleNamespace(path=tmp_path / "library.duckdb"),
    )

    state = runner._get_workflow_state(thread_id)
    assert state is not None
    assert state["status"] == "cancelled"

    update_kwargs = tracker.store.last_update_kwargs
    assert update_kwargs is not None
    assert update_kwargs["status"] == "cancelled"

    sub = events.subscribe()
    seen = []
    while True:
        event = sub.get_nowait()
        if event is None:
            break
        seen.append(event.event)
    assert "cancelled" in seen
    assert "error" not in seen
    runner._remove_workflow_state(thread_id)
