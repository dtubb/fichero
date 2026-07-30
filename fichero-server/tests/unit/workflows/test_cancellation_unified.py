"""#4317: one cancellation primitive for single runs and batches; resume runs
on the worker-thread background path.

- ``execution.cancellation`` is the shared registry (threading.Event) the
  cancel endpoint, DELETE, batch cancel, the runner loop, AND the per-file
  fan-out all consult — so cancel reaches an evicted run and stops a
  multi-file node within one file boundary.
- ``/threads/{id}/resume`` no longer blocks the FastAPI loop with ``ainvoke``:
  it dispatches ``_run_workflow_in_background(is_resume=True)``, which streams
  SSE, respects a subsequent cancel, and hits the completion boundary.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.execution import cancellation


@pytest.fixture(autouse=True)
def _clean_registry():
    cancellation._events.clear()
    yield
    cancellation._events.clear()


@pytest.fixture
def temp_db():
    from fichero_server.db import Database

    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "fichero.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir)


class TestCancellationRegistry:
    def test_set_check_clear(self):
        assert not cancellation.cancellation_requested("run-1")
        cancellation.request_cancellation("run-1")
        assert cancellation.cancellation_requested("run-1")
        cancellation.clear_cancellation("run-1")
        assert not cancellation.cancellation_requested("run-1")

    def test_empty_run_id_raises_on_event_and_is_false_on_check(self):
        with pytest.raises(ValueError):
            cancellation.cancellation_event("")
        assert not cancellation.cancellation_requested("")
        assert not cancellation.cancellation_requested(None)

    def test_registry_is_bounded(self):
        for i in range(cancellation._EVENTS_LIMIT + 50):
            cancellation.cancellation_event(f"run-{i}")
        assert len(cancellation._events) <= cancellation._EVENTS_LIMIT


class TestPerFileFanOutCancellation:
    @pytest.mark.asyncio
    async def test_cancel_stops_at_file_boundary(self):
        """A cancelled run's remaining fan-out branches must not invoke the
        tool — cancel latency is bounded by one file, not the whole node."""
        from fichero_server.workflows.builder import _make_parallel_node_function
        from fichero_server.workflows.types import NodeDef
        from fichero_server.llm import LLMConfig

        calls = []

        async def tool_fn(inputs, state, llm_config):
            calls.append(inputs)
            return {"text": "done"}

        node_fn = _make_parallel_node_function(
            NodeDef(id="node-1", tool="transcribe", label="T", inputs={}, config={}),
            tool_fn,
            LLMConfig(provider="test", model="test"),
            workflow_config={"workflow_id": "wf-1"},
        )

        state = {
            "task_id": "run-cancel-fanout",
            "parallel_file": "/tmp/a.png",
            "parallel_index": 0,
            "parallel_total": 3,
            "library_path": "",
        }

        # Not cancelled → tool runs.
        result = await node_fn(dict(state))
        assert calls, "sanity: tool runs when not cancelled"
        assert not result["parallel_results"]["node-1"][0].get("cancelled")

        # Cancelled → branch short-circuits without calling the tool.
        calls.clear()
        cancellation.request_cancellation("run-cancel-fanout")
        result = await node_fn(dict(state))
        assert calls == [], "cancelled run must not invoke the tool per file"
        row = result["parallel_results"]["node-1"][0]
        assert row["cancelled"] is True
        assert row["success"] is False


class _FakeActivityStore:
    def __init__(self):
        self.update_calls = []

    async def save_workflow_run(self, **_kwargs):
        return None

    async def update_workflow_run(self, **kwargs):
        self.update_calls.append(kwargs)


class _FakeActivityTracker:
    def __init__(self):
        self.store = _FakeActivityStore()
        self.calls = []

    def __getattr__(self, name):
        def _record(**kwargs):
            self.calls.append((name, kwargs))

        return _record


class _FakeCheckpointer:
    def __init__(self, channel_values=None):
        self.channel_values = channel_values or {}

    async def aget_tuple(self, _config):
        return SimpleNamespace(
            checkpoint={"id": "ckpt-1", "channel_values": self.channel_values}
        )


def _wire_runner(monkeypatch, run_app, checkpointer, db_obj):
    from fichero_server.execution import runner

    tracker = _FakeActivityTracker()
    monkeypatch.setattr(runner, "get_activity_tracker", lambda _p: tracker)
    monkeypatch.setattr(
        runner,
        "build_graph",
        lambda *_a, **_k: SimpleNamespace(
            get_graph=lambda: SimpleNamespace(draw_mermaid=lambda: "graph TD")
        ),
    )
    monkeypatch.setattr(
        runner, "create_compiled_app", lambda *_a, **_k: (run_app, checkpointer)
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.get_database",
        lambda _library_path: db_obj,
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.close_current_thread", lambda: None
    )
    return runner, tracker


@pytest.mark.asyncio
async def test_runner_honors_shared_cancellation_event(monkeypatch, tmp_path):
    """Cancel via the SHARED registry alone (no registry flag) — the path a
    registry-evicted run depends on — must cancel the run."""
    from fichero_server.api.routes.workflow_execution.schemas import (
        ExecuteWorkflowRequest,
    )
    from fichero_server.models import Workflow

    thread_id = "thread-shared-cancel"

    class _App:
        async def astream_events(self, *_a, **_k):
            yield {"event": "on_chain_start", "name": "node-1", "data": {}}
            # Cancel arrives mid-stream, via the shared event only.
            cancellation.request_cancellation(thread_id)
            yield {"event": "on_chain_end", "name": "node-1", "data": {"output": {}}}
            raise AssertionError("stream must stop after cancellation")

    db_obj = SimpleNamespace(path=tmp_path / "library.duckdb")
    runner, tracker = _wire_runner(monkeypatch, _App(), _FakeCheckpointer(), db_obj)
    state = {"events": runner.WorkflowEventHub()}
    runner._set_workflow_state(thread_id, state)

    workflow = Workflow(
        id="wf-sc",
        name="SharedCancel",
        format="nodes",
        nodes=[{"id": "node-1", "tool": "transcribe", "label": "node-1"}],
        edges=[],
    )
    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(workflow_id="wf-sc", inputs={}),
        db_obj,
    )

    assert state["status"] == "cancelled"
    # Terminal run must have dropped its event from the registry.
    assert not cancellation.cancellation_requested(thread_id)


@pytest.mark.asyncio
async def test_resume_runs_on_background_path_and_completes(
    monkeypatch, temp_db
):
    """is_resume=True streams from the checkpoint (resume_input, not a fresh
    initial state), records workflow_resumed, and hits the completion
    boundary — resumed documents complete (#4315 acceptance)."""
    from fichero_server.api.routes.workflow_execution.schemas import (
        ExecuteWorkflowRequest,
    )
    from fichero_server.models import Document, Status, Workflow

    doc = Document(name="p.png", path="/tmp/p.png", status=Status.processing)
    temp_db.save(doc)

    thread_id = "thread-resume-bg"
    seen_inputs = []

    class _App:
        async def astream_events(self, stream_input, *_a, **_k):
            seen_inputs.append(stream_input)
            yield {"event": "on_chain_start", "name": "node-1", "data": {}}
            yield {"event": "on_chain_end", "name": "node-1", "data": {"output": {}}}

    checkpointer = _FakeCheckpointer(
        channel_values={"outputs": {"src": {"documents": [{"id": doc.id}]}}}
    )
    runner, tracker = _wire_runner(monkeypatch, _App(), checkpointer, temp_db)
    state = {"events": runner.WorkflowEventHub()}
    runner._set_workflow_state(thread_id, state)

    workflow = Workflow(
        id="wf-res",
        name="Resume",
        format="nodes",
        nodes=[{"id": "node-1", "tool": "transcribe", "label": "node-1"}],
        edges=[],
    )
    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(workflow_id="wf-res", inputs={}),
        temp_db,
        resume_input=None,
        is_resume=True,
    )

    assert seen_inputs == [None], "resume must stream from the checkpoint"
    assert state["status"] == "completed"
    assert ("workflow_resumed" in [name for name, _ in tracker.calls])
    assert "workflow_started" not in [name for name, _ in tracker.calls]
    after = temp_db.get(Document, doc.id)
    assert after.status == Status.completed, (
        "resume-to-completion must finalize the run's documents"
    )


