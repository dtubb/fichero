"""#4314: the runner's snapshot must not destroy per-node config/provider/model,
and the progress timeline must flush at node boundaries, not only at terminal
states.

Previously the runner overwrote the full node dicts /execute had saved with a
trimmed ``{id, tool, label}`` projection (COALESCE let the overwrite land), so
the prompt and model a run actually used were lost the moment the run started;
and ``progress_timeline`` was only persisted on terminal transitions, so a
killed process lost the whole trace.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.api.routes.workflow_execution.schemas import ExecuteWorkflowRequest
from fichero_server.execution import runner
from fichero_server.models import Workflow


class _RecordingActivityStore:
    def __init__(self):
        self.saved_run_kwargs: list[dict] = []
        self.update_calls: list[dict] = []

    async def save_workflow_run(self, **kwargs):
        self.saved_run_kwargs.append(kwargs)

    async def update_workflow_run(self, **kwargs):
        self.update_calls.append(kwargs)


class _RecordingActivityTracker:
    def __init__(self):
        self.store = _RecordingActivityStore()

    def __getattr__(self, _name):
        return lambda **_kwargs: None


class _FakeCheckpointer:
    async def aget_tuple(self, _config):
        return SimpleNamespace(checkpoint={"id": "ckpt-1", "channel_values": {}})


def _wire(monkeypatch, tracker, run_app, tmp_path):
    events = runner.WorkflowEventHub()
    monkeypatch.setattr(runner, "get_activity_tracker", lambda _p: tracker)
    monkeypatch.setattr(
        runner,
        "build_graph",
        lambda *_a, **_k: SimpleNamespace(
            get_graph=lambda: SimpleNamespace(draw_mermaid=lambda: "graph TD")
        ),
    )
    monkeypatch.setattr(
        runner,
        "create_compiled_app",
        lambda *_a, **_k: (run_app, _FakeCheckpointer()),
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.get_database",
        lambda _library_path: SimpleNamespace(path=tmp_path / "library.duckdb"),
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.close_current_thread", lambda: None
    )
    return events


@pytest.mark.asyncio
async def test_snapshot_preserves_node_config_provider_model(monkeypatch, tmp_path):
    thread_id = "thread-snapshot"

    class _App:
        async def astream_events(self, *_a, **_k):
            yield {"event": "on_chain_start", "name": "node-1", "data": {}}
            yield {"event": "on_chain_end", "name": "node-1", "data": {"output": {}}}

    tracker = _RecordingActivityTracker()
    events = _wire(monkeypatch, tracker, _App(), tmp_path)
    runner._set_workflow_state(thread_id, {"events": events})

    workflow = Workflow(
        id="wf-snap",
        name="Snapshot",
        format="nodes",
        nodes=[
            {
                "id": "node-1",
                "tool": "transcribe",
                "label": "node-1",
                "config": {"prompt": "Transcribe this page faithfully."},
                "inputs": {"files": "$.nodes.src.files"},
                "provider_name": "openrouter",
                "model_name": "qwen-vl-max",
            }
        ],
        edges=[],
    )
    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(workflow_id="wf-snap", inputs={}),
        SimpleNamespace(path=tmp_path / "library.duckdb"),
    )

    assert tracker.store.saved_run_kwargs, "runner must persist the run record"
    snapshot = tracker.store.saved_run_kwargs[-1]["workflow_snapshot"]
    node = snapshot["nodes"][0]
    assert node["config"] == {"prompt": "Transcribe this page faithfully."}
    assert node["inputs"] == {"files": "$.nodes.src.files"}
    assert node["provider_name"] == "openrouter"
    assert node["model_name"] == "qwen-vl-max"


@pytest.mark.asyncio
async def test_snapshot_records_effective_override_model(monkeypatch, tmp_path):
    """A run-level provider/model override is what the run actually used —
    the snapshot must record the overridden values."""
    thread_id = "thread-override"

    class _App:
        async def astream_events(self, *_a, **_k):
            yield {"event": "on_chain_start", "name": "node-1", "data": {}}
            yield {"event": "on_chain_end", "name": "node-1", "data": {"output": {}}}

    tracker = _RecordingActivityTracker()
    events = _wire(monkeypatch, tracker, _App(), tmp_path)
    runner._set_workflow_state(thread_id, {"events": events})

    monkeypatch.setattr(
        runner,
        "get_tool_def",
        lambda _name: SimpleNamespace(uses_llm=True),
    )
    workflow = Workflow(
        id="wf-override",
        name="Override",
        format="nodes",
        nodes=[
            {
                "id": "node-1",
                "tool": "transcribe",
                "label": "node-1",
                "provider_name": "openai",
                "model_name": "gpt-4o",
            }
        ],
        edges=[],
    )
    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(
            workflow_id="wf-override",
            inputs={},
            provider_override="apple",
            model_override="on-device",
        ),
        SimpleNamespace(path=tmp_path / "library.duckdb"),
    )

    node = tracker.store.saved_run_kwargs[-1]["workflow_snapshot"]["nodes"][0]
    assert node["provider_name"] == "apple"
    assert node["model_name"] == "on-device"


@pytest.mark.asyncio
async def test_timeline_flushes_at_node_boundary_before_terminal(
    monkeypatch, tmp_path
):
    """A crash after the first node must leave a partial timeline: the runner
    persists progress_timeline at each node_end, not only at terminal states."""
    thread_id = "thread-flush"

    class _App:
        async def astream_events(self, *_a, **_k):
            yield {"event": "on_chain_start", "name": "node-1", "data": {}}
            yield {"event": "on_chain_end", "name": "node-1", "data": {"output": {}}}
            raise RuntimeError("simulated crash mid-run")

    tracker = _RecordingActivityTracker()
    events = _wire(monkeypatch, tracker, _App(), tmp_path)
    runner._set_workflow_state(thread_id, {"events": events})

    workflow = Workflow(
        id="wf-flush",
        name="Flush",
        format="nodes",
        nodes=[
            {"id": "node-1", "tool": "transcribe", "label": "node-1"},
            {"id": "node-2", "tool": "clean_text", "label": "node-2"},
        ],
        edges=[{"source": "node-1", "target": "node-2"}],
    )
    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(workflow_id="wf-flush", inputs={}),
        SimpleNamespace(path=tmp_path / "library.duckdb"),
    )

    boundary_flushes = [
        call
        for call in tracker.store.update_calls
        if call.get("progress_timeline") is not None and "status" not in call
    ]
    assert boundary_flushes, (
        "a node boundary must persist progress_timeline without waiting for a "
        "terminal transition"
    )
    steps = boundary_flushes[0]["progress_timeline"]["steps"]
    assert any(
        step.get("node_id") == "node-1" and step.get("status") == "success"
        for step in steps
    ), "the boundary flush must contain the completed first node"

    # And the terminal failed update still lands with the timeline.
    terminal = [c for c in tracker.store.update_calls if c.get("status") == "failed"]
    assert terminal and terminal[-1]["progress_timeline"] is not None
