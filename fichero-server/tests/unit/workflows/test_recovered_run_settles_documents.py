"""#4379: a run whose PROCESS died must still release its documents.

Every other terminal path settles documents in-process, because the run's
document set is in memory when the run ends. A run whose process was killed
(crash, OOM, app restart, or a dev-loop reload killing the uvicorn worker
mid-run) never reaches that moment: the recovery sweep flipped the
``workflow_runs`` row to 'failed' with raw SQL and stopped there, so every
document the run left at ``Status.processing`` stayed there forever — a
permanent spinner on a document that could never be re-run.

``completion.py`` states the contract as "EVERY terminal path must call this
(#4315)". Process death was the one terminal path where it was skipped, and it
is the path that produced the reported incident. These tests pin that the sweep
now settles documents too, that it settles EXACTLY the dead run's set, and that
it never touches a run this process is still executing.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from fichero_server.db import Database
from fichero_server.models import Document, Status
from fichero_server.workflows import activity
from fichero_server.workflows.activity_store import ActivityStore
from fichero_server.workflows.checkpointer import AsyncDuckDBCheckpointer


@pytest.fixture(autouse=True)
def _no_default_workflow_seeding(monkeypatch):
    """`db_manager.get_database` seeds shipped presets; irrelevant here."""
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")


@pytest.fixture
def library(tmp_path: Path):
    """A real `.fichero` package, because the sweep resolves the library
    ``Database`` from the enclosing package directory of its ``db_path``.
    """
    package = tmp_path / "recovery.fichero"
    package.mkdir()
    db_path = str(package / "fichero.duckdb")
    db = Database(Path(db_path))
    try:
        yield SimpleNamespace(package=package, db_path=db_path, db=db)
    finally:
        db.close()


@pytest.fixture
def store(library):
    return ActivityStore(library.db_path)


@pytest.fixture(autouse=True)
def _shared_database(library, monkeypatch):
    """Hand the sweep the SAME `Database` the test seeded.

    In production `db_manager` returns the already-open shared instance for the
    library. Pinning it here keeps the test honest about that — the sweep must
    settle documents through the library's real connection, not open a second
    one behind the caller's back.
    """
    from fichero_server.db import manager as manager_module

    monkeypatch.setattr(
        manager_module.db_manager, "get_database", lambda _path: library.db
    )


async def _save_run(store: ActivityStore, thread_id: str, status: str) -> None:
    await store.save_workflow_run(
        thread_id=thread_id,
        workflow_id="wf-ner",
        workflow_name="NER per-page (local)",
        status=status,
        started_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )


async def _write_checkpoint(db_path: str, thread_id: str, document_ids: list[str]):
    """Persist the checkpoint a live run would have written before dying.

    This is the whole basis of the fix: `AsyncDuckDBCheckpointer` writes into
    the library DuckDB, so the run's document set outlives the process that
    was executing it.
    """
    checkpointer = AsyncDuckDBCheckpointer.from_db_path(db_path)
    await checkpointer.aput(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
        {
            "v": 1,
            "id": f"ckpt-{thread_id}",
            "ts": datetime.now(timezone.utc).isoformat(),
            "channel_values": {
                "outputs": {
                    "extract_all": {"documents": [{"id": d} for d in document_ids]}
                }
            },
            "channel_versions": {},
            "versions_seen": {},
            "pending_sends": [],
        },
        {},
        {},
    )


def _processing_doc(db, name: str) -> Document:
    doc = Document(name=name, path=f"/tmp/{name}", status=Status.processing)
    db.save(doc)
    return doc


class TestRecoveredRunReleasesDocuments:
    def test_killed_run_releases_its_documents(self, library, store):
        """The reported failure: NER run dies mid-extraction, document stranded."""
        doc = _processing_doc(library.db, "marshall-page-004.pdf")
        asyncio.run(_save_run(store, "t-dead", "running"))
        asyncio.run(_write_checkpoint(library.db_path, "t-dead", [doc.id]))

        tracker = SimpleNamespace(store=store)
        asyncio.run(activity._recover_stale_runs_bg(tracker, library.db_path))

        assert asyncio.run(store.get_workflow_run("t-dead")).status == "failed"
        after = library.db.get(Document, doc.id)
        assert after.status == Status.pending, (
            "a document stranded by a killed run must be released, not left "
            "spinning at 'processing' forever (#4379)"
        )

    def test_released_document_records_why(self, library, store):
        """Failing honestly means saying what happened, not just unsticking."""
        doc = _processing_doc(library.db, "diary-page-011.pdf")
        asyncio.run(_save_run(store, "t-dead", "running"))
        asyncio.run(_write_checkpoint(library.db_path, "t-dead", [doc.id]))

        tracker = SimpleNamespace(store=store)
        asyncio.run(activity._recover_stale_runs_bg(tracker, library.db_path))

        provenance = library.db.get(Document, doc.id).workflow_runs
        assert provenance, "a recovered run must leave provenance on its documents"
        assert provenance[-1]["result"]["status"] == "failed"
        assert (
            provenance[-1]["result"]["reason"]
            == "process_died_recovered_on_library_open"
        )

    def test_page_children_are_released_too(self, library, store):
        """Per-page fan-out is how NER actually runs — children must settle."""
        parent = _processing_doc(library.db, "marshall.pdf")
        child = Document(
            name="page-1", path=None, parent_id=parent.id, status=Status.processing
        )
        library.db.save(child)
        asyncio.run(_save_run(store, "t-dead", "running"))
        asyncio.run(_write_checkpoint(library.db_path, "t-dead", [parent.id]))

        tracker = SimpleNamespace(store=store)
        asyncio.run(activity._recover_stale_runs_bg(tracker, library.db_path))

        assert library.db.get(Document, parent.id).status == Status.pending
        assert library.db.get(Document, child.id).status == Status.pending


class TestSettlementIsScopedToTheDeadRun:
    def test_documents_of_another_run_are_untouched(self, library, store):
        """A blind 'everything at processing' sweep would trample a live run's
        documents. Settlement reads the DEAD run's checkpoint, so it cannot.
        """
        mine = _processing_doc(library.db, "mine.pdf")
        theirs = _processing_doc(library.db, "theirs.pdf")
        asyncio.run(_save_run(store, "t-dead", "running"))
        asyncio.run(_write_checkpoint(library.db_path, "t-dead", [mine.id]))

        tracker = SimpleNamespace(store=store)
        asyncio.run(activity._recover_stale_runs_bg(tracker, library.db_path))

        assert library.db.get(Document, mine.id).status == Status.pending
        assert library.db.get(Document, theirs.id).status == Status.processing, (
            "a document the dead run never touched must keep its status"
        )

    def test_live_run_is_neither_failed_nor_settled(self, library, store):
        """The F5 guarantee (#4316) must survive the new settlement step: a run
        this process is still executing keeps both its status AND its documents.
        """
        from fichero_server.execution import runner

        doc = _processing_doc(library.db, "in-flight.pdf")
        asyncio.run(_save_run(store, "t-live", "running"))
        asyncio.run(_write_checkpoint(library.db_path, "t-live", [doc.id]))

        runner._set_workflow_state(
            "t-live", {"status": "running", "events": runner.WorkflowEventHub()}
        )
        try:
            tracker = SimpleNamespace(store=store)
            asyncio.run(activity._recover_stale_runs_bg(tracker, library.db_path))

            assert asyncio.run(store.get_workflow_run("t-live")).status == "running"
            assert library.db.get(Document, doc.id).status == Status.processing, (
                "reopening a library mid-run must not yank the documents out "
                "from under the run that is still processing them"
            )
        finally:
            runner._remove_workflow_state("t-live")


class TestSettlementEdgeCases:
    def test_run_that_died_before_checkpointing_settles_nothing(
        self, library, store
    ):
        """No checkpoint means the run never reached a content tool, so it never
        moved a document to 'processing'. Settle nothing — and never guess.
        """
        doc = _processing_doc(library.db, "untouched.pdf")
        asyncio.run(_save_run(store, "t-early-death", "running"))
        # Deliberately no checkpoint written.

        tracker = SimpleNamespace(store=store)
        asyncio.run(activity._recover_stale_runs_bg(tracker, library.db_path))

        assert asyncio.run(store.get_workflow_run("t-early-death")).status == "failed"
        assert library.db.get(Document, doc.id).status == Status.processing, (
            "with no checkpoint there is no evidence this run owned the "
            "document — it must not be settled on a guess"
        )

    def test_checkpoint_with_no_documents_settles_nothing(self, library, store):
        from fichero_server.workflows.completion import (
            settle_documents_for_dead_run,
        )

        doc = _processing_doc(library.db, "unrelated.pdf")
        asyncio.run(_save_run(store, "t-empty", "running"))
        asyncio.run(_write_checkpoint(library.db_path, "t-empty", []))

        settled = asyncio.run(
            settle_documents_for_dead_run(library.db, "t-empty", "failed")
        )
        assert settled == 0
        assert library.db.get(Document, doc.id).status == Status.processing

    def test_one_unreadable_run_does_not_block_the_others(
        self, library, store, monkeypatch
    ):
        """Per-run isolation: a run that fails to settle must not strand the
        documents of every OTHER recovered run in the same sweep.
        """
        from fichero_server.workflows import completion

        good = _processing_doc(library.db, "good.pdf")
        asyncio.run(_save_run(store, "t-bad", "running"))
        asyncio.run(_save_run(store, "t-good", "running"))
        asyncio.run(_write_checkpoint(library.db_path, "t-good", [good.id]))

        real = completion.settle_documents_for_dead_run

        async def _explode_for_bad(db, thread_id, *args, **kwargs):
            if thread_id == "t-bad":
                raise RuntimeError("checkpoint unreadable")
            return await real(db, thread_id, *args, **kwargs)

        monkeypatch.setattr(
            completion, "settle_documents_for_dead_run", _explode_for_bad
        )

        tracker = SimpleNamespace(store=store)
        asyncio.run(activity._recover_stale_runs_bg(tracker, library.db_path))

        assert library.db.get(Document, good.id).status == Status.pending, (
            "one unsettleable run must not stop the sweep settling the rest"
        )


class TestSweepNamesWhatItFlipped:
    """The enabling seam: the sweep must return WHICH runs it flipped. A bare
    count cannot name what to settle, which is why documents were stranded.
    """

    def test_recover_stale_run_ids_returns_the_flipped_thread_ids(self, store):
        asyncio.run(_save_run(store, "t-a", "running"))
        asyncio.run(_save_run(store, "t-b", "accepted"))
        asyncio.run(_save_run(store, "t-done", "completed"))

        recovered = asyncio.run(store.recover_stale_run_ids(max_age_hours=0))

        assert sorted(recovered) == ["t-a", "t-b"]

    def test_count_wrapper_still_reports_the_same_sweep(self, store):
        asyncio.run(_save_run(store, "t-a", "running"))
        asyncio.run(_save_run(store, "t-b", "paused"))

        assert asyncio.run(store.recover_stale_runs(max_age_hours=0)) == 2

    def test_excluded_live_run_is_not_named(self, store):
        asyncio.run(_save_run(store, "t-live", "running"))
        asyncio.run(_save_run(store, "t-zombie", "running"))

        recovered = asyncio.run(
            store.recover_stale_run_ids(
                max_age_hours=0, exclude_thread_ids=("t-live",)
            )
        )
        assert recovered == ["t-zombie"]
