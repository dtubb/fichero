import asyncio
import contextlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from fichero_server.execution.batch import BatchManager, MAX_BATCH_CACHE_SIZE
from fichero_server.workflows.executor import (
    ProgressEventType,
    WorkflowExecutor,
)
from fichero_server.workflows.file_watcher import (
    FileWatcherManager,
    FilterMode,
    TriggerConfig,
    TriggerEvent,
)
from fichero_server.workflows.scheduler import (
    MAX_SCHEDULE_CACHE_SIZE,
    Schedule,
    ScheduleConfig,
    ScheduleStatus,
    ScheduleType,
    WorkflowScheduler,
)
from fichero_server.workflows.types import NodeDef, WorkflowDef


class SyncWorkflowStore:
    def __init__(self, workflow):
        self.workflow = workflow

    def get(self, workflow_id):
        if workflow_id == self.workflow.id:
            return self.workflow
        return None


def _workflow(workflow_id: str = "wf-1") -> WorkflowDef:
    return WorkflowDef(
        id=workflow_id,
        name="Regression Workflow",
        nodes=[NodeDef(id="node-1", tool="noop")],
        edges=[],
    )


@pytest.mark.asyncio
async def test_scheduler_sync_workflow_store_runs_due_schedule(tmp_path, monkeypatch):
    """#2130: scheduler must not await WorkflowStore.get()."""
    workflow = _workflow()
    scheduler = WorkflowScheduler(
        str(tmp_path / "scheduler.duckdb"),
        SyncWorkflowStore(workflow),
    )
    calls = []

    async def fake_execute_workflow(*, workflow, inputs):
        calls.append((workflow.id, inputs))
        return {"outputs": {"ok": True}}

    monkeypatch.setattr(
        "fichero_server.workflows.builder.execute_workflow",
        fake_execute_workflow,
    )

    schedule = await scheduler.create_schedule(
        name="run once",
        workflow_id=workflow.id,
        config=ScheduleConfig(
            schedule_type=ScheduleType.ONCE,
            run_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
        inputs={"x": 1},
    )

    await scheduler._execute_schedule(schedule.schedule_id)

    runs = await scheduler.get_schedule_runs(schedule.schedule_id)
    assert calls == [(workflow.id, {"x": 1})]
    assert runs[0].status == "completed"


@pytest.mark.asyncio
async def test_scheduler_uses_utc_aware_times_for_one_time_schedule(tmp_path):
    """#2134: next_run_at and created/updated timestamps are UTC-aware."""
    workflow = _workflow()
    scheduler = WorkflowScheduler(
        str(tmp_path / "scheduler_utc.duckdb"),
        SyncWorkflowStore(workflow),
    )

    schedule = await scheduler.create_schedule(
        name="utc run",
        workflow_id=workflow.id,
        config=ScheduleConfig(
            schedule_type=ScheduleType.ONCE,
            run_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )

    assert schedule.created_at.tzinfo == timezone.utc
    assert schedule.updated_at.tzinfo == timezone.utc
    assert schedule.next_run_at is not None
    assert schedule.next_run_at.tzinfo == timezone.utc


@pytest.mark.asyncio
async def test_scheduler_tracks_fire_and_forget_tasks(tmp_path, monkeypatch):
    """#2133: manual runs keep a strong reference to their background task."""
    workflow = _workflow()
    scheduler = WorkflowScheduler(
        str(tmp_path / "scheduler_tasks.duckdb"),
        SyncWorkflowStore(workflow),
    )
    hold = asyncio.Event()

    async def wait_forever(schedule, run):
        await hold.wait()

    monkeypatch.setattr(scheduler, "_execute_manual_run", wait_forever)
    schedule = await scheduler.create_schedule(
        name="manual",
        workflow_id=workflow.id,
        config=ScheduleConfig(
            schedule_type=ScheduleType.ONCE,
            run_at=datetime.now(timezone.utc) + timedelta(hours=1),
        ),
    )

    await scheduler.trigger_now(schedule.schedule_id)

    assert len(scheduler._bg_tasks) == 1
    task = next(iter(scheduler._bg_tasks))
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def test_scheduler_cache_is_bounded(tmp_path):
    """#2136: schedule cache cannot grow without bound."""
    workflow = _workflow()
    scheduler = WorkflowScheduler(
        str(tmp_path / "scheduler_cache.duckdb"),
        SyncWorkflowStore(workflow),
    )

    for index in range(MAX_SCHEDULE_CACHE_SIZE + 25):
        scheduler._remember_schedule(
            Schedule(
                schedule_id=f"schedule-{index}",
                name=f"schedule {index}",
                workflow_id=workflow.id,
                config=ScheduleConfig(schedule_type=ScheduleType.INTERVAL, interval_seconds=60),
                status=ScheduleStatus.ACTIVE,
            )
        )

    assert len(scheduler._schedules) == MAX_SCHEDULE_CACHE_SIZE
    assert "schedule-0" not in scheduler._schedules


@pytest.mark.asyncio
async def test_file_watcher_sync_workflow_store_trigger_executes(tmp_path, monkeypatch):
    """#2147: file watcher must not await WorkflowStore.get()."""
    workflow = _workflow()
    manager = FileWatcherManager(
        str(tmp_path / "watcher.duckdb"),
        SyncWorkflowStore(workflow),
    )
    monkeypatch.setattr(manager, "_setup_watcher", lambda trigger: None)
    executed = asyncio.Event()
    calls = []

    async def fake_execute_workflow(*, workflow, inputs):
        calls.append((workflow.id, inputs["file_path"]))
        executed.set()
        return {"outputs": {"ok": True}}

    monkeypatch.setattr(
        "fichero_server.workflows.builder.execute_workflow",
        fake_execute_workflow,
    )
    watched = tmp_path / "watched"
    watched.mkdir()
    source = watched / "in.txt"
    source.write_text("hello", encoding="utf-8")

    trigger = await manager.create_trigger(
        name="watch",
        workflow_id=workflow.id,
        config=TriggerConfig(
            watch_path=str(watched),
            recursive=False,
            events=[TriggerEvent.CREATED],
            filter_mode=FilterMode.GLOB,
            filter_pattern="*.txt",
            batch_delay_seconds=0.01,
        ),
        use_batch=False,
    )
    manager._pending_events[trigger.trigger_id] = [("created", str(source))]

    await manager._process_pending_events(trigger.trigger_id)
    await asyncio.wait_for(executed.wait(), timeout=1)

    assert calls == [(workflow.id, str(source))]


def _a_run_that_ends(status: str, error: str | None = None):
    """Stands in for `runner.start_run`: each batch item is a run of the runner (#5374); this one
    writes the run's record as the runner would and ends at once."""
    import threading

    async def start_run(db, workflow, request, thread_id, *, parent_job=None):
        from fichero_server.workflows.activity import get_activity_tracker

        store = get_activity_tracker(str(db.path)).store
        await store.save_workflow_run(thread_id=thread_id, workflow_id=workflow.id,
                                      workflow_name=workflow.name, status=status)
        if error:
            await store.update_workflow_run(thread_id, status=status, error=error)
        finished = threading.Event()
        finished.set()
        return finished

    return start_run


@pytest.mark.asyncio
async def test_batch_item_execution_accepts_string_db_path(db, monkeypatch):
    """#2131: batch execution must wrap a string db_path before reading its parent (the library
    its runs belong to). An item whose run completes is a completed item."""
    manager = BatchManager(str(db.path))
    batch = await manager.create_batch(workflow_id="wf-1", items_inputs=[{"value": 1}])
    monkeypatch.setattr("fichero_server.execution.runner.start_run", _a_run_that_ends("completed"))

    events = [
        event.event_type
        async for event in manager.execute_batch(batch.batch_id, SyncWorkflowStore(_workflow()))
    ]

    persisted = await manager.get_batch(batch.batch_id)
    assert "item_completed" in events
    assert persisted is not None
    assert persisted.completed_items == 1


@pytest.mark.asyncio
async def test_batch_records_document_completion_failure(db, monkeypatch):
    """A run that finished its graph but failed to persist its documents is not a completed batch
    item: the item fails with the run's own reason (the runner completes the documents, #5374)."""
    manager = BatchManager(str(db.path))
    batch = await manager.create_batch(workflow_id="wf-1", items_inputs=[{"value": 1}])
    monkeypatch.setattr("fichero_server.execution.runner.start_run",
                        _a_run_that_ends("failed", "Document completion failed: document write failed"))

    events = [
        event.event_type
        async for event in manager.execute_batch(batch.batch_id, SyncWorkflowStore(_workflow()))
    ]
    persisted = await manager.get_batch(batch.batch_id)

    assert "item_failed" in events
    assert persisted is not None
    assert persisted.status.value == "failed"
    assert persisted.items[0].status.value == "failed"
    assert "Document completion failed: document write failed" == persisted.items[0].error


def test_batch_cache_is_bounded(tmp_path):
    """#2136: batch cache cannot grow without bound."""
    manager = BatchManager(str(tmp_path / "batch_cache.duckdb"))

    for index in range(MAX_BATCH_CACHE_SIZE + 25):
        batch = SimpleNamespace(batch_id=f"batch-{index}")
        manager._remember_batch(batch)

    assert len(manager._batches) == MAX_BATCH_CACHE_SIZE
    assert "batch-0" not in manager._batches


@pytest.mark.asyncio
async def test_executor_node_error_surfaces_instead_of_fake_retry(monkeypatch):
    """#2132: transient-looking node errors are not silently cleared."""

    class FakeGraph:
        async def astream(self, current_state, stream_mode=None, subgraphs=False):
            yield (
                (),
                {
                    "node-1": {
                        "current_node": "node-1",
                        "error": "transient boom",
                    }
                },
            )

    monkeypatch.setattr(
        "fichero_server.workflows.executor.build_graph",
        lambda workflow: FakeGraph(),
    )
    executor = WorkflowExecutor(_workflow(), max_retries=3)
    state = executor._create_initial_state({})

    final_state = await executor._execute_with_pregel(state)

    assert final_state["error"] == "Node node-1 failed: transient boom"
    assert final_state["retry_counts"]["node-1"] == 1
    event = await executor._event_queue.get()
    assert event.event_type == ProgressEventType.NODE_STARTED
    event = await executor._event_queue.get()
    assert event.event_type == ProgressEventType.NODE_FAILED
