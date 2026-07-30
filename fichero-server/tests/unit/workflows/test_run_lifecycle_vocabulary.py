"""#4316: paused/accepted must not be dead-end states.

- Pause → Cancel works: cancelling a paused run (whose worker coroutine
  already returned) settles it directly — run row → cancelled, processing
  documents released.
- DELETE works on paused/accepted runs (previously 409 forever).
- Recovery sweeps EVERY non-terminal status past the cutoff, but never a run
  this process is actively tracking — reopening a library mid-run must not
  flap a live run's status (F5 regression).
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.db import Database
from fichero_server.models import Document, Status
from fichero_server.workflows.activity_store import ActivityStore


@pytest.fixture
def temp_db():
    tmpdir = tempfile.mkdtemp()
    db = Database(Path(tmpdir) / "fichero.duckdb")
    yield db
    db.close()
    shutil.rmtree(tmpdir)


async def _save_run(store: ActivityStore, thread_id: str, status: str, minutes_old=5):
    await store.save_workflow_run(
        thread_id=thread_id,
        workflow_id="wf-1",
        workflow_name="Transcribe",
        status=status,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=minutes_old),
    )


class TestRecoverySweep:
    def test_sweeps_every_non_terminal_status(self, tmp_path):
        store = ActivityStore(str(tmp_path / "lib.duckdb"))
        asyncio.run(_save_run(store, "t-running", "running"))
        asyncio.run(_save_run(store, "t-accepted", "accepted"))
        asyncio.run(_save_run(store, "t-paused", "paused"))
        asyncio.run(_save_run(store, "t-done", "completed"))

        recovered = asyncio.run(store.recover_stale_runs(max_age_hours=0))
        assert recovered == 3

        for tid in ("t-running", "t-accepted", "t-paused"):
            run = asyncio.run(store.get_workflow_run(tid))
            assert run.status == "failed", f"{tid} not swept"
            assert run.error
        assert asyncio.run(store.get_workflow_run("t-done")).status == "completed"

    def test_sweep_excludes_live_runs(self, tmp_path):
        store = ActivityStore(str(tmp_path / "lib.duckdb"))
        asyncio.run(_save_run(store, "t-live", "running"))
        asyncio.run(_save_run(store, "t-zombie", "running"))

        recovered = asyncio.run(
            store.recover_stale_runs(
                max_age_hours=0, exclude_thread_ids=("t-live",)
            )
        )
        assert recovered == 1
        assert asyncio.run(store.get_workflow_run("t-live")).status == "running"
        assert asyncio.run(store.get_workflow_run("t-zombie")).status == "failed"

    def test_library_reopen_does_not_flap_live_run(self, tmp_path, monkeypatch):
        """F5 regression: the tracker-creation sweep must exclude the runs the
        in-process runner registry says are live."""
        from fichero_server.execution import runner
        from fichero_server.workflows import activity

        db_path = str(tmp_path / "lib.duckdb")
        store = ActivityStore(db_path)
        asyncio.run(_save_run(store, "t-live-registry", "running"))

        runner._set_workflow_state(
            "t-live-registry",
            {"status": "running", "events": runner.WorkflowEventHub()},
        )
        try:
            tracker = SimpleNamespace(store=store)
            asyncio.run(activity._recover_stale_runs_bg(tracker, db_path))
            run = asyncio.run(store.get_workflow_run("t-live-registry"))
            assert run.status == "running", (
                "reopening a library mid-run must not flip a live run to failed"
            )
        finally:
            runner._remove_workflow_state("t-live-registry")

    def test_store_construction_never_flips_rows(self, tmp_path):
        db_path = str(tmp_path / "lib.duckdb")
        store = ActivityStore(db_path)
        asyncio.run(_save_run(store, "t-running", "running"))
        # Constructing a SECOND store over the same DB (library reopen) must
        # not touch statuses — the cutoff-less init sweep is gone (#4316).
        ActivityStore(db_path)
        assert asyncio.run(store.get_workflow_run("t-running")).status == "running"


class _FakeCheckpointTuple:
    def __init__(self, doc_id):
        self.checkpoint = {
            "id": "ckpt-1",
            "channel_values": {"outputs": {"src": {"documents": [{"id": doc_id}]}}},
        }


def _isolated_tracker(monkeypatch, temp_db):
    """A tracker whose store is a plain ActivityStore, wired into the threads
    module so no test goes through get_activity_tracker — that would schedule
    the zero-cutoff recovery sweep on the test loop and race these seeds."""
    from fichero_server.api.routes.workflow_execution import threads

    store = ActivityStore(str(temp_db.path))
    tracker = SimpleNamespace(
        store=store,
        workflow_deleted=lambda **_kwargs: None,
        workflow_cancelled=lambda **_kwargs: None,
    )
    monkeypatch.setattr(threads, "get_activity_tracker", lambda _p: tracker)
    return store


class TestCancelPausedRun:
    @pytest.mark.asyncio
    async def test_pause_then_cancel_settles_run_and_documents(
        self, temp_db, monkeypatch
    ):
        from fichero_server.api.routes.workflow_execution import threads
        from fichero_server.execution import runner

        doc = Document(name="p.png", path="/tmp/p.png", status=Status.processing)
        temp_db.save(doc)

        store = _isolated_tracker(monkeypatch, temp_db)
        await _save_run(store, "t-paused-cancel", "paused")
        runner._set_workflow_state(
            "t-paused-cancel",
            {"status": "paused", "events": runner.WorkflowEventHub()},
        )

        class _FakeCkpt:
            async def aget_tuple(self, _config):
                return _FakeCheckpointTuple(doc.id)

        monkeypatch.setattr(
            "fichero_server.workflows.checkpointer."
            "AsyncDuckDBCheckpointer.from_db_path",
            classmethod(lambda _cls, _path: _FakeCkpt()),
        )

        try:
            result = await threads.cancel_workflow("t-paused-cancel", db=temp_db)
        finally:
            runner._remove_workflow_state("t-paused-cancel")

        assert result.status == "cancelled"
        run = await store.get_workflow_run("t-paused-cancel")
        assert run.status == "cancelled"
        after = temp_db.get(Document, doc.id)
        assert after.status == Status.pending, "paused→cancel must free documents"

    @pytest.mark.asyncio
    async def test_cancel_paused_without_registry_state(self, temp_db, monkeypatch):
        """A paused run from a previous process (no registry entry, no
        checkpoint yet) is still cancellable — the pre-checkpoint dead end."""
        from fichero_server.api.routes.workflow_execution import threads

        store = _isolated_tracker(monkeypatch, temp_db)
        await _save_run(store, "t-paused-orphan", "paused")

        class _FakeCkpt:
            async def aget_tuple(self, _config):
                return None  # paused before the first checkpoint

        monkeypatch.setattr(
            "fichero_server.workflows.checkpointer."
            "AsyncDuckDBCheckpointer.from_db_path",
            classmethod(lambda _cls, _path: _FakeCkpt()),
        )

        result = await threads.cancel_workflow("t-paused-orphan", db=temp_db)
        assert result.status == "cancelled"
        run = await store.get_workflow_run("t-paused-orphan")
        assert run.status == "cancelled"


class TestDeletePausedRun:
    @pytest.mark.asyncio
    async def test_delete_paused_run_succeeds(self, temp_db, monkeypatch):
        """Previously DELETE 409'd on paused — a run paused before its first
        checkpoint was stuck forever."""
        from fichero_server.api.routes.workflow_execution import threads

        store = _isolated_tracker(monkeypatch, temp_db)
        await _save_run(store, "t-paused-delete", "paused")

        class _FakeCkpt:
            async def aget_tuple(self, _config):
                return None

            async def adelete_thread(self, _thread_id):
                return 0

        monkeypatch.setattr(
            "fichero_server.workflows.checkpointer."
            "AsyncDuckDBCheckpointer.from_db_path",
            classmethod(lambda _cls, _path: _FakeCkpt()),
        )

        result = await threads.delete_thread("t-paused-delete", db=temp_db)
        assert "deleted" in result.message
        run = await store.get_workflow_run("t-paused-delete")
        assert run.status == "deleted"

    @pytest.mark.asyncio
    async def test_delete_running_run_still_409s(self, temp_db, monkeypatch):
        from fastapi import HTTPException

        from fichero_server.api.routes.workflow_execution import threads

        store = _isolated_tracker(monkeypatch, temp_db)
        await _save_run(store, "t-running-delete", "running")

        class _FakeCkpt:
            async def aget_tuple(self, _config):
                return None

        monkeypatch.setattr(
            "fichero_server.workflows.checkpointer."
            "AsyncDuckDBCheckpointer.from_db_path",
            classmethod(lambda _cls, _path: _FakeCkpt()),
        )

        with pytest.raises(HTTPException) as exc:
            await threads.delete_thread("t-running-delete", db=temp_db)
        assert exc.value.status_code == 409
