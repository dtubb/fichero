"""What a relaunch resumes, and what it must leave alone (#6584).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md, `activity.relaunch.only-running-work-resumes`.
WHY (owner 2026-11-13): a run that had failed, or that the person had paused, carried on by itself when the app
relaunched. A recipe run's pause lived only in memory, so the open put its row back to waiting and the lane took it;
a document whose thumbnail had failed was handed to the derivative queue again at every open. Through `jobs.resume`
(what a library open calls) and the real jobs table; nothing runs (background work is paused for the test).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.execution import jobs
from fichero_server.importers import derivatives
from fichero_server.models import DocType, Document, FileType, Status

KIND = "t-relaunch"


@pytest.fixture
def held(db, monkeypatch):
    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=lambda db, subject: None, model=None, name="Read a page"))
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())  # a new engine process: nothing of the old one is live
    jobs.set_paused(True)
    yield db
    jobs.set_paused(False)


def _row(db, subject, state, reason=None, **cols):
    job_id = jobs.enqueue(db, KIND, subject)
    sets = ", ".join(["state = ?", "reason = ?", *(f"{c} = ?" for c in cols)])
    db.execute(f"UPDATE jobs SET {sets} WHERE id = ?", [state, reason, *cols.values(), job_id])
    return job_id


def _state(db, job_id):
    return db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ?", [job_id])


def test_a_pause_asked_before_quit_is_still_a_pause_after_the_relaunch(held):
    pausing = _row(held, "p:1", "running", jobs.PAUSING)
    with_run = _row(held, "p:2", "waiting", "Paused with its run")
    between = _row(held, "p:3", "waiting", "Paused between steps")

    jobs.resume(held)

    assert _state(held, pausing) == ("paused", jobs.PAUSED_REASON)
    assert _state(held, with_run) == ("paused", "Paused with its run")
    assert _state(held, between) == ("paused", "Paused between steps")


def test_only_work_running_at_quit_carries_on__failed_stays_failed_with_its_reason(held):
    running = _row(held, "r:1", "running", None)
    failed = _row(held, "r:2", "failed", "Anthropic has no credit left", finished_at=jobs.utc_now())
    stopped = _row(held, "r:3", "cancelled", "Stopped by you", finished_at=jobs.utc_now())
    queued = _row(held, "r:4", "waiting", None)

    jobs.resume(held)

    assert _state(held, running) == ("waiting", "Interrupted; carries on")
    assert _state(held, failed) == ("failed", "Anthropic has no credit left"), "a failed run is never re-run by itself"
    assert _state(held, stopped) == ("cancelled", "Stopped by you")
    assert _state(held, queued)[0] == "waiting"


def test_a_deleted_row_never_comes_back(held):
    deleted = _row(held, "d:1", "running", None, cleared_at=jobs.utc_now())
    deleted_waiting = _row(held, "d:2", "waiting", None, cleared_at=jobs.utc_now())

    jobs.resume(held)

    assert _state(held, deleted) == ("cancelled", "Deleted by you")
    assert _state(held, deleted_waiting) == ("cancelled", "Deleted by you")
    assert not {deleted, deleted_waiting} & {j["id"] for j in jobs.snapshot(held)}


def test_a_document_whose_derivative_failed_is_not_queued_again_at_open(held, monkeypatch):
    monkeypatch.setattr(derivatives, "auto_nlp_enabled", lambda: False)
    failed = Document(name="bad.md", doc_type=DocType.file, file_type=FileType.text, status=Status.pending,
                      page_content="x", metadata={"derivative_error": "PIL cannot open this file"})
    stranded = Document(name="ok.md", doc_type=DocType.file, file_type=FileType.text, status=Status.pending,
                        page_content="y")
    for doc in (failed, stranded):
        held.save(doc)

    derivatives.queue_derivatives([failed, stranded], library_path=Path(held.path).parent, db=held, arrived=False)

    subjects = {r[0] for r in held.execute_fetchall("SELECT subject FROM jobs WHERE kind <> ?", [KIND])}
    assert stranded.id in subjects, "a page the quit stranded is still picked up"
    assert failed.id not in subjects, "a page whose derivative failed waits for Retry, not for the next open"
