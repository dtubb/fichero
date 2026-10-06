"""A library's job threads end when it closes, and on engine shutdown (#5503).

WHY: the full engine suite on an 8 GB Mac hung at 600% CPU; at the timeout 210 threads named
`fichero-jobs-database` were still in `_loop -> _claim -> _next -> is_paused`, polling for
libraries long closed. Nothing ended a lane's threads: a closed library was only forgotten by the
next full scan, never while background work was paused, and a look-again time left from an earlier
scan made a paused lane wake at once, every time. The same leak runs in the app whenever a project
is closed. These tests drive the real scheduler threads against a library opened and closed through
the database manager -- the one owner of when a library is open.
"""
from __future__ import annotations

import time

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs

#: How long a closed library's threads may take to end.
ENDS_WITHIN_SECONDS = 3.0


def _threads():
    return [t for lane in jobs._scheduler.lanes.values() for t in lane.threads]


def _waiting_job(monkeypatch, test_package, lane="database"):
    """A library with a job left waiting under the pause: the case that kept a lane alive."""
    kind = f"t-idle-{lane}"
    monkeypatch.setitem(jobs.KINDS, kind, jobs.Kind(run=lambda db, subject: None, model=None, lane=lane))
    jobs.set_paused(True)
    db = db_manager.get_database(test_package)
    with db.transaction():
        jobs.enqueue(db, kind, "page-1")
    deadline = time.monotonic() + ENDS_WITHIN_SECONDS
    while not any(t.is_alive() for t in jobs._scheduler.lanes[lane].threads) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert any(t.is_alive() for t in jobs._scheduler.lanes[lane].threads), "the lane never started"
    return db


def test_closing_a_library_ends_its_job_threads(test_package, monkeypatch):
    """WHY: a closed project must leave nothing polling; before #5503 its lane thread woke every
    30 s (or at once) for the life of the engine, one more per test in the suite."""
    _waiting_job(monkeypatch, test_package)
    started = time.monotonic()

    db_manager.close_database(test_package)

    assert [t.name for t in _threads() if t.is_alive()] == []
    assert time.monotonic() - started < ENDS_WITHIN_SECONDS


def test_the_job_waits_for_the_library_to_open_again(test_package, monkeypatch):
    """WHY: ending the threads must not lose the work: the row stays waiting, and opening the
    library starts a thread for it again (`jobs.resume`)."""
    _waiting_job(monkeypatch, test_package)
    db_manager.close_database(test_package)

    db = db_manager.get_database(test_package)

    assert db.execute_fetchone("SELECT state FROM jobs WHERE subject = 'page-1'")[0] == "waiting"
    assert any(t.is_alive() for t in jobs._scheduler.lanes["database"].threads)


def test_a_lane_whose_library_is_gone_ends_by_itself(test_package, monkeypatch):
    """WHY: a thread must not outlive its libraries even when no one tells it (a scheduler a test
    replaced, a close the manager did not see): its next scan finds the library closed, forgets it,
    and the thread ends -- instead of polling, or spinning on the closed connection."""
    _waiting_job(monkeypatch, test_package)
    lane = jobs._scheduler.lanes["database"]
    db = db_manager._databases.pop(db_manager._cache_key(test_package))  # gone without `stop`
    try:
        jobs.set_paused(False)  # wakes the lane; a full scan may forget a closed library
        deadline = time.monotonic() + ENDS_WITHIN_SECONDS
        while any(t.is_alive() for t in lane.threads) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not any(t.is_alive() for t in lane.threads)
        assert not lane.libraries
    finally:
        db.close()


def test_a_paused_idle_lane_does_not_spin(test_package, monkeypatch):
    """WHY: a look-again time left by an earlier scan was only cleared when the scan got past the
    pause check, so a paused lane with a past look-again time waited 0 s, every time: one core per
    thread. Paused, it must sleep until woken."""
    _waiting_job(monkeypatch, test_package)
    lane = jobs._scheduler.lanes["database"]
    calls = []
    real = jobs._Scheduler._next

    def counting(self, lane_, **kwargs):
        if lane_ is lane:
            calls.append(1)
        return real(self, lane_, **kwargs)

    monkeypatch.setattr(jobs._Scheduler, "_next", counting)
    lane.look_again_at = time.monotonic() - 10  # left from an earlier scan
    lane.event.set()
    time.sleep(0.5)

    assert len(calls) <= 2
    db_manager.close_database(test_package)


def test_engine_shutdown_joins_every_lane(test_package, monkeypatch):
    """WHY: the engine's shutdown closes every library through `close_all`; that one path must end
    and join every job thread, or a quitting engine leaves them running against closed files."""
    _waiting_job(monkeypatch, test_package, lane="database")
    _waiting_job(monkeypatch, test_package, lane="network")
    assert len([t for t in _threads() if t.is_alive()]) >= 2

    db_manager.close_all()

    assert not any(t.is_alive() for t in _threads())


def test_a_thread_mid_job_finishes_it_then_ends(test_package, monkeypatch):
    """WHY: closing waits only a short while for a running job (a long page must not hold a close
    for minutes); the thread finishes that job and then ends, rather than living on."""
    import threading

    release = threading.Event()
    started = threading.Event()

    def run(db, subject):
        started.set()
        release.wait(10)

    monkeypatch.setitem(jobs.KINDS, "t-long", jobs.Kind(run=run, model=None, lane="database"))
    db = db_manager.get_database(test_package)
    with db.transaction():
        jobs.enqueue(db, "t-long", "page-1")
    assert started.wait(ENDS_WITHIN_SECONDS)

    left = jobs.stop(db_manager._cache_key(test_package), timeout=0.2)
    assert [t.name for t in left] == ["fichero-jobs-database"]

    release.set()
    left[0].join(ENDS_WITHIN_SECONDS)
    assert not left[0].is_alive()
