"""A thumbnail claim nobody runs must not hold the thumbnails-first gate (#6203, `activity.lane.no-wait-on-a-job-that-will-not-run`)."""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs

THUMB = "thumbnail-6203"


@pytest.fixture
def thumbs(monkeypatch):
    made: set[str] = set()
    monkeypatch.setitem(jobs.KINDS, THUMB, jobs.Kind(run=lambda db, subject: None, model=None, lane="images",
                                                     name="Make thumbnails", first=True))
    monkeypatch.setattr("fichero_server.db.storage.has_thumbnail", lambda doc_id, package_path=None: doc_id in made)
    return made


def _state(db, job_id) -> str:
    return db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [job_id])[0]


def _claimed_by_a_dead_worker(db, subject, seconds_ago=600):
    job_id = jobs._insert(db, THUMB, subject, None, "automatic")
    db.execute(f"UPDATE jobs SET state = 'running', attempts = 1, started_at = now() - INTERVAL {seconds_ago} SECOND "
               "WHERE id = ?", [job_id])
    return job_id


def test_a_claim_left_running_by_a_dead_process_is_requeued_on_open(db, thumbs):
    jobs._ensure(db)
    job_id = _claimed_by_a_dead_worker(db, "page-008")

    jobs.resume(db)

    assert _state(db, job_id) == "waiting"  # no thumbnail file: its job stands, to run


def test_a_running_claim_no_thread_runs_goes_back_to_waiting_without_a_reopen(db, thumbs):
    jobs._ensure(db)
    orphan = _claimed_by_a_dead_worker(db, "page-009")

    assert jobs.requeue_orphaned_first(db) == 1

    assert _state(db, orphan) == "waiting"


def test_a_claim_just_made_or_run_by_a_live_thread_stays_running(db, thumbs, monkeypatch):
    jobs._ensure(db)
    fresh = _claimed_by_a_dead_worker(db, "page-010", seconds_ago=1)
    live = _claimed_by_a_dead_worker(db, "page-011")
    monkeypatch.setattr(jobs._scheduler, "running_ids", lambda: [live])

    assert jobs.requeue_orphaned_first(db) == 0

    assert _state(db, fresh) == "running" and _state(db, live) == "running"


def test_the_scan_that_holds_heavy_work_requeues_the_claim_nobody_runs(db, thumbs, monkeypatch):
    jobs._ensure(db)
    monkeypatch.setitem(jobs.KINDS, "heavy-6203", jobs.Kind(run=lambda db, subject: None, model=None, lane="local-ml",
                                                            name="Heavy"))
    orphan = _claimed_by_a_dead_worker(db, "page-008")
    heavy = jobs._insert(db, "heavy-6203", "page-008", None, "automatic")
    monkeypatch.setattr(jobs._scheduler.lanes["local-ml"], "libraries", {jobs._key(db)})

    picked = jobs._scheduler._next(jobs._scheduler.lanes["local-ml"])

    assert _state(db, orphan) == "waiting"  # requeued for the thumbnail lane
    assert picked is None or picked[2][0] != heavy  # the thumbnail waits first, so the heavy job still waits its turn
