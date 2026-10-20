"""Review 424: `run_on_lane_blocking` waits as `_wait_for_lane` does -- a Stop, a Pause or a closed project withdraws
a page still WAITING for the lane (it used to be `.result()` with no timeout, a thread hung for good)."""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs
from fichero_server.execution.cancellation import WorkflowCancelled, clear_cancellation, request_cancellation


@pytest.fixture
def busy_lane(db):
    """A heavy page holding the lane, so the next one waits behind it."""
    gate, started = threading.Event(), threading.Event()
    first = jobs.submit(db, "find-lines", "first", model="kraken:blla", fn=lambda: (started.set(), gate.wait(20)))
    assert started.wait(10)
    yield
    gate.set()
    first.result(10)


def _wait_in_thread(test_package, run_id=None):
    outcome = {}

    def go():
        try:
            outcome["value"] = jobs.run_on_lane_blocking(
                str(test_package), "find-regions", "page", model="omlx:reader", fn=lambda: "ran", run_id=run_id)
        except BaseException as exc:  # noqa: BLE001 -- the test reads what the wait raised
            outcome["error"] = exc

    thread = threading.Thread(target=go, daemon=True)
    thread.start()
    return thread, outcome


def test_stop_while_waiting_withdraws_the_page_and_the_run_reads_stopped(db, test_package, busy_lane):
    thread, outcome = _wait_in_thread(test_package, run_id="run-blocking")
    time.sleep(0.5)
    request_cancellation("run-blocking")
    try:
        thread.join(10)
        assert not thread.is_alive(), ("the thread was still hung after Stop", db.execute_fetchall("SELECT subject, state, reason FROM jobs"), outcome)
        assert isinstance(outcome.get("error"), WorkflowCancelled)
    finally:
        clear_cancellation("run-blocking")
    assert db.execute_fetchone("SELECT state, reason FROM jobs WHERE subject = 'page'") == ("cancelled", "Stopped by you")


def test_closing_the_project_while_waiting_ends_the_wait_cancelled(db, test_package, busy_lane, monkeypatch):
    thread, outcome = _wait_in_thread(test_package)
    time.sleep(0.5)
    monkeypatch.setattr(jobs, "_still_open", lambda _db: False)
    thread.join(10)
    assert not thread.is_alive(), "the thread was still hung after the project closed"
    assert isinstance(outcome.get("error"), jobs.JobCancelled)
    assert str(outcome["error"]) == jobs.CLOSED_BEFORE_RUN


def test_a_find_regions_page_with_a_free_lane_runs_it_the_kind_is_registered(db, test_package):
    assert jobs.run_on_lane_blocking(str(test_package), "find-regions", "page", model="kraken:blla", fn=lambda: "ran") == "ran"
