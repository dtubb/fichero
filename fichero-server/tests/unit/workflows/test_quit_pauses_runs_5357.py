"""Quit pauses the runs in flight (#5357, `activity.run.quit-pauses`): a live run with a checkpoint on disk is recorded
paused, so the next open leaves it for Resume; one with no checkpoint yet is left to the reopen sweep."""
import asyncio

from fichero_server.execution import runner
from fichero_server.workflows.activity_store import ActivityStore
from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer


import pytest


@pytest.fixture(autouse=True)
def _no_boundary_wait(monkeypatch):
    """The workers here are stand-ins that never reach a boundary; the wait has its own tests below."""
    monkeypatch.setattr(runner, "BOUNDARY_GRACE_SECONDS", 0)


def _save(store, thread_id, status="running"):
    asyncio.run(store.save_workflow_run(thread_id=thread_id, workflow_id="w", workflow_name="W", python_code="",
                                        execution_log="", status=status))


def _checkpoint(db_path, thread_id):
    async def go():
        cp = AsyncDuckDBCheckpointer.from_db_path(db_path)
        await cp.aput({"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
                      {"id": "c1", "type": "checkpoint", "channel_values": {}, "channel_versions": {},
                       "versions_seen": {}}, {"source": "t", "step": 1, "writes": {}}, {})
    asyncio.run(go())


def test_a_live_run_with_a_checkpoint_is_paused_and_one_without_is_not(tmp_path, monkeypatch):
    db_path = str(tmp_path / "fichero.duckdb")
    store = ActivityStore(db_path)
    _save(store, "with-cp")
    _save(store, "no-cp")
    _save(store, "done", status="completed")
    _checkpoint(db_path, "with-cp")
    monkeypatch.setattr(runner, "_running_workflows", {
        "with-cp": {"status": "running", "db_path": db_path},
        "no-cp": {"status": "accepted", "db_path": db_path},
        "done": {"status": "completed", "db_path": db_path},
        "bare": {"status": "running"}})

    from fichero_server.execution.cancellation import clear_pause, pause_requested

    opened = []
    real = AsyncDuckDBCheckpointer.from_db_path
    monkeypatch.setattr(AsyncDuckDBCheckpointer, "from_db_path",
                        classmethod(lambda cls, p, **k: opened.append(real(p, **k)) or opened[-1]))
    assert asyncio.run(runner.pause_live_runs_for_shutdown()) == 1
    # the run is asked to pause, so it settles as paused through its own path at its next boundary ...
    assert pause_requested("with-cp") and not pause_requested("no-cp")
    clear_pause("with-cp")
    # ... and one connection was opened for the library, then closed
    assert len(opened) == 1
    import duckdb
    import pytest
    with pytest.raises(duckdb.ConnectionException):
        opened[0].conn.execute("select 1")
    status = lambda t: asyncio.run(store.get_workflow_run(t)).status  # noqa: E731
    assert (status("with-cp"), status("no-cp"), status("done")) == ("paused", "running", "completed")


def test_the_engine_pauses_before_it_closes_the_streams():
    import inspect

    from fichero_server.api import main

    src = inspect.getsource(main)
    assert src.index("pause_live_runs_for_shutdown()") < src.index("close_all_event_hubs_for_shutdown()")
