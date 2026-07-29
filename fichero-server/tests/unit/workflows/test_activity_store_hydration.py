from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from fichero_server.workflows.activity_store import ActivityStore


@pytest.mark.asyncio
async def test_get_workflow_run_hydrates_progress_timeline_from_persisted_events(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "activity.duckdb"
    store = ActivityStore(str(db_path))

    started_at = datetime(2026, 6, 25, 12, 0, tzinfo=timezone.utc)
    completed_at = datetime(2026, 6, 25, 12, 3, tzinfo=timezone.utc)

    await store.save_workflow_run(
        thread_id="thread-2635",
        workflow_id="wf-2635",
        workflow_name="Hydration Workflow",
        execution_log="Workflow completed\n",
        started_at=started_at,
    )
    await store.update_workflow_run(
        thread_id="thread-2635",
        status="completed",
        execution_log="Workflow completed\n",
        progress_timeline={
            "events": [
                {
                    "event": "node_begin",
                    "thread_id": "thread-2635",
                    "workflow_id": "wf-2635",
                    "timestamp": "2026-06-25T12:00:00+00:00",
                    "node_id": "catalogue",
                    "data": {"node": "catalogue"},
                },
                {
                    "event": "file_start",
                    "thread_id": "thread-2635",
                    "workflow_id": "wf-2635",
                    "timestamp": "2026-06-25T12:00:05+00:00",
                    "node_id": "catalogue",
                    "file_path": "/tmp/page-1.txt",
                    "file_index": 1,
                    "file_total": 1,
                    "data": {
                        "node_id": "catalogue",
                        "file_path": "/tmp/page-1.txt",
                        "file_index": 1,
                        "file_total": 1,
                        "document_id": "doc-1",
                        "page_id": "page-1",
                        "display_name": "Page 1",
                        "sequence": 1,
                    },
                },
                {
                    "event": "file_complete",
                    "thread_id": "thread-2635",
                    "workflow_id": "wf-2635",
                    "timestamp": "2026-06-25T12:00:35+00:00",
                    "node_id": "catalogue",
                    "file_path": "/tmp/page-1.txt",
                    "file_index": 1,
                    "file_total": 1,
                    "data": {
                        "node_id": "catalogue",
                        "file_path": "/tmp/page-1.txt",
                        "file_index": 1,
                        "file_total": 1,
                        "document_id": "doc-1",
                        "page_id": "page-1",
                        "display_name": "Page 1",
                        "sequence": 1,
                    },
                },
                {
                    "event": "node_end",
                    "thread_id": "thread-2635",
                    "workflow_id": "wf-2635",
                    "timestamp": "2026-06-25T12:01:00+00:00",
                    "node_id": "catalogue",
                    "data": {"node": "catalogue", "duration_ms": 60_000},
                },
                {
                    "event": "complete",
                    "thread_id": "thread-2635",
                    "workflow_id": "wf-2635",
                    "timestamp": "2026-06-25T12:03:00+00:00",
                    "data": {
                        "checkpoint_id": "ckpt-1",
                        "duration_ms": 180_000,
                    },
                },
            ]
        },
        duration_ms=180_000,
        completed_at=completed_at,
    )

    run = await store.get_workflow_run("thread-2635")
    assert run is not None
    timeline = run.progress_timeline
    assert timeline is not None

    assert timeline["events"][1]["document_id"] == "doc-1"
    assert timeline["events"][1]["page_id"] == "page-1"
    assert timeline["events"][1]["display_name"] == "Page 1"
    assert timeline["events"][1]["sequence"] == 1

    assert timeline["steps"][0]["node_id"] == "catalogue"
    assert timeline["steps"][0]["status"] == "success"
    assert timeline["steps"][1]["type"] == "file"
    assert timeline["steps"][1]["document_id"] == "doc-1"
    assert timeline["steps"][1]["page_id"] == "page-1"
    assert timeline["steps"][1]["status"] == "success"

    assert timeline["nodes"]["catalogue"]["status"] == "success"
    assert timeline["terminal_status"] == "completed"
    assert timeline["execution_log"] == "Workflow completed\n"
