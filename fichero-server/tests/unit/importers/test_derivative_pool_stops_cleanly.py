"""Stopping the derivative pool drops the stages it has not started (#5223).

WHY: the pool's worker threads are not daemons, so Python's exit joins them, and before this they
ran every queued thumbnail and embed stage first. A test file that imported a folder passed in
14 s and then sat at exit -- at background QoS, embedding pages of libraries pytest had already
deleted -- until it was killed; a gate running such a file would hang. The test session now stops
the pool with `cancel_pending=True` (tests/conftest.py, pytest_sessionfinish). If this regresses,
queued stages run at exit again. A stage already RUNNING still finishes: a page is never left
half-written.
"""

from __future__ import annotations

import threading

from fichero_server.importers import derivatives


def test_queued_stages_are_cancelled_and_never_run_and_running_ones_finish():
    derivatives.shutdown(wait=True)             # a fresh pool
    executor = derivatives._get_executor()
    release = threading.Event()
    started = threading.Semaphore(0)
    ran_queued = threading.Event()

    def blocker():
        started.release()
        release.wait(30)
        return "finished"

    running = [executor.submit(blocker) for _ in range(derivatives.MAX_CONCURRENT_DERIVATIVES)]
    for _ in running:
        assert started.acquire(timeout=30), "a worker never picked up its stage"
    queued = executor.submit(ran_queued.set)    # every worker is busy: this one waits

    derivatives.shutdown(wait=False, cancel_pending=True)
    release.set()

    assert queued.cancelled()
    assert all(f.result(timeout=30) == "finished" for f in running)
    assert not ran_queued.is_set()


def test_the_test_session_stops_the_pool_with_its_queue_dropped():
    """The hook is what makes a test run exit; a moved or deleted call would bring the hang back."""
    from pathlib import Path

    conftest = (Path(__file__).resolve().parents[2] / "conftest.py").read_text(encoding="utf-8")
    finish = conftest.split("def pytest_sessionfinish", 1)[1].split("\ndef ", 1)[0]
    assert "derivatives.shutdown(wait=False, cancel_pending=True)" in finish
