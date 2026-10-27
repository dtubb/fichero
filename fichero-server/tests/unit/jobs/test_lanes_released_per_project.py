"""The lanes are shared, the holds are not (#6213): a row a dead process left running holds no lane, a job stuck in a lane
thread does not keep its slot from another project, and a release refuses only a run alive in this engine
(`recipes-run.restart.releases-lanes`, `recipes-run.isolation.one-project-never-blocks-another`,
`recipes-run.isolation.release-never-refused-by-a-phantom`)."""
from __future__ import annotations

import time

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs

THUMB = "thumbnail-6213"


@pytest.fixture
def thumbs(monkeypatch):
    monkeypatch.setitem(jobs.KINDS, THUMB, jobs.Kind(run=lambda db, subject: None, model=None, lane="images",
                                                     name="Make thumbnails", first=True))
    monkeypatch.setattr("fichero_server.db.storage.has_thumbnail", lambda doc_id, package_path=None: False)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)


@pytest.fixture
def other(tmp_path, db):
    """A second project open on the same engine."""
    package = tmp_path / "other.fichero"
    for sub in ("", "lance", "storage", "files"):
        (package / sub).mkdir(exist_ok=True)
    other_db = db_manager.get_database(package)
    jobs._ensure(other_db)
    return other_db


@pytest.fixture
def images(monkeypatch):
    lane = jobs._scheduler.lanes["images"]
    monkeypatch.setattr(lane, "running", {})
    monkeypatch.setattr(lane, "started", {})
    return lane


def _left_running(db, subject, seconds_ago=600) -> str:
    job_id = jobs._insert(db, THUMB, subject, None, "automatic")
    db.execute(f"UPDATE jobs SET state = 'running', attempts = 1, started_at = now() - INTERVAL {seconds_ago} SECOND "
               "WHERE id = ?", [job_id])
    return job_id


def test_a_row_a_dead_process_left_running_holds_no_lane_for_another_project(db, other, thumbs, images, monkeypatch):
    jobs._ensure(db)
    _left_running(db, "a-page-1")
    _left_running(db, "a-page-2")
    fresh = jobs._insert(other, THUMB, "b-page-1", None, "automatic")
    monkeypatch.setattr(images, "libraries", {jobs._key(db), jobs._key(other)})

    picked = jobs._scheduler._next(images)

    assert picked is not None and picked[2][0] == fresh
    assert images.may_start(THUMB, None)


def test_jobs_stuck_in_the_lane_past_the_deadline_give_back_their_slots(db, other, thumbs, images):
    jobs._ensure(db)
    stuck = [_left_running(db, f"a-page-{n}") for n in range(2)]
    for job_id in stuck:  # two lane threads of this engine, each stuck on a page of project A
        images.running[job_id] = None
        images.started[job_id] = time.monotonic() - jobs.STUCK_IMAGE_JOB_SECONDS - 1
    fresh = jobs._insert(other, THUMB, "b-page-1", None, "automatic")

    assert images.may_start(THUMB, None)  # project B's thumbnail starts
    assert images.threads_wanted == images.slots + 2  # on a thread of its own: the stuck ones are still blocked
    reason = jobs.waiting_reason(other, fresh, THUMB)
    assert "another project" not in reason and not reason.startswith("Waiting for the thumbnail lane:")


def test_a_job_running_within_the_deadline_still_holds_its_slot(db, thumbs, images):
    jobs._ensure(db)
    for n in range(2):
        job_id = _left_running(db, f"a-page-{n}", seconds_ago=1)
        images.running[job_id] = None
        images.started[job_id] = time.monotonic()

    assert not images.may_start(THUMB, None)
    assert images.threads_wanted == images.slots


def test_a_release_is_not_refused_by_a_run_row_no_live_thread_runs(db, monkeypatch):
    jobs._ensure(db)
    jobs._insert(db, "workflow", "run-phantom", None, "automatic")
    db.execute("UPDATE jobs SET state = 'running', detail = '{\"name\": \"Detect Segments (Kraken)\"}' WHERE kind = 'workflow'")
    monkeypatch.setattr("fichero_server.execution.runner._running_workflows", {})

    runs, _running, _waiting = jobs.live_work(db)

    assert runs == []


def test_a_release_refused_by_a_live_run_names_it_and_its_state(db, monkeypatch):
    jobs._ensure(db)
    run_id = jobs._insert(db, "workflow", "run-live", None, "automatic")
    db.execute("UPDATE jobs SET state = 'running', detail = '{\"name\": \"Detect Segments (Kraken)\"}' WHERE id = ?", [run_id])
    monkeypatch.setattr("fichero_server.execution.runner._running_workflows", {run_id: {"status": "running"}})

    runs, _running, _waiting = jobs.live_work(db)

    assert runs == [f"Detect Segments (Kraken), {run_id}, running"]


def test_a_slow_live_model_job_keeps_its_slot_past_the_deadline(monkeypatch):
    """Only the images lane gives back a stuck slot: a model job reading one page for ten minutes is alive, and a second
    heavy model never starts beside it (#6000), nor does the lane want a thread beside it."""
    lane = jobs._scheduler.lanes["local-ml"]
    monkeypatch.setattr(lane, "running", {"slow-read": "mlx:a-big-reader"})
    monkeypatch.setattr(lane, "started", {"slow-read": time.monotonic() - jobs.STUCK_IMAGE_JOB_SECONDS * 10})
    monkeypatch.setattr(lane, "slots", 1)

    assert lane.stuck() == set()
    assert "slow-read" in lane.holding()
    assert not lane.may_start("read-a-line", "mlx:another-big-reader")
    from fichero_server.llm.local_inference import LOCAL_READS_CEILING

    assert lane.threads_wanted == max(1, LOCAL_READS_CEILING)
