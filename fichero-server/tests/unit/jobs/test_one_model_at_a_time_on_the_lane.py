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


def _memory(monkeypatch, *, free_gib: float, need_gib: float, physical_gib: float = 32) -> None:
    """The free memory, the load's need, and the Mac's total (a 16 GB host and a 32 GB one decide differently: the tests never
    depend on the machine they run on)."""
    from fichero_server.execution import throttle

    monkeypatch.setattr(jobs, "_physical_memory_bytes", lambda: int(physical_gib * GIB), raising=False)
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
    picks: list[str] = []  # every scan: which thread, what was loaded, whether the loaded model's pages were seen queued, what it picked
    real_next, real_queued = jobs._Scheduler._next, jobs._loaded_work_queued

    def queued(keys, lane_):
        seen = real_queued(keys, lane_)
        picks.append(f"queued? loaded={lane_.loaded_model} keys={len(keys)} -> {seen}")
        return seen

    def spy(self, lane_, **kw):
        found = real_next(self, lane_, **kw)
        if lane_.name == "local-ml":
            subject = found[1].execute_fetchone("SELECT subject FROM jobs WHERE id = ?", [found[2][0]])[0] if found else None
            picks.append(f"{threading.current_thread().name} loaded={lane_.loaded_model} running={list(lane_.running)} -> {subject}")
        return found

    monkeypatch.setattr(jobs, "_loaded_work_queued", queued)
    monkeypatch.setattr(jobs._Scheduler, "_next", spy)
    jobs.enqueue(db, KRAKEN, "a1-hold")
    assert _wait_for(lambda: "a1-hold" in lane.ran)
    jobs.enqueue(db, KRAKEN, "a2")
    jobs.enqueue(db, KRAKEN, "a3")
    jobs.enqueue(db, VLM, "b1")
    jobs.enqueue(db, VLM, "b2")
    jobs.enqueue(db, VLM, "person-b", started_by="owner")
    lane.gate.set()  # the page in flight ends: the next boundary
    assert _wait_for(lambda: len(lane.ran) == 6)
    # What the lane had loaded as each page started, and what it released, say WHY if the order is wrong (#5357 flake, M4 2026-10-20:
    # A,A then B means the lane handed back to A while b1/b2 were queued; this prints whether `loaded_model` was B at that pick).
    why = f"ran={lane.ran} loaded_at_run={lane.loaded_at_run} swaps={lane.swaps} picks={picks}"
    assert lane.ran == ["a1-hold", "person-b", "b1", "b2", "a2", "a3"], why  # the person's, B's queued pages, back to A


def test_on_a_16_gb_mac_a_vlm_after_kraken_frees_kraken_however_much_looks_free(db, lane, monkeypatch):
    """`activity.lane.small-mac-one-heavy-model`: at 16 GB or less never two heavy models, whatever macOS's 'free' says."""
    _memory(monkeypatch, free_gib=20, need_gib=8, physical_gib=16)
    jobs.enqueue(db, KRAKEN, "k1")
    assert _wait_for(lambda: "k1" in lane.ran)
    jobs.enqueue(db, VLM, "v1")
    assert _wait_for(lambda: "v1" in lane.ran)
    assert [s for s in lane.swaps if s.startswith("kraken:")], lane.swaps  # Kraken was freed before the served model ran


def test_on_a_16_gb_mac_kraken_after_a_served_model_stops_the_served_model(db, lane, monkeypatch):
    _memory(monkeypatch, free_gib=20, need_gib=2, physical_gib=16)
    jobs.enqueue(db, VLM, "v1")
    assert _wait_for(lambda: "v1" in lane.ran)
    jobs.enqueue(db, KRAKEN, "k1")
    assert _wait_for(lambda: "k1" in lane.ran)
    assert [s for s in lane.swaps if s.startswith("local-model:")], lane.swaps  # the served model was stopped before Kraken loaded


def test_on_a_32_gb_mac_both_still_stay_when_both_fit(db, lane, monkeypatch):
    _memory(monkeypatch, free_gib=20, need_gib=2, physical_gib=32)
    jobs.enqueue(db, VLM, "v1")
    assert _wait_for(lambda: "v1" in lane.ran)
    jobs.enqueue(db, KRAKEN, "k1")
    assert _wait_for(lambda: "k1" in lane.ran)
    assert lane.swaps == []


def test_on_a_16_gb_mac_kraken_does_not_load_beside_a_served_model_that_could_not_be_released(db, lane, monkeypatch):
    """## 844 MED 2: a release that frees nothing (a call still reads from the served model) is not a switch: the job waits with its
    reason and Kraken never loads beside the 7B."""
    _memory(monkeypatch, free_gib=20, need_gib=2, physical_gib=16)
    jobs.enqueue(db, VLM, "v1")
    assert _wait_for(lambda: "v1" in lane.ran)
    stuck = {"on": True}
    monkeypatch.setattr(jobs, "RELEASE_RETRY_SECONDS", 0.05)
    monkeypatch.setitem(jobs._RELEASE, "local-model", lambda reason="": (lane.swaps.append("tried"), not stuck["on"])[1])
    jobs.enqueue(db, KRAKEN, "k1")
    assert _wait_for(lambda: "tried" in lane.swaps)
    time.sleep(0.4)
    assert "k1" not in lane.ran, "Kraken loaded beside a served model that was not released"
    assert jobs._scheduler.lanes["local-ml"].loaded_model == "omlx:big-vlm"
    row = db.execute_fetchone("SELECT state, reason FROM jobs WHERE subject = 'k1'")  # it keeps waiting with its reason, in the lane
    assert row[0] in ("waiting", "running") and "still using" in (row[1] or "")
    stuck["on"] = False  # the call ended: the next try frees it and Kraken goes on
    assert _wait_for(lambda: "k1" in lane.ran)
    assert lane.swaps.count("tried") >= 2  # it asked again, and the second try freed it
