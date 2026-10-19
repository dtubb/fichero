"""One model at a time on the lane, unloaded only when memory needs it (owner rulings 2026-10-19; speed review fix 3).

Real lanes and real job rows; the work is faked. `_RELEASE[...]` is what unloads a model when the lane moves to another
heavy one, so recording it counts the swaps.
"""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs

GIB = 1024**3
KRAKEN, VLM, EMBED, VISION = "kraken-page-omt", "vlm-page-omt", "embed-omt", "vision-omt"


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
    loaded_at_run: list[str | None] = []
    swaps: list[str] = []
    gate = threading.Event()

    def work(db, subject):
        ran.append(subject)
        loaded_at_run.append(jobs._scheduler.lanes["local-ml"].loaded_model)
        if subject.endswith("-hold"):
            gate.wait(30)

    monkeypatch.setitem(jobs.KINDS, KRAKEN, jobs.Kind(run=work, model="kraken:blla", lane="local-ml", name="Read a page"))
    monkeypatch.setitem(jobs.KINDS, VLM, jobs.Kind(run=work, model="omlx:big-vlm", lane="local-ml", name="VLM page"))
    monkeypatch.setitem(jobs.KINDS, EMBED, jobs.Kind(run=work, model="embedder", lane="embed", name="Embed"))
    monkeypatch.setitem(jobs.KINDS, VISION, jobs.Kind(run=work, model="apple:vision", lane="search", name="Vision"))
    monkeypatch.setitem(jobs._RELEASE, "kraken", lambda reason="": swaps.append(f"kraken: {reason}"))
    monkeypatch.setitem(jobs._RELEASE, "local-model", lambda reason="": swaps.append(f"local-model: {reason}"))
    monkeypatch.setitem(jobs._RELEASE, "embedder", lambda reason="": swaps.append(f"embedder: {reason}"))
    monkeypatch.setattr(jobs, "SWITCH_AFTER_QUIET_SECONDS", 0.05)
    monkeypatch.setattr(jobs, "THROTTLE_LOOK_AGAIN_SECONDS", 0.05)
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "0")
    yield type("Lane", (), {"ran": ran, "swaps": swaps, "gate": gate, "loaded_at_run": loaded_at_run})
    gate.set()


def _memory(monkeypatch, *, free_gib: float, need_gib: float) -> None:
    from fichero_server.execution import throttle

    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: int(free_gib * GIB))
    monkeypatch.setattr(jobs, "_model_need_bytes", lambda _model: int(need_gib * GIB))


def test_vision_work_during_a_kraken_run_unloads_nothing_and_does_not_wait_for_the_heavy_lane(db, lane, monkeypatch):
    _memory(monkeypatch, free_gib=1, need_gib=6)  # tight: nothing would fit, yet Vision evicts nothing
    jobs.enqueue(db, KRAKEN, "k-hold")
    assert _wait_for(lambda: "k-hold" in lane.ran)
    future = jobs.submit(db, VISION, "page-1", model="apple:vision", fn=lambda: lane.ran.append("vision-page") or "ok")
    assert future.result(timeout=30) == "ok"  # ran while the heavy lane's one slot was held by Kraken
    assert lane.swaps == [] and jobs._scheduler.lanes["local-ml"].loaded_model == "kraken:blla"


def test_an_embed_during_a_kraken_run_unloads_nothing(db, lane):
    jobs.enqueue(db, KRAKEN, "k-hold")
    assert _wait_for(lambda: "k-hold" in lane.ran)
    jobs.enqueue(db, EMBED, "e1")
    assert _wait_for(lambda: "e1" in lane.ran)  # beside Kraken, on its own lane
    assert lane.swaps == [] and jobs._scheduler.lanes["local-ml"].loaded_model == "kraken:blla"


def test_a_vlm_and_kraken_that_both_fit_stay_loaded_together(db, lane, monkeypatch):
    _memory(monkeypatch, free_gib=20, need_gib=8)
    jobs.enqueue(db, KRAKEN, "k1")
    assert _wait_for(lambda: "k1" in lane.ran)
    jobs.enqueue(db, VLM, "v1")
    assert _wait_for(lambda: "v1" in lane.ran)
    assert lane.swaps == []  # nothing unloaded: both fit


def test_when_they_do_not_fit_ten_interleaved_pages_cause_at_most_two_swaps(db, lane, monkeypatch):
    _memory(monkeypatch, free_gib=3, need_gib=8)
    jobs.set_paused(True)
    for number in range(5):
        jobs.enqueue(db, KRAKEN, f"k{number}")
        jobs.enqueue(db, VLM, f"v{number}")
    jobs.set_paused(False)
    assert _wait_for(lambda: len(lane.ran) == 10)
    assert len(lane.swaps) <= 2, lane.swaps
    assert all("memory:" in swap for swap in lane.swaps)  # each says why: the memory it needed


def test_embed_kraken_and_vlm_interleaved_load_each_heavy_model_once(db, lane, monkeypatch):
    _memory(monkeypatch, free_gib=3, need_gib=8)
    jobs.set_paused(True)
    for number in range(4):
        for kind in (KRAKEN, EMBED, VLM):
            jobs.enqueue(db, kind, f"{kind}-{number}")
    jobs.set_paused(False)
    assert _wait_for(lambda: len(lane.ran) == 12)
    heavy = [m for m in lane.loaded_at_run if m in ("kraken:blla", "omlx:big-vlm")]
    changes = sum(1 for before, after in zip(heavy, heavy[1:]) if before != after)
    assert changes <= 1  # two distinct heavy models: loaded once each (one change between them)
    assert "embedder" not in lane.loaded_at_run  # a small model is never "the loaded model"


def test_a_person_job_for_another_model_goes_at_the_next_page_boundary_and_its_pages_follow_it(db, lane, monkeypatch):
    _memory(monkeypatch, free_gib=3, need_gib=8)
    jobs.enqueue(db, KRAKEN, "a1-hold")
    assert _wait_for(lambda: "a1-hold" in lane.ran)
    jobs.enqueue(db, KRAKEN, "a2")
    jobs.enqueue(db, KRAKEN, "a3")
    jobs.enqueue(db, VLM, "b1")
    jobs.enqueue(db, VLM, "b2")
    jobs.enqueue(db, VLM, "person-b", started_by="owner")
    lane.gate.set()  # the page in flight ends: the next boundary
    assert _wait_for(lambda: len(lane.ran) == 6)
    assert lane.ran == ["a1-hold", "person-b", "b1", "b2", "a2", "a3"]  # the person's, B's queued pages, back to A
