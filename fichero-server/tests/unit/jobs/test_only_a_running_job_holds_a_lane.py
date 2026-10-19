"""Only a job that is actually running holds a lane (owner screenshot 2026-10-19 16:25): Kraken sat 3 min 49 s on
"Waiting for the model lane: Embed for search is running" while the Embed for search row itself said "Waiting:
Interrupted; carries on". A library opened again (`resume`) had reset the rows of jobs this engine was still running.

Real lane and rows, faked work.
"""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs

HOLDER, NEXT = "holder-lane-5819", "next-lane-5819"


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def lane(monkeypatch):
    ran: list[str] = []
    gate = threading.Event()

    def work(db, subject):
        ran.append(subject)
        if subject == "hold":
            gate.wait(30)

    monkeypatch.setitem(jobs.KINDS, HOLDER, jobs.Kind(run=work, model=None, lane="recipes", name="Embed for search"))
    monkeypatch.setitem(jobs.KINDS, NEXT, jobs.Kind(run=work, model=None, lane="recipes", name="Next job"))
    yield type("Lane", (), {"ran": ran, "gate": gate, "lane": jobs._scheduler.lanes["recipes"]})
    gate.set()


def _holding(db, lane):
    holder = jobs.enqueue(db, HOLDER, "hold")
    assert _wait_for(lambda: "hold" in lane.ran and holder in lane.lane.running)
    return holder


def test_opening_the_library_again_does_not_interrupt_a_job_that_is_running(db, lane):
    holder = _holding(db, lane)
    jobs.resume(db)  # a project opened again while the engine runs it
    row = jobs.read_job(db, holder)
    assert row["state"] == "running" and "Interrupted" not in (row["reason"] or "")


def test_the_waiting_words_name_only_a_holder_whose_row_is_running(db, lane):
    holder = _holding(db, lane)
    queued = jobs.enqueue(db, NEXT, "n1")
    assert "Embed for search is running" in jobs.state_and_reason(db, queued)[1]  # honest while it runs
    db.execute("UPDATE jobs SET state = 'waiting', reason = 'Interrupted; carries on' WHERE id = ?", [holder])
    said = jobs.state_and_reason(db, queued)[1]
    assert "Embed for search is running" not in said  # its row says waiting: it is not named as the holder


def test_a_holder_whose_row_left_running_is_released_at_once(db, lane):
    holder = _holding(db, lane)
    for state in ("waiting", "cancelled", "failed"):  # interrupted, stopped, set aside
        lane.lane.running[holder] = None  # (re-held for each state)
        db.execute("UPDATE jobs SET state = ?, reason = 'x' WHERE id = ?", [state, holder])
        assert jobs._scheduler.release_stale_holders(lane.lane) == [holder]
        assert holder not in lane.lane.running and lane.lane.may_start(NEXT, None)
        db.execute("UPDATE jobs SET state = 'running' WHERE id = ?", [holder])
    assert jobs._scheduler.release_stale_holders(lane.lane) == []  # a running holder is kept


def test_a_stale_holder_from_a_previous_engine_run_is_cleared_at_startup(db, lane):
    jobs._ensure(db)
    db.execute("INSERT INTO jobs (id, kind, subject, state, created_at, started_by) "
               "VALUES ('old', ?, 'old-page', 'running', now(), 'automatic')", [HOLDER])  # left by a dead engine
    assert lane.lane.running == {}  # the lane's holders are in memory: a new engine has none
    jobs.resume(db)
    row = jobs.read_job(db, "old")
    assert row["state"] == "waiting" and row["reason"] == "Interrupted; carries on"  # not running, so not a holder
    queued = jobs.enqueue(db, NEXT, "n1")
    assert _wait_for(lambda: "n1" in lane.ran)  # the next job takes the lane at once
    assert "old" not in lane.lane.running
