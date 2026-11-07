"""Opening a library must not make two waiting rows for one pending document (#6209).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md --
`activity.lane.no-wait-on-a-job-that-will-not-run`.

A dead engine leaves its queued work as durable `jobs` rows: a pending document
whose thumbnail was mid-render when the engine quit sits there with its
thumbnail `running` and its embed still `waiting`. On the next open the
pending document is re-queued; whatever row the dead engine left must already
be back to `waiting` by then, so the queue sees it and keeps one row per stage
-- never two waiting rows for the same work.
"""
from __future__ import annotations

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.models import DocType, Document, FileType, Status


def _pending_doc(db) -> Document:
    doc = Document(name="p0.md", doc_type=DocType.file, file_type=FileType.text,
                   status=Status.pending, page_content="page 0")
    db.save(doc)
    return doc


def _queued_rows(db):
    return sorted(db.execute_fetchall("SELECT kind, state FROM jobs"))


@pytest.fixture(autouse=True)
def no_nlp(monkeypatch):
    """The free NLP draft is off, so the open's requeue queues exactly the thumbnail and the embed."""
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)


def test_opening_a_project_queues_each_pending_stage_once(db, test_package, monkeypatch):
    """`activity.lane.no-wait-on-a-job-that-will-not-run` (#6209): after open, each pending
    document has exactly one waiting row per stage. The engine died mid-thumbnail: that job is
    `running` and its embed is `waiting` when the project opens again, and the requeue must not
    make a second thumbnail row for the same page."""
    monkeypatch.delenv("FICHERO_SKIP_DERIVATIVE_RESUME", raising=False)  # the open's requeue, as in a real relaunch
    db_manager.get_database(test_package)
    jobs.set_paused(True)  # the lanes never pick, so the rows stay where the open leaves them
    with db.transaction():
        doc = _pending_doc(db)
        derivatives.queue_derivatives([doc], library_path=test_package, db=db)
    # The engine dies mid-thumbnail: that job is running, its embed still queued.
    db.execute("UPDATE jobs SET state = 'running', attempts = 1 WHERE kind = 'thumbnail'")

    db_manager.close_database(test_package)  # quit
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())  # a new engine process
    db = db_manager.get_database(test_package)  # relaunch

    assert _queued_rows(db) == [("embed", "waiting"), ("thumbnail", "waiting")], (
        "open queued the page's stages twice: " + repr(_queued_rows(db))
    )


def test_opening_a_project_with_everything_waiting_keeps_one_row_per_stage(db, test_package, monkeypatch):
    """The twin of the case above, already held: a page whose jobs were all `waiting` when the
    engine quit gets nothing new on open -- the requeue finds its waiting rows and skips them."""
    monkeypatch.delenv("FICHERO_SKIP_DERIVATIVE_RESUME", raising=False)
    db_manager.get_database(test_package)
    jobs.set_paused(True)
    with db.transaction():
        doc = _pending_doc(db)
        derivatives.queue_derivatives([doc], library_path=test_package, db=db)

    db_manager.close_database(test_package)  # quit
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())  # a new engine process
    db = db_manager.get_database(test_package)  # relaunch

    assert _queued_rows(db) == [("embed", "waiting"), ("thumbnail", "waiting")]
