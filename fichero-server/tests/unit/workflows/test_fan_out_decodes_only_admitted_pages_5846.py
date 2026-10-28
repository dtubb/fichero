"""A fan-out hands the model lane its pages as work to do, never as decoded images: a page waiting for the lane holds no
bitmap, and the lane decodes at most `pages_at_once` at a time (`recipes-run.memory.fan-out-does-not-decode-ahead`, #5846).
58 pages queued is 58 rows, not 58 x 32 MB. Real scheduler and lane; the page's work is a stub that records its decode."""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def lane(monkeypatch):
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    monkeypatch.setattr(jobs, "_kraken_pages_at_once", lambda: 2)
    monkeypatch.setattr(jobs, "_kraken_busy", lambda queued=0: False)
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")


def test_queued_pages_hold_no_decoded_image_and_at_most_the_gates_number_decode(db, lane):
    release = threading.Event()
    decoded: list[str] = []

    def page(name: str):
        def work():
            decoded.append(name)  # the page's image is read HERE, once the lane admits it
            release.wait(30)
            return name
        return work

    futures = [jobs.submit(db, "read-a-page", f"page-{n}", model="kraken:blla", fn=page(f"page-{n}")) for n in range(6)]
    try:
        assert _wait_for(lambda: len(decoded) >= 1)
        time.sleep(0.5)  # the lane has had time to admit more if it would

        assert 1 <= len(decoded) <= 2  # never 6 bitmaps: the waiting pages are rows
        waiting = db.execute_fetchone("SELECT count(*) FROM jobs WHERE kind = 'read-a-page' AND state = 'waiting'")[0]
        assert waiting == 6 - len(decoded)
    finally:
        release.set()
    assert sorted(f.result(timeout=30) for f in futures) == [f"page-{n}" for n in range(6)]
    assert len(decoded) == 6
