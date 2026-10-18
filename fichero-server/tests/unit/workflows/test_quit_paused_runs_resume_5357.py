"""#5357 `activity.run.quit-pauses`: a run the quit paused carries on at the next launch; a run a person paused does not."""
import asyncio

from fichero_server.execution import runner
from fichero_server.workflows import activity
from fichero_server.workflows.activity_store import ActivityStore


def _save(store, thread_id, status="paused", error=None):
    asyncio.run(store.save_workflow_run(thread_id=thread_id, workflow_id="w", workflow_name="W", python_code="",
                                        execution_log="", status=status))
    if error:
        asyncio.run(store.update_workflow_run(thread_id, error=error))


def test_quit_records_the_pause_with_its_reason(tmp_path, monkeypatch):
    from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer

    async def go():
        cp = AsyncDuckDBCheckpointer.from_db_path(db_path)
        await cp.aput({"configurable": {"thread_id": "r", "checkpoint_ns": ""}},
                      {"id": "c1", "type": "checkpoint", "channel_values": {}, "channel_versions": {},
                       "versions_seen": {}}, {"source": "t", "step": 1, "writes": {}}, {})

    db_path = str(tmp_path / "fichero.duckdb")
    store = ActivityStore(db_path)
    _save(store, "r", status="running")
    asyncio.run(go())
    monkeypatch.setattr(runner, "_running_workflows", {"r": {"status": "running", "db_path": db_path}})
    assert asyncio.run(runner.pause_live_runs_for_shutdown()) == 1
    run = asyncio.run(store.get_workflow_run("r"))
    assert (run.status, run.error) == ("paused", runner.QUIT_PAUSED_ERROR)


def test_launch_resumes_only_the_runs_the_quit_paused(tmp_path, monkeypatch):
    db_path = str(tmp_path / "fichero.duckdb")
    store = ActivityStore(db_path)
    _save(store, "by-quit", error=runner.QUIT_PAUSED_ERROR)
    _save(store, "by-person")
    resumed = []

    async def fake_resume(thread_id, request=None, db=None):
        resumed.append((thread_id, db))

    monkeypatch.setattr("fichero_server.api.routes.workflow_execution.core.resume_workflow", fake_resume)
    assert asyncio.run(activity.resume_quit_paused_runs(store, "DB")) == ["by-quit"]
    assert resumed == [("by-quit", "DB")]
    # the marker is cleared, so a later pause by the person is not taken for a quit
    assert asyncio.run(store.get_workflow_run("by-quit")).error != runner.QUIT_PAUSED_ERROR


def test_a_resume_that_fails_leaves_the_run_paused_and_says_why(tmp_path, monkeypatch):
    db_path = str(tmp_path / "fichero.duckdb")
    store = ActivityStore(db_path)
    _save(store, "r", error=runner.QUIT_PAUSED_ERROR)

    async def boom(*a, **k):
        raise RuntimeError("no checkpoint")

    monkeypatch.setattr("fichero_server.api.routes.workflow_execution.core.resume_workflow", boom)
    assert asyncio.run(activity.resume_quit_paused_runs(store, "DB")) == []
    run = asyncio.run(store.get_workflow_run("r"))
    assert run.status == "paused" and "no checkpoint" in run.error
