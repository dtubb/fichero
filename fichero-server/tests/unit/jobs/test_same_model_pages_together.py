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


def test_the_lanes_own_pages_in_the_gate_are_not_a_page_outside_the_queue():
    """With r1's gate, `locked()` is True while ANY page reads. A queued page must not wait for the other queued page
    (`_kraken_busy(queued=1)`), but still waits for a page outside the queue or a whole hold."""
    import threading

    from fichero_server.llm import kraken_runtime as kr

    gate = kr._INFERENCE_LOCK
    inside, release = threading.Event(), threading.Event()

    def one_page():
        with gate.page(2):
            inside.set()
            release.wait(10)

    reader = threading.Thread(target=one_page, daemon=True)
    reader.start()
    assert inside.wait(5)
    try:
        assert jobs._kraken_busy() is True  # nobody told it the page is the lane's own
        assert jobs._kraken_busy(queued=1) is False  # one queued page reading: the second may start
        assert jobs._kraken_busy(queued=0) is True  # a page outside the queue
    finally:
        release.set()
        reader.join(5)
    assert jobs._kraken_busy() is False
    with gate:  # held whole: always busy
        assert jobs._kraken_busy(queued=1) is True


def test_the_third_page_says_two_pages_of_its_model_are_already_reading(db, lane):
    ids = [jobs.enqueue(db, KRAKEN, f"w{number}", started_by="owner") for number in range(3)]
    assert _wait_for(lambda: len(lane.started) == 2)
    waiting = next(i for i in ids if jobs.read_job(db, i)["state"] == "waiting")
    assert jobs.waiting_reason(db, waiting, KRAKEN) == jobs.pages_at_cap_reason(2) == "Waiting: two pages of this model are already reading"
    other = jobs.enqueue(db, VLM, "wv", started_by="owner")  # a different model is not waiting on the cap
    assert jobs.waiting_reason(db, other, VLM) != jobs.pages_at_cap_reason(2)