@pytest.mark.asyncio
async def test_resume_seeds_precompleted_exit_nodes(monkeypatch, tmp_path):
    """An exit node that finished BEFORE the pause never re-fires after
    resume; the missing-exit-node guard must not fail the resumed run."""
    from fichero_server.api.routes.workflow_execution.schemas import (
        ExecuteWorkflowRequest,
    )
    from fichero_server.models import Workflow

    thread_id = "thread-resume-seed"

    class _App:
        async def astream_events(self, *_a, **_k):
            # Only the still-pending exit node replays after resume.
            yield {"event": "on_chain_start", "name": "exit-b", "data": {}}
            yield {"event": "on_chain_end", "name": "exit-b", "data": {"output": {}}}

    checkpointer = _FakeCheckpointer(
        channel_values={"completed_nodes": ["exit-a"]}
    )
    db_obj = SimpleNamespace(path=tmp_path / "library.duckdb")
    runner, _tracker = _wire_runner(monkeypatch, _App(), checkpointer, db_obj)
    state = {"events": runner.WorkflowEventHub()}
    runner._set_workflow_state(thread_id, state)

    workflow = Workflow(
        id="wf-seed",
        name="Seed",
        format="nodes",
        nodes=[
            {"id": "src", "tool": "files", "label": "src"},
            {"id": "exit-a", "tool": "transcribe", "label": "exit-a"},
            {"id": "exit-b", "tool": "describe", "label": "exit-b"},
        ],
        edges=[
            {"source": "src", "target": "exit-a"},
            {"source": "src", "target": "exit-b"},
        ],
    )
    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(workflow_id="wf-seed", inputs={}),
        db_obj,
        resume_input=None,
        is_resume=True,
    )

    assert state["status"] == "completed", state.get("error")


