from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest
from fichero_server.execution import runner
from fichero_server.models import Workflow


class _FakeActivityStore:
    def __init__(self):
        self.last_update_kwargs = None

    async def save_workflow_run(self, **_kwargs):
        return None

    async def update_workflow_run(self, **_kwargs):
        self.last_update_kwargs = _kwargs
        return None


class _FakeActivityTracker:
    def __init__(self):
        self.store = _FakeActivityStore()

    def workflow_started(self, **_kwargs):
        return None

    def node_started(self, **_kwargs):
        return None

    def node_completed(self, **_kwargs):
        return None

    def workflow_completed(self, **_kwargs):
        return None

    def workflow_failed(self, **_kwargs):
        raise AssertionError("non-dict node output must not fail the workflow")


class _FakeGraph:
    def draw_mermaid(self):
        return "graph TD"


class _FakePreviewApp:
    def get_graph(self):
        return _FakeGraph()


class _FakeRunApp:
    async def astream_events(self, *_args, **_kwargs):
        yield {"event": "on_chain_start", "name": "fan_out", "data": {}}
        yield {"event": "on_chain_end", "name": "fan_out", "data": {"output": []}}


class _FakeCheckpointer:
    async def aget_tuple(self, _config):
        return SimpleNamespace(checkpoint={"id": "ckpt-1", "channel_values": {}})


@pytest.mark.asyncio
async def test_background_runner_handles_non_dict_node_output(monkeypatch, tmp_path):
    """Regression for Transcribe HTR fan-out crashing on list output."""
    thread_id = "thread-non-dict"
    workflow_id = "wf-non-dict"
    events = runner.WorkflowEventHub()
    runner._set_workflow_state(thread_id, {"events": events})

    tracker = _FakeActivityTracker()
    monkeypatch.setattr(runner, "get_activity_tracker", lambda _path: tracker)
    monkeypatch.setattr(runner, "build_graph", lambda *_args, **_kwargs: _FakePreviewApp())
    monkeypatch.setattr(
        runner,
        "create_compiled_app",
        lambda *_args, **_kwargs: (_FakeRunApp(), _FakeCheckpointer()),
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.get_database",
        lambda _library_path: SimpleNamespace(path=tmp_path / "library.duckdb"),
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.close_current_thread",
        lambda: None,
    )

    workflow = Workflow(
        id=workflow_id,
        name="Non Dict Output",
        format="nodes",
        nodes=[{"id": "fan_out", "tool": "files", "label": "fan_out"}],
        edges=[],
    )
    request = ExecuteWorkflowRequest(workflow_id=workflow_id, inputs={})

    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        request,
        SimpleNamespace(path=tmp_path / "library.duckdb"),
    )

    state = runner._get_workflow_state(thread_id)
    assert state is not None
    assert state["status"] == "completed"

    update_kwargs = tracker.store.last_update_kwargs
    assert update_kwargs is not None
    timeline = update_kwargs["progress_timeline"]
    event_names = [event["event"] for event in timeline["events"]]
    assert "start" in event_names
    assert "node_begin" in event_names
    assert "node_end" in event_names
    assert event_names[-1] == "complete"

    sub = events.subscribe()
    event_names = []
    while True:
        event = sub.get_nowait()
        if event is None:
            break
        event_names.append(event.event)
    assert "node_end" in event_names
    assert "complete" in event_names

    runner._remove_workflow_state(thread_id)
