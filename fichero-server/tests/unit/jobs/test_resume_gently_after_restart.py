"""An interrupted run resumes by itself on the next open, one page at a time for its first minute
(`recipes-run.restart.resumes-at-once-gently`, #6216; ruling 2)."""
from __future__ import annotations

import pytest

from fichero_server.execution import jobs
from fichero_server.llm import kraken_runtime


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(jobs.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(jobs, "_gentle_until", None)
    monkeypatch.setattr(jobs._scheduler, "wake", lambda key: None)
    return now


@pytest.fixture
def two_pages_allowed(monkeypatch):
    """A Mac whose gate lets two pages in for a person's run."""
    monkeypatch.setattr("fichero_server.core.compute_preferences.priority_for", lambda person: "fast")
    monkeypatch.setattr("fichero_server.execution.throttle.memory_is_busy", lambda: False)
    monkeypatch.setattr("fichero_server.core.cores.cores_available", lambda: (8, "mac"))
    monkeypatch.setattr("fichero_server.core.cores.is_a_mac_pipeline_host", lambda source: True)
    monkeypatch.setattr(kraken_runtime, "page_fan_out", lambda cap: cap)


def _interrupted(db):
    jobs._ensure(db)
    job_id = jobs._insert(db, "embed", "page-1", None, "automatic")
    db.execute("UPDATE jobs SET state = 'running', attempts = 1 WHERE id = ?", [job_id])
    return job_id


def test_an_open_that_finds_interrupted_work_reads_one_page_at_a_time_for_a_minute(db, clock, two_pages_allowed):
    assert kraken_runtime.pages_at_once_and_why(True) == (2, None)
    job_id = _interrupted(db)

    jobs.resume(db)

    assert db.execute_fetchone("SELECT state FROM jobs WHERE id = ?", [job_id])[0] == "waiting"  # resumes, no one asked
    assert kraken_runtime.pages_at_once_and_why(True) == (1, jobs.RESUMING_WORDS)
    images = jobs._Lane("images", 2)
    images.running = {"a": None}
    assert not images.may_start("thumbnail", None)  # every lane: one at a time
    clock[0] += jobs.GENTLE_START_SECONDS
    assert kraken_runtime.pages_at_once_and_why(True) == (2, None)  # the gate's own number again
    assert images.may_start("thumbnail", None)


def test_an_open_with_nothing_interrupted_is_not_gentle(db, clock, two_pages_allowed):
    jobs._ensure(db)

    jobs.resume(db)

    assert kraken_runtime.pages_at_once_and_why(True) == (2, None)


def test_a_page_held_by_the_gentle_minute_says_so(db, clock, two_pages_allowed, monkeypatch):
    _interrupted(db)
    jobs.resume(db)
    images = jobs._scheduler.lanes["images"]
    monkeypatch.setattr(images, "running", {"another-page": None})
    monkeypatch.setitem(jobs.KINDS, "thumbnail", jobs.Kind(run=lambda db, subject: None, model=None, lane="images",
                                                           name="Make thumbnails", first=True))
    waiting = jobs._insert(db, "thumbnail", "page-2", None, "automatic")

    reason = jobs.waiting_reason(db, waiting, "thumbnail")

    assert reason == f"Waiting: {jobs.RESUMING_WORDS}"
    assert jobs.RESUMING_WORDS == "resuming after a restart: one page at a time for a minute"
