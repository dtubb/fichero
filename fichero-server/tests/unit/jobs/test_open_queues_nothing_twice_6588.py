"""Opening a project queues nothing twice (#6595).

Spec: docs/contributor_manual/specs/ui/activity-pane.md, `activity.engine.open-queues-nothing-twice`.
WHY: the open re-queues every pending document's derivatives before `jobs.resume`; the dedupe looked only at WAITING
rows, so the quit-paused rows of the last session got a twin at every relaunch, and a page whose thumbnail row the person
deleted was queued again. Through the open's own resume (`db.manager.resume_pending_derivatives`) and the real jobs table.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.db import manager
from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.models import DocType, Document, FileType, Status


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _pending(db, n):
    docs = [Document(name=f"p{i}.png", doc_type=DocType.file, file_type=FileType.image, status=Status.pending,
                     page_content="x") for i in range(n)]
    for doc in docs:
        db.save(doc)
    return docs


def _open(db):
    manager.resume_pending_derivatives(db, str(Path(db.path).parent))


def _counts(db):
    return db.execute_fetchall(
        "SELECT kind, subject, count(*) FROM jobs WHERE kind IN ('thumbnail', 'embed') AND deleted_at IS NULL "
        "GROUP BY kind, subject HAVING count(*) > 1")


def test_two_opens_with_quit_paused_rows_leave_one_row_per_kind_and_subject(held):
    docs = _pending(held, 3)
    _open(held)
    held.execute("UPDATE jobs SET state = 'paused', reason = ? WHERE kind IN ('thumbnail', 'embed')", [jobs.QUIT_REASON])
    before = held.execute_fetchone("SELECT count(*) FROM jobs WHERE kind IN ('thumbnail', 'embed')")[0]
    assert before >= 3

    _open(held)
    _open(held)

    assert held.execute_fetchone("SELECT count(*) FROM jobs WHERE kind IN ('thumbnail', 'embed')")[0] == before
    assert _counts(held) == [], f"a twin for {[d.id for d in docs]}"


def test_a_deleted_thumbnail_row_is_not_queued_again_by_the_open_but_new_material_still_queues(held):
    docs = _pending(held, 2)
    _open(held)
    gone = held.execute_fetchone("SELECT id FROM jobs WHERE kind = 'thumbnail' AND subject = ?", [docs[0].id])[0]
    jobs.delete_jobs(held, [gone])

    _open(held)

    assert held.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = 'thumbnail' AND subject = ? AND deleted_at IS NULL",
                                 [docs[0].id])[0] == 0, "the open does not revive what the person deleted"
    # Genuinely new material (arrived) is queued, whatever the page's history.
    derivatives.queue_derivatives([docs[0]], library_path=Path(held.path).parent, db=held, arrived=True)
    assert held.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = 'thumbnail' AND subject = ? AND deleted_at IS NULL",
                                 [docs[0].id])[0] == 1


def test_a_synced_folders_open_read_adds_no_twin_to_a_paused_one_and_skips_a_deleted_one(held):
    from fichero_server import sync_folder

    sync_folder.register_job_kinds()
    first = sync_folder._queue_read(held, "folder-1", hold=True)
    sync_folder._queue_read(held, "folder-1", hold=True)
    assert held.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ? AND subject = 'folder-1'", [sync_folder.READ_KIND])[0] == 1
    assert held.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [first])[0] == "paused"

    jobs.delete_jobs(held, [first])
    sync_folder._queue_read(held, "folder-1", hold=True)
    assert held.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = ? AND subject = 'folder-1' AND deleted_at IS NULL",
                                 [sync_folder.READ_KIND])[0] == 0, "the open does not queue a read the person deleted"


def test_a_persons_request_on_a_paused_row_lets_it_run(held):
    """The dedupe reuses a paused row, but a person waiting on the work (`watched`) is a new instruction: the row it
    reuses goes back to waiting, so the click is never swallowed by a row paused at quit (spec: `activity.engine.open-queues-
    nothing-twice`; `activity.run.failed-is-never-requeued-by-itself` leaves a person's own request free to run)."""
    doc = _pending(held, 1)[0]
    _open(held)
    held.execute("UPDATE jobs SET state = 'paused', reason = ? WHERE kind = 'thumbnail'", [jobs.QUIT_REASON])

    job_id = jobs.enqueue(held, "thumbnail", doc.id, started_by="person", watched=True)

    row = jobs.read_job(held, job_id)
    assert row["state"] == "waiting" and row["reason"] is None
    assert held.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = 'thumbnail'")[0] == 1


def test_the_opens_own_requeue_leaves_a_paused_row_paused(held):
    doc = _pending(held, 1)[0]
    _open(held)
    held.execute("UPDATE jobs SET state = 'paused', reason = ? WHERE kind = 'thumbnail'", [jobs.QUIT_REASON])

    job_id = jobs.enqueue(held, "thumbnail", doc.id)

    assert jobs.read_job(held, job_id)["state"] == "paused"
