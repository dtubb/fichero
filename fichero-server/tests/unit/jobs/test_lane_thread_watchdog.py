"""A lane thread hung inside a database call is released after a bounded time (#6205,
`activity.lane.hung-call-says-so`): its slot is freed, its row says `timed out in the database`, and the lane no
longer counts it as holding a slot. The lane's thread is blocked in the call and cannot settle its own row; a
watchdog of its own lets it go, on the lane the thread still holds so a beside thread can take up the work behind
it. A job that keeps reporting progress is NOT let go, even if its total run exceeds the deadline."""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs

KIND = "hung-db-call"


@pytest.fixture
def hung_kind(monkeypatch):
    """A database-lane kind whose work blocks on a lock no test releases: the database call that never comes back. While
    the test runs the call holds its thread; released at the end so the lane's thread finishes and no blocked thread
    lingers into the next test."""
    release = threading.Event()

    def run(db, subject):
        release.wait(30)  # the call that does not come back

    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=run, model=None, lane="database",
                                                    name="Write to a synced folder"))
    yield release
    release.set()


def _wait_for(predicate, seconds=10.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _row(db, job_id):
    return db.execute_fetchone("SELECT state, reason, finished_at FROM jobs WHERE id = ?", [job_id])


def test_a_hung_database_lane_job_is_released_after_the_deadline(db, hung_kind, monkeypatch):
    """WHY (#6205): a database-lane thread wedged in a database call held its one slot for good, so every other write to
    a synced folder queued behind it and held work never started. After `STUCK_DATABASE_JOB_SECONDS` of no progress the
    lane lets it go: the slot is free, the row says `timed out in the database`, and the lane no longer counts it as
    holding a slot (another write may start)."""
    lane = jobs._scheduler.lanes["database"]
    job_id = jobs.enqueue(db, KIND, "folder-1")

    assert _wait_for(lambda: job_id in lane.running)  # claimed and running: blocked inside the call
    monkeypatch.setattr(jobs, "STUCK_DATABASE_JOB_SECONDS", 0.1)  # the ten-minute constant, down to a fraction of a second

    assert job_id in lane.holding()  # within the deadline it still holds its slot
    assert not lane.may_start(KIND, None)
    assert _row(db, job_id)[0] == "running"

    assert _wait_for(lambda: job_id in lane.stuck())  # the deadline passes, on its own
    jobs._scheduler.release_hung_database_jobs()

    state, reason, finished_at = _row(db, job_id)
    assert (state, reason) == ("failed", "timed out in the database")
    assert finished_at is not None
    assert job_id not in lane.holding()  # the slot is free: another write may start
    assert lane.may_start(KIND, None)
    assert lane.threads_wanted == lane.slots + 1  # on a thread of its own: the blocked one may still finish


def test_a_database_lane_job_within_the_deadline_keeps_its_slot(db, hung_kind, monkeypatch):
    """Running for a moment is not a hang: within the ten-minute deadline the database-lane job keeps its slot, and the
    watchdog releases nothing (a big write that takes two minutes is not a hung call)."""
    monkeypatch.setattr(jobs, "STUCK_DATABASE_JOB_SECONDS", 600.0)  # the default: ten minutes
    lane = jobs._scheduler.lanes["database"]
    job_id = jobs.enqueue(db, KIND, "folder-1")

    assert _wait_for(lambda: job_id in lane.running)
    jobs._scheduler.release_hung_database_jobs()  # nothing is past the deadline: nothing is released

    assert _row(db, job_id)[0] == "running"
    assert job_id in lane.holding()
    assert not lane.may_start(KIND, None)
    assert lane.threads_wanted == lane.slots


def test_a_progressing_database_lane_job_is_not_released(db, monkeypatch):
    """WHY (#6205): the deadline counts from the job's LAST progress, not from claim. A database-lane job that keeps
    reporting progress (a sync or export looping over many files) is healthy, so it must NOT be marked stuck even
    after its total runtime passes `STUCK_DATABASE_JOB_SECONDS`. Without the `heard` ping it would be killed mid-write."""
    release = threading.Event()
    start_time = [0.0]

    def run_progress(db, subject):
        start_time[0] = time.monotonic()
        # Work for ~1s, pinging progress every 0.1s so `heard` stays fresh.
        while time.monotonic() - start_time[0] < 1.0:
            jid = jobs.current_job_id()
            if jid:
                jobs.progress(jid)
            time.sleep(0.1)
        release.wait(30)  # stop pinging and hold the thread for the rest of the test

    monkeypatch.setitem(
        jobs.KINDS, "progress-db-call",
        jobs.Kind(run=run_progress, model=None, lane="database", name="Progress"),
    )
    monkeypatch.setattr(jobs, "STUCK_DATABASE_JOB_SECONDS", 0.5)  # deadline shorter than the pinging window

    lane = jobs._scheduler.lanes["database"]
    job_id = jobs.enqueue(db, "progress-db-call", "folder-1")

    assert _wait_for(lambda: job_id in lane.running)

    # Once we are well past the 0.5s deadline (but still inside the 1.0s pinging window), the job has been running
    # longer than the deadline yet must NOT be stuck, because it has been pinging `heard` all along.
    def past_deadline_and_not_stuck():
        if time.monotonic() - start_time[0] < 0.8:
            return False
        return job_id in lane.running and job_id not in lane.stuck()

    try:
        assert _wait_for(past_deadline_and_not_stuck, seconds=5.0)
        # Still holding its slot while it works, so no second writer starts beside it.
        assert job_id in lane.holding()
        assert _row(db, job_id)[0] == "running"
    finally:
        release.set()
