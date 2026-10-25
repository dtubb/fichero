"""The memory hold lets go of the models the engine holds idle (#6129). Owner, 2026-10-25: the engine's embedding worker held ~10 GB
while 'Make vectors' and 'Tie text' sat in Activity at 'Waiting: memory is tight'. Review 1236: the freeing runs with no lock held
(closing a process and a collect under `_heavy_pick` stalled every heavy lane), keeps the lane's loaded family, and leaves Kraken
alone while a page reads."""
from __future__ import annotations

import threading
import time

from fichero_server.db import embeddings
from fichero_server.execution import jobs, throttle


class _Embedder:
    closed = False

    def close(self):
        self.closed = True


def _embedder_held(monkeypatch):
    held = _Embedder()
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {"bge-m3": held})
    monkeypatch.setattr(embeddings, "_EMBEDDER_IN_USE", {})
    monkeypatch.setattr(embeddings, "_EMBEDDER_LAST_USE", {"bge-m3": time.monotonic()})  # used a moment ago
    return held


def test_a_memory_hold_asks_for_the_idle_models_to_be_freed_on_the_next_claim(monkeypatch):
    sched, lane = jobs._scheduler, jobs._scheduler.lanes["local-ml"]
    lane.free_idle_for = None
    monkeypatch.setattr(throttle, "why_wait", lambda **k: f"{throttle.MEMORY_REASON}: a model needs about 2.5 GB")
    monkeypatch.setattr(sched, "_say_why_background_waits", lambda *a: None)
    monkeypatch.setattr(sched, "_next", lambda lane, background=True: None)
    sched._claim_one(lane)
    assert lane.free_idle_for is not None
    lane.free_idle_for = None


def test_the_freeing_runs_before_the_heavy_pick_lock_is_taken(monkeypatch):
    sched, lane = jobs._scheduler, jobs._scheduler.lanes["local-ml"]
    held = _embedder_held(monkeypatch)
    locked_at_release = []
    real = jobs.release_idle_models
    monkeypatch.setattr(jobs, "release_idle_models",
                        lambda **k: locked_at_release.append((sched._heavy_pick.locked(), lane.pick.locked())) or real(**k))
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: False)
    monkeypatch.setattr(throttle, "memory_is_busy", lambda: False)
    monkeypatch.setattr(sched, "_claim_one", lambda lane: None)
    lane.free_idle_for, lane.loaded_model = {None}, None
    sched._claim(lane)
    assert locked_at_release == [(False, False)], "the freeing ran with a lock held"
    assert held.closed and lane.free_idle_for is None


def test_the_lanes_loaded_family_is_kept(monkeypatch):
    sched, lane = jobs._scheduler, jobs._scheduler.lanes["local-ml"]
    held = _embedder_held(monkeypatch)
    monkeypatch.setattr(sched, "_claim_one", lambda lane: None)
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: False)
    monkeypatch.setattr(throttle, "memory_is_busy", lambda: False)
    lane.free_idle_for, lane.loaded_model = {None}, "embedder"
    try:
        sched._claim(lane)
    finally:
        lane.loaded_model = None
    assert not held.closed, "the embedder is the next job's: it was released"


def test_an_embedder_a_call_is_using_stays(monkeypatch):
    held = _embedder_held(monkeypatch)
    monkeypatch.setattr(embeddings, "_EMBEDDER_IN_USE", {"bge-m3": 1})
    assert jobs.release_idle_models() == []
    assert not held.closed


def test_kraken_stays_while_a_page_reads(monkeypatch):
    from fichero_server.llm import kraken_runtime

    monkeypatch.setattr(kraken_runtime, "_RESIDENT", {"read": ("model", object())})
    reading, done = threading.Event(), threading.Event()

    def page():
        with kraken_runtime._INFERENCE_LOCK:  # a page reading holds Kraken's lock
            reading.set()
            done.wait(10)

    thread = threading.Thread(target=page)
    thread.start()
    reading.wait(10)
    try:
        assert "Kraken" not in jobs.release_idle_models()
        assert kraken_runtime._RESIDENT, "Kraken's readers were released under a page that reads"
    finally:
        done.set()
        thread.join(10)
    assert "Kraken" in jobs.release_idle_models()  # idle again: it goes
    assert not kraken_runtime._RESIDENT


def test_only_the_memory_hold_asks_for_it():
    assert jobs.memory_holds(f"{throttle.MEMORY_REASON}: x") and not jobs.memory_holds("Waiting: the Mac is on battery")
    assert not jobs.memory_holds(None)


def test_the_held_jobs_own_family_is_kept_beside_the_loaded_one(monkeypatch):
    """review 1248: a held embed job must not have the embedder freed under it only to load it again."""
    sched, lane = jobs._scheduler, jobs._scheduler.lanes["local-ml"]
    held = _embedder_held(monkeypatch)
    monkeypatch.setattr(throttle, "why_wait", lambda **k: f"{throttle.MEMORY_REASON}: a model needs about 0.3 GB")
    sched._ask_to_free_idle(lane, f"{throttle.MEMORY_REASON}: x", "embedder")  # the job held is an embed
    lane.loaded_model = "kraken:blla"
    try:
        sched._free_idle_when_asked(lane)
    finally:
        lane.loaded_model = None
    assert not held.closed and lane.free_idle_for is None


def test_two_threads_asking_and_taking_neither_lose_an_ask_nor_free_twice(monkeypatch):
    sched, lane = jobs._scheduler, jobs._scheduler.lanes["local-ml"]
    calls = []
    monkeypatch.setattr(jobs, "release_idle_models", lambda **k: calls.append(k) or [])
    lane.free_idle_for = None
    sched._ask_to_free_idle(lane, f"{throttle.MEMORY_REASON}: x", None)
    threads = [threading.Thread(target=sched._free_idle_when_asked, args=(lane,)) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert len(calls) == 1, f"freed {len(calls)} times for one ask"