@pytest.mark.asyncio
async def test_resume_endpoint_dispatches_background_thread(monkeypatch, tmp_path):
    """The endpoint registers the run, returns status=running immediately,
    and dispatches the background runner with is_resume=True."""
    from fichero_server.api.routes.workflow_execution import core
    from fichero_server.execution import runner
    from fichero_server.models import Workflow

    thread_id = "thread-resume-endpoint"
    dispatched = {}
    done = __import__("threading").Event()

    async def fake_run_in_background(**kwargs):
        dispatched.update(kwargs)
        done.set()

    class _FakeCkptCls:
        @classmethod
        def from_db_path(cls, _path):
            return _FakeCheckpointer(channel_values={"workflow_id": "wf-ep"})

    workflow = Workflow(
        id="wf-ep",
        name="Endpoint",
        format="nodes",
        nodes=[{"id": "n", "tool": "transcribe", "label": "n"}],
        edges=[],
    )

    class _FakeStore:
        def __init__(self, _db):
            pass

        def get(self, workflow_id):
            return workflow if workflow_id == "wf-ep" else None

    monkeypatch.setattr(
        "fichero_server.workflows.checkpointer.AsyncDuckDBCheckpointer",
        _FakeCkptCls,
    )
    monkeypatch.setattr(core, "WorkflowStore", _FakeStore)
    monkeypatch.setattr(
        core, "get_activity_tracker", lambda _p: _FakeActivityTracker()
    )
    monkeypatch.setattr(core, "_run_workflow_in_background", fake_run_in_background)

    db_obj = SimpleNamespace(path=tmp_path / "library.duckdb")
    try:
        response = await core.resume_workflow(thread_id, None, db=db_obj)
    finally:
        done.wait(timeout=5)
        runner._remove_workflow_state(thread_id)

    assert response.status == "running"
    assert dispatched.get("is_resume") is True
    assert dispatched.get("thread_id") == thread_id
    # The run is registered so /stream/{thread_id} and cancel can reach it.
    assert dispatched.get("resume_input") is None
