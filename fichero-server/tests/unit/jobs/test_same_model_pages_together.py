"""`activity.lane.same-model-pages-together`: the model lane runs two pages of the same model together for a person's run
when memory allows; a third waits, a different model waits, background stays at one. Real lane and rows; work faked."""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs

KRAKEN, VLM = "kraken-page-tg", "vlm-page-tg"


def _wait_for(predicate, seconds=30.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def lane(monkeypatch):
    started: list[str] = []
    gate = threading.Event()

    def work(db, subject):
        started.append(subject)
        gate.wait(30)

    monkeypatch.setitem(jobs.KINDS, KRAKEN, jobs.Kind(run=work, model="kraken:blla", lane="local-ml", name="Read a page"))
    monkeypatch.setitem(jobs.KINDS, VLM, jobs.Kind(run=work, model="omlx:big-vlm", lane="local-ml", name="VLM page"))
    monkeypatch.setitem(jobs._RELEASE, "kraken", lambda reason="": None)
    monkeypatch.setitem(jobs._RELEASE, "local-model", lambda reason="": None)
    monkeypatch.setattr(jobs, "_kraken_pages_at_once", lambda: 2)
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    yield type("Lane", (), {"started": started, "gate": gate})
    gate.set()


def test_two_pages_of_a_persons_run_run_together_and_a_third_waits(db, lane):
    for number in range(3):
        jobs.enqueue(db, KRAKEN, f"p{number}", started_by="owner")
    assert _wait_for(lambda: len(lane.started) == 2)
    time.sleep(0.3)
    assert len(lane.started) == 2, "a third page started beside two"
    lane.gate.set()
    assert _wait_for(lambda: len(lane.started) == 3)


def test_background_pages_stay_one_at_a_time(db, lane):
    for number in range(2):
        jobs.enqueue(db, KRAKEN, f"b{number}", started_by="automatic")
    assert _wait_for(lambda: len(lane.started) == 1)
    time.sleep(0.3)
    assert len(lane.started) == 1


def test_a_different_model_waits_for_the_pages_running(db, lane):
    jobs.enqueue(db, KRAKEN, "k0", started_by="owner")
    assert _wait_for(lambda: "k0" in lane.started)
    jobs.enqueue(db, VLM, "v0", started_by="owner")
    time.sleep(0.3)
    assert "v0" not in lane.started


def test_when_memory_holds_only_one_page_it_stays_one(db, lane, monkeypatch):
    monkeypatch.setattr(jobs, "_kraken_pages_at_once", lambda: 1)
    for number in range(2):
        jobs.enqueue(db, KRAKEN, f"m{number}", started_by="owner")
    assert _wait_for(lambda: len(lane.started) == 1)
    time.sleep(0.3)
    assert len(lane.started) == 1
