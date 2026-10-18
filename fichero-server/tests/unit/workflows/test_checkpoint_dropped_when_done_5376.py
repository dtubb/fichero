"""#5376 `activity.run.checkpoints-pruned`: a run that finished clean keeps its account on its record and its checkpoint is
deleted; a run that did not keeps its checkpoint, and the account still reads the same afterwards."""
import asyncio
from types import SimpleNamespace
from uuid import uuid4

from fichero_server.workflows import run_account as accounts
from fichero_server.workflows.activity_store import ActivityStore
from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer


def _run(tmp_path, status):
    db_path = str(tmp_path / "fichero.duckdb")
    store = ActivityStore(db_path)

    async def setup():
        await store.save_workflow_run(thread_id="t", workflow_id="w", workflow_name="W", python_code="",
                                      execution_log="", status=status)
        await store.update_workflow_run("t", status=status, progress_timeline={"events": []})
        cp = AsyncDuckDBCheckpointer.from_db_path(db_path)
        await cp.aput({"configurable": {"thread_id": "t", "checkpoint_ns": ""}},
                      {"id": str(uuid4()), "type": "checkpoint", "channel_values": {}, "channel_versions": {},
                       "versions_seen": {}}, {"source": "t", "step": 1, "writes": {}}, {})
        return cp

    return db_path, store, asyncio.run(setup())


def _left(db_path):
    cp = AsyncDuckDBCheckpointer.from_db_path(db_path)
    got = asyncio.run(cp.aget_tuple({"configurable": {"thread_id": "t", "checkpoint_ns": ""}}))
    cp.conn.close()
    return got


def test_a_clean_finish_keeps_its_account_and_drops_the_checkpoint(tmp_path):
    db_path, store, cp = _run(tmp_path, "completed")
    db = SimpleNamespace(path=db_path)
    assert asyncio.run(accounts.drop_finished_checkpoint(db, "t")) is True
    assert _left(db_path) is None
    run = asyncio.run(store.get_workflow_run("t"))
    assert run.progress_timeline[accounts.KEPT_ACCOUNT]["state"] == "done"
    accounts._FINISHED.clear()
    # the account reads from the record now that there is no checkpoint
    read = asyncio.run(accounts.run_account(db, "t", run=run))
    assert read.state == "done" and read.model_dump(mode="json") == run.progress_timeline[accounts.KEPT_ACCOUNT]


def test_a_run_that_is_not_done_keeps_its_checkpoint(tmp_path):
    for status in ("paused", "failed", "running"):
        db_path, _, _ = _run(tmp_path / status if (tmp_path / status).mkdir() is None else tmp_path, status)
        assert asyncio.run(accounts.drop_finished_checkpoint(SimpleNamespace(path=db_path), "t")) is False
        assert _left(db_path) is not None


def test_a_finish_with_a_failed_page_keeps_its_checkpoint(tmp_path, monkeypatch):
    db_path, _, _ = _run(tmp_path, "completed")

    async def with_a_failure(*a, **k):
        return accounts.RunAccount(state="done", pages_total=2, pages_done=1, pages_failed=1)

    monkeypatch.setattr(accounts, "run_account", with_a_failure)
    assert asyncio.run(accounts.drop_finished_checkpoint(SimpleNamespace(path=db_path), "t")) is False
    assert _left(db_path) is not None
