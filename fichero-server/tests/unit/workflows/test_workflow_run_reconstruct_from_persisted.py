"""#2624: persisted run snapshot is the source of truth.

The EPIC requires that a run can be fully reconstructed from persisted state
WITHOUT an active SSE connection — streaming is live acceleration, not the
record. These tests persist a run with one ActivityStore, then open a FRESH
store on the same DB (simulating an engine restart / a client that never held
the stream) and prove the terminal status, timing, snapshot, error, and
progress timeline all reconstruct. Covers the failure modes the EPIC calls
out: runs stuck at 0%, stale logs, and cancellation/error 'visually running'.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from fichero_server.workflows.activity_store import ActivityStore


async def _persist_completed_run(store: ActivityStore) -> tuple[datetime, datetime]:
    started = datetime(2026, 6, 27, 9, 0, tzinfo=timezone.utc)
    completed = datetime(2026, 6, 27, 9, 5, tzinfo=timezone.utc)
    await store.save_workflow_run(
        thread_id="thread-rec",
        workflow_id="wf-rec",
        workflow_name="Reconstructable Run",
        execution_log="started\n",
        workflow_snapshot={"nodes": [{"id": "t", "tool": "transcribe"}], "edges": []},
        node_name_map={"t": "Transcribe"},
        started_at=started,
        status="running",
    )
    await store.update_workflow_run(
        thread_id="thread-rec",
        status="completed",
        execution_log="started\ndone\n",
        completed_at=completed,
        progress_timeline={"events": [{"event": "node_end", "node_id": "t"}]},
    )
    return started, completed


@pytest.mark.asyncio
async def test_terminal_run_reconstructs_from_fresh_store_without_sse(tmp_path: Path):
    db_path = tmp_path / "activity.duckdb"
    started, completed = await _persist_completed_run(ActivityStore(str(db_path)))

    # Fresh store, same DB — no in-memory tracker, no live stream.
    reopened = ActivityStore(str(db_path))
    run = await reopened.get_workflow_run("thread-rec")

    assert run is not None, "persisted run must reconstruct without SSE"
    assert run.status == "completed"  # terminal status survives
    # Timing reconstructs. The store round-trips timestamps as naive-local, so
    # assert the tz-representation-independent invariant: both present, ordered,
    # and the 5-minute duration preserved (stable start time per the EPIC).
    assert run.started_at is not None and run.completed_at is not None
    assert run.completed_at >= run.started_at
    assert (run.completed_at - run.started_at) == (completed - started)
    # Snapshot + step structure are the source of truth for replay.
    assert run.workflow_snapshot["nodes"][0]["tool"] == "transcribe"
    assert run.node_name_map == {"t": "Transcribe"}
    assert run.progress_timeline["events"][0]["event"] == "node_end"


@pytest.mark.asyncio
async def test_errored_run_preserves_error_and_terminal_status(tmp_path: Path):
    """A failed/cancelled run must not reconstruct as 'running' (EPIC: stuck-running)."""
    db_path = tmp_path / "activity.duckdb"
    store = ActivityStore(str(db_path))
    await store.save_workflow_run(
        thread_id="thread-err",
        workflow_id="wf-err",
        workflow_name="Failing Run",
        execution_log="boom\n",
        started_at=datetime(2026, 6, 27, 10, 0, tzinfo=timezone.utc),
    )
    await store.update_workflow_run(
        thread_id="thread-err",
        status="error",
        error="provider quota exceeded",
        completed_at=datetime(2026, 6, 27, 10, 1, tzinfo=timezone.utc),
    )

    run = await ActivityStore(str(db_path)).get_workflow_run("thread-err")
    assert run is not None
    assert run.status == "error"  # not silently 'running'
    assert run.error == "provider quota exceeded"
    assert run.completed_at is not None


@pytest.mark.asyncio
async def test_unknown_thread_reconstructs_to_none(tmp_path: Path):
    store = ActivityStore(str(tmp_path / "activity.duckdb"))
    assert await store.get_workflow_run("no-such-thread") is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
