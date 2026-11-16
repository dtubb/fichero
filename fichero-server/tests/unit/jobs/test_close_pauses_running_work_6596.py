"""Closing a project pauses the work running in it (#6596).

Spec: docs/contributor_manual/specs/ui/activity-pane.md `activity.engine.close-pauses-running-work`. A close PAUSES the
project's waiting and running rows ("Paused: the project closed"), waits for its lane threads to let go of the connection
(longer than 2 s), and only then closes; a job that still meets a closed connection ends paused with those words, never
failed with the library's path.
"""
from __future__ import annotations

import threading
import time

import duckdb
import pytest

from fichero_server.db.manager import db_manager
from fichero_server.execution import jobs
from tests.unit.jobs.test_runs_are_jobs import _wait_for

KIND = "t-close-job"
CLOSED = "Paused: the project closed"


@pytest.fixture
def work(monkeypatch, test_package):
    """A job kind whose run waits for `go`, then writes to its project (what an embed does as it ends a page)."""
    state = {"started": threading.Event(), "go": threading.Event(), "wrote": []}

    def run(db, subject):
        state["started"].set()
        state["go"].wait(30)
        state["wrote"].append(db.execute_fetchone("SELECT 1")[0])  # a closed connection raises here

    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=run, model=None, name="Close job"))
    jobs.load_kinds()
    yield state
    state["go"].set()


def _row(db, job_id):
    return db.execute_fetchone("SELECT state, reason FROM jobs WHERE id = ?", [job_id])


def test_a_close_waits_past_two_seconds_for_the_running_job_and_pauses_the_waiting_one(work, test_package):
    db = db_manager.get_database(test_package)
    running = jobs.enqueue(db, KIND, "running")
    assert work["started"].wait(30)
    waiting = jobs.enqueue(db, KIND, "waiting")  # the lane's one thread per library is busy: this one waits
    threading.Timer(3.0, work["go"].set).start()  # longer than the old 2 s wait
    began = time.monotonic()
    db_manager.close_database(test_package)
    assert time.monotonic() - began >= 2.5, "the close let go of the connection under a job still working"
    assert work["wrote"] == [1], "the running job wrote to its project before the connection closed"
    db = db_manager.get_database(test_package)
    assert _row(db, running)[0] == "done"
    assert _row(db, waiting) == ("paused", CLOSED)


def test_a_job_that_still_meets_the_closed_connection_ends_paused_not_failed(work, test_package, monkeypatch):
    monkeypatch.setattr(jobs, "CLOSE_WAIT_SECONDS", 0.2)  # the wait runs out: the connection closes under the job
    db = db_manager.get_database(test_package)
    running = jobs.enqueue(db, KIND, "running")
    assert work["started"].wait(30)
    db_manager.close_database(test_package)
    work["go"].set()  # the job now writes to a closed connection
    assert _wait_for(lambda: not any(t.name.startswith("fichero-jobs") and t.is_alive() and jobs._scheduler.running_ids()
                                     for t in threading.enumerate()), 30)
    time.sleep(0.5)
    db = db_manager.get_database(test_package)
    state, reason = _row(db, running)
    assert (state, reason) == ("paused", CLOSED), (state, reason)
    assert "/" not in reason


def test_a_job_that_meets_a_closed_connection_is_paused_by_its_end_write(db, monkeypatch):
    def run(_db, subject):
        raise duckdb.ConnectionException("Connection Error: Connection already closed: the library "
                                         "/Volumes/Archive/P.fichero/fichero.duckdb was closed")

    monkeypatch.setitem(jobs.KINDS, KIND, jobs.Kind(run=run, model=None, name="Close job"))
    jobs.load_kinds()
    job_id = jobs.enqueue(db, KIND, "one")
    assert _wait_for(lambda: _row(db, job_id)[0] != "waiting" and _row(db, job_id)[0] != "running", 30), _row(db, job_id)
    assert _row(db, job_id) == ("paused", CLOSED)
