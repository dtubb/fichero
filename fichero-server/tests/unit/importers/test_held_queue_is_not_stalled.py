"""After a restart, pages held for Continue are held, not stalled (#6827).

Spec: docs/contributor_manual/specs/importer/importer.md -- `importer.resume.held-queue-is-not-stalled`,
`importer.resume.no-twin-rows-at-open`. Driven through the open's own re-queue (`db.manager.resume_pending_derivatives`),
`jobs.resume`, the stall watchdog's own read of the job table (`_jobs_say`) and the launch alert's Continue
(`jobs.continue_after_quit`), on the real jobs table.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from fichero_server.db import manager
from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.models import DocType, Document, FileType, Status


@pytest.fixture
def lib(db, monkeypatch):
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    monkeypatch.setattr(derivatives, "_emit_queue_progress", lambda *a, **k: None)
    monkeypatch.setattr(derivatives, "_emit_queue_activity", lambda *a, **k: None)
    monkeypatch.setattr(derivatives, "STALL_SECONDS", 0.3)
    from fichero_server.execution import throttle

    monkeypatch.setattr(throttle, "why_wait", lambda **k: None)
    monkeypatch.setattr(manager.db_manager, "open_database", lambda key: db)
    jobs.set_paused(True)  # nothing runs: the rows stay where the test puts them
    library = str(Path(db.path).parent)
    yield db, library
    jobs.set_paused(False)
    derivatives._disarm_stall_watchdog()
    derivatives._progress.pop(derivatives._key(library), None)
    derivatives._queue_db_paths.pop(derivatives._key(library), None)


def _pending(db, n):
    docs = [Document(name=f"p{i}.png", doc_type=DocType.file, file_type=FileType.image, status=Status.pending,
                     page_content="x") for i in range(n)]
    for doc in docs:
        db.save(doc)
    return docs


def test_a_queue_whose_live_rows_are_all_paused_is_held(lib):
    db, library = lib
    jobs.load_kinds()
    _pending(db, 2)
    manager.resume_pending_derivatives(db, library)
    own = [derivatives.THUMBNAIL_KIND, derivatives.EMBED_KIND, derivatives.NLP_KIND]
    assert jobs.queue_state(db, own) == "held"
    db.execute("UPDATE jobs SET state = 'waiting' WHERE id = (SELECT id FROM jobs WHERE kind = 'thumbnail' LIMIT 1)")
    assert jobs.queue_state(db, own) is None


def test_the_open_requeue_holds_the_rows_and_arms_no_queue_and_no_stall_is_said(lib):
    db, library = lib
    warnings: list[str] = []
    derivatives._emit_queue_activity = lambda path, **k: warnings.append(k["message"]) if k.get("warning") else None
    _pending(db, 3)

    manager.resume_pending_derivatives(db, library)

    states = {r[0] for r in db.execute_fetchall("SELECT state FROM jobs WHERE kind IN ('thumbnail', 'embed')")}
    assert states == {"paused"}
    assert derivatives._key(library) not in derivatives._progress, "the open armed a queue for held pages"
    time.sleep(0.8)
    assert warnings == []


def test_the_watchdog_says_nothing_for_a_queue_whose_rows_are_paused(lib):
    db, library = lib
    jobs.load_kinds()
    warnings: list[str] = []
    derivatives._emit_queue_activity = lambda path, **k: warnings.append(k["message"]) if k.get("warning") else None
    _pending(db, 2)
    manager.resume_pending_derivatives(db, library)
    derivatives._progress_add(library, 2, db_path=str(db.path))  # the queue armed by an earlier import in this process
    time.sleep(0.8)
    assert warnings == [], warnings


def test_a_page_whose_thumbnail_job_was_running_at_the_kill_gets_no_second_row(lib):
    db, library = lib
    docs = _pending(db, 3)
    manager.resume_pending_derivatives(db, library)
    db.execute("DELETE FROM jobs")  # the quit left no held rows; one page's job was running at the kill
    jobs.enqueue_many(db, "thumbnail", [d.id for d in docs])
    db.execute("UPDATE jobs SET state = 'running' WHERE kind = 'thumbnail' AND subject = ?", [docs[0].id])

    jobs.resume(db)  # the open: what the quit left is held
    manager.resume_pending_derivatives(db, library)

    twins = db.execute_fetchall(
        "SELECT subject, count(*) FROM jobs WHERE kind = 'thumbnail' GROUP BY subject HAVING count(*) > 1")
    assert twins == []


def test_continue_arms_the_count_from_the_held_pages(lib):
    db, library = lib
    _pending(db, 4)
    manager.resume_pending_derivatives(db, library)
    assert derivatives._key(library) not in derivatives._progress

    jobs.continue_after_quit(db, None)

    state = derivatives._progress[derivatives._key(library)]
    assert (state["done"], state["total"]) == (0, 4)
