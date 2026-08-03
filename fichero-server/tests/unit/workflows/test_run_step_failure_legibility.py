"""#4284: a run that dies mid-node must say WHICH step died.

Before this, the runner appended a ``progress_timeline`` entry with
``status="running"`` when a node started and only ever settled it on
``on_chain_end``. A run that raised inside a node — the common case, and the
one Daniel actually hits — left that entry at 'running' forever. The record
then had a step claiming to be running for a run that ended, and the step that
broke looked exactly like every step that never started: nothing distinguished
them.

These tests drive the REAL background runner with a stubbed graph so the
assertion is on what actually gets persisted, not on a helper in isolation.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.models import Document


@pytest.fixture
def temp_db():
    from fichero_server.db import Database

    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "fichero.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir)


class _RecordingActivityStore:
    """Keeps every update_workflow_run payload so tests can read the last one."""

    def __init__(self):
        self.updates: list[dict] = []

    async def save_workflow_run(self, **_kwargs):
        return None

    async def update_workflow_run(self, **kwargs):
        self.updates.append(kwargs)
        return None


class _RecordingActivityTracker:
    def __init__(self):
        self.store = _RecordingActivityStore()

    def __getattr__(self, _name):
        return lambda **_kwargs: None


class _FakeCheckpointer:
    async def aget_tuple(self, _config):
        return SimpleNamespace(checkpoint={"id": "ckpt-1", "channel_values": {}})


class _AppThatDiesInsideNode:
    """Starts node-1, then raises the way a provider failure does."""

    async def astream_events(self, _initial_state, *_args, **_kwargs):
        yield {"event": "on_chain_start", "name": "node-1", "data": {}}
        raise RuntimeError("provider returned 401")


def _last_timeline(tracker) -> dict:
    for update in reversed(tracker.store.updates):
        timeline = update.get("progress_timeline")
        if timeline is not None:
            return timeline
    raise AssertionError("the run persisted no progress_timeline at all")


async def _drive_failing_run(monkeypatch, temp_db, thread_id: str):
    from fichero_server.api.routes.workflow_execution.schemas import (
        ExecuteWorkflowRequest,
    )
    from fichero_server.execution import runner
    from fichero_server.models import Workflow

    doc = Document(name="page.png", path="/tmp/page.png")
    temp_db.save(doc)

    tracker = _RecordingActivityTracker()
    events = runner.WorkflowEventHub()
    runner._set_workflow_state(thread_id, {"events": events})
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
        lambda *_a, **_k: (_AppThatDiesInsideNode(), _FakeCheckpointer()),
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.get_database",
        lambda _library_path: temp_db,
    )
    monkeypatch.setattr(
        "fichero_server.db.manager.db_manager.close_current_thread",
        lambda: None,
    )

    workflow = Workflow(
        id="wf-fail",
        name="Dies",
        format="nodes",
        nodes=[
            {"id": "node-1", "tool": "transcribe", "label": "node-1"},
            {"id": "node-2", "tool": "transcribe", "label": "node-2"},
        ],
        edges=[{"source": "node-1", "target": "node-2"}],
    )
    await runner._run_workflow_in_background(
        thread_id,
        workflow,
        ExecuteWorkflowRequest(workflow_id="wf-fail", inputs={}),
        temp_db,
    )
    return tracker


@pytest.mark.asyncio
async def test_failed_run_leaves_no_step_claiming_to_be_running(
    monkeypatch, temp_db
):
    tracker = await _drive_failing_run(monkeypatch, temp_db, "thread-dies")
    timeline = _last_timeline(tracker)

    steps = timeline.get("steps", [])
    assert steps, (
        "the run must have recorded at least one step — an empty timeline "
        "would make this assertion vacuous (#4487)"
    )
    still_running = [s for s in steps if s.get("status") == "running"]
    assert not still_running, (
        f"a finished run must leave no step marked running, found: {still_running}"
    )


@pytest.mark.asyncio
async def test_the_step_that_died_is_recorded_as_failed_with_the_error(
    monkeypatch, temp_db
):
    tracker = await _drive_failing_run(monkeypatch, temp_db, "thread-dies-2")
    timeline = _last_timeline(tracker)

    node_1 = [s for s in timeline["steps"] if s.get("node_id") == "node-1"]
    assert node_1, "the node that started must appear in the timeline"
    entry = node_1[-1]
    assert entry["status"] == "failed"
    assert entry["terminated_by_run"] is True
    assert "401" in str(entry.get("error", "")), (
        "the failing step must carry the run's error, not just a bare status"
    )


@pytest.mark.asyncio
async def test_the_step_after_the_failure_reads_back_as_not_run(
    monkeypatch, temp_db
):
    """node-2 never started. It must be reported, and reported as not_run —
    distinct from node-1, which ran and failed."""
    from fichero_server.workflows.run_steps import (
        STEP_FAILED,
        STEP_NOT_RUN,
        build_run_steps,
    )

    tracker = await _drive_failing_run(monkeypatch, temp_db, "thread-dies-3")
    timeline = _last_timeline(tracker)

    steps = build_run_steps(
        planned_nodes=[
            {"node_id": "node-1", "node_name": "node-1", "tool": "transcribe"},
            {"node_id": "node-2", "node_name": "node-2", "tool": "transcribe"},
        ],
        progress_timeline=timeline,
        artifacts=[],
    )
    assert len(steps) == 2, "a 2-step workflow yields 2 records however it ended"
    by_id = {s.node_id: s for s in steps}
    assert by_id["node-1"].status == STEP_FAILED
    assert by_id["node-1"].produced_nothing is True
    assert by_id["node-2"].status == STEP_NOT_RUN
    assert by_id["node-2"].produced_nothing is False
