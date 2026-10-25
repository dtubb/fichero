"""The memory gate lets go of the models the engine holds idle before it says 'memory is tight' (#6129). Owner, 2026-10-25: the
engine's embedding worker held ~10 GB while 'Make vectors' and 'Tie text' sat in Activity at 'Waiting: memory is tight'."""
from __future__ import annotations

import time

from fichero_server.db import embeddings
from fichero_server.execution import jobs, throttle


class _Embedder:
    closed = False

    def close(self):
        self.closed = True


def _tight_while_an_embedder_is_held(monkeypatch):
    held = _Embedder()
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {"bge-m3": held})
    monkeypatch.setattr(embeddings, "_EMBEDDER_IN_USE", {})
    monkeypatch.setattr(embeddings, "_EMBEDDER_LAST_USE", {"bge-m3": time.monotonic()})  # used a moment ago: not idle by the clock
    monkeypatch.setattr(throttle, "why_wait",
                        lambda **k: f"{throttle.MEMORY_REASON}: a model needs about 2.5 GB" if embeddings._EMBEDDER_CACHE else None)
    return held


def test_the_idle_embedder_is_released_before_a_wait_is_reported(monkeypatch):
    held = _tight_while_an_embedder_is_held(monkeypatch)
    assert jobs.why_wait_freeing_idle(person_waiting=True, model="kraken:blla") is None
    assert held.closed and not embeddings._EMBEDDER_CACHE


def test_an_embedder_a_call_is_using_stays_and_the_wait_is_said(monkeypatch):
    held = _tight_while_an_embedder_is_held(monkeypatch)
    monkeypatch.setattr(embeddings, "_EMBEDDER_IN_USE", {"bge-m3": 1})
    assert jobs.why_wait_freeing_idle(person_waiting=True, model="kraken:blla").startswith(throttle.MEMORY_REASON)
    assert not held.closed


def test_the_asked_models_own_family_is_kept(monkeypatch):
    held = _tight_while_an_embedder_is_held(monkeypatch)
    assert jobs.why_wait_freeing_idle(person_waiting=True, model="embedder").startswith(throttle.MEMORY_REASON)
    assert not held.closed


def test_another_reason_than_memory_releases_nothing(monkeypatch):
    held = _tight_while_an_embedder_is_held(monkeypatch)
    monkeypatch.setattr(throttle, "why_wait", lambda **k: "Waiting: the Mac is on battery")
    assert jobs.why_wait_freeing_idle(person_waiting=False) == "Waiting: the Mac is on battery"
    assert not held.closed
