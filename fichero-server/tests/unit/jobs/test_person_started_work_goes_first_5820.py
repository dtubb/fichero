"""Work a person started goes ahead of background work on a shared lane (#5820,
`activity.throttle.person-started-first`).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. Seen live: a Transcribe (Kraken) run waited
"for the model lane: Embed for search", behind background embedding. A job is one item (one page's embed), so a
running background job yields at its own end: the next pick on the lane is the person's job, not the next
background one.

Real lane, real job rows, kinds that record when they start (one shared lane slot so order is exact).
"""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs

BACKGROUND, PERSON, WATCHED = "background-embed-5820", "person-transcribe-5820", "watched-try-5839"


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def lane(monkeypatch):
    """Two kinds on the one-slot recipes lane; the first started holds until released."""
    started: list[str] = []
    release = threading.Event()

    def run(db, subject):
        started.append(subject)
        if len(started) == 1:
            release.wait(30)

    monkeypatch.setitem(jobs.KINDS, BACKGROUND, jobs.Kind(run=run, model=None, lane="recipes", name="Embed for search"))
    monkeypatch.setitem(jobs.KINDS, WATCHED, jobs.Kind(run=run, model=None, lane="recipes", name="Try a stage"))
    monkeypatch.setitem(jobs.KINDS, PERSON, jobs.Kind(run=run, model=None, lane="recipes", name="Transcribe"))
    yield type("Lane", (), {"started": started, "release": release})
    release.set()


def test_a_queued_person_started_job_starts_before_background_work_queued_earlier(db, lane):
    jobs.set_paused(True)
    jobs.enqueue(db, BACKGROUND, "embed-1")
    jobs.enqueue(db, BACKGROUND, "embed-2")
    jobs.enqueue(db, PERSON, "transcribe", started_by="owner")
    lane.release.set()
    jobs.set_paused(False)
    assert _wait_for(lambda: len(lane.started) == 3)
    assert lane.started == ["transcribe", "embed-1", "embed-2"]


def test_a_running_background_job_is_followed_by_the_person_started_one_not_by_more_background_work(db, lane):
    first = jobs.enqueue(db, BACKGROUND, "embed-1")
    assert _wait_for(lambda: lane.started == ["embed-1"])
    jobs.enqueue(db, BACKGROUND, "embed-2")
    jobs.enqueue(db, PERSON, "transcribe", started_by="owner")
    lane.release.set()  # embed-1 ends: its next checkpoint
    assert _wait_for(lambda: len(lane.started) == 3)
    assert lane.started == ["embed-1", "transcribe", "embed-2"]
    assert jobs.read_job(db, first)["state"] in ("running", "done")


def test_the_waiting_line_names_what_the_person_started_job_waits_for(db, lane):
    jobs.enqueue(db, BACKGROUND, "embed-1")
    assert _wait_for(lambda: lane.started == ["embed-1"])
    person = jobs.enqueue(db, PERSON, "transcribe", started_by="owner")
    state, reason = jobs.state_and_reason(db, person)
    assert state == "waiting"
    assert "Embed for search" in reason


# -- a stage try is watched, and goes ahead of a bulk run the person also started (#5839) -------------------------


def test_a_watched_job_starts_before_a_bulk_run_the_person_started_earlier(db, lane):
    jobs.set_paused(True)
    jobs.enqueue(db, PERSON, "bulk-1", started_by="owner")
    jobs.enqueue(db, PERSON, "bulk-2", started_by="owner")
    jobs.enqueue(db, PERSON, "try", started_by="owner", watched=True)
    lane.release.set()
    jobs.set_paused(False)
    assert _wait_for(lambda: len(lane.started) == 3)
    assert lane.started == ["try", "bulk-1", "bulk-2"]


def test_activity_lists_the_waiting_rows_in_the_order_they_will_run(db, lane):
    jobs.set_paused(True)
    jobs.enqueue(db, BACKGROUND, "embed-1")
    jobs.enqueue(db, PERSON, "bulk", started_by="owner")
    jobs.enqueue(db, WATCHED, "try", started_by="owner", watched=True)
    assert [r["kind"] for r in jobs.snapshot(db)] == [WATCHED, PERSON, BACKGROUND]


def test_a_model_lane_row_made_while_a_person_waits_is_watched(db):
    with jobs.person_is_waiting():
        future = jobs.submit(db, "read-page", "p1", model="m", fn=lambda: None, lane="recipes")
    other = jobs.submit(db, "read-page", "p2", model="m", fn=lambda: None, lane="recipes")
    flags = {r[0]: r[1] for r in db.execute_fetchall("SELECT id, COALESCE(watched, FALSE) FROM jobs")}
    assert flags[future.job_id] is True and flags[other.job_id] is False
