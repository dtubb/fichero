"""Activity shows which models the engine holds and what each takes (#6129): the engine's own memory is part of 'memory is tight'."""
from __future__ import annotations

import time

from fichero_server.db import embeddings
from fichero_server.execution import models_held as held
from fichero_server.execution import throttle


class _Embedder:
    class _Process:
        pid = 4242

    _process = _Process()


def test_the_search_embedder_is_listed_with_its_childs_size(monkeypatch):
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {"BAAI/bge-m3": _Embedder()})
    monkeypatch.setattr(held, "process_bytes", lambda pid: 10 * 1024**3 if pid == 4242 else None)
    assert held.models_held()[0] == {"name": "BAAI/bge-m3", "kind": "search embedder", "memory_bytes": 10 * 1024**3}


def test_nothing_loaded_lists_nothing(monkeypatch):
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {})
    assert [m for m in held.models_held() if m["kind"] == "search embedder"] == []


def test_the_machine_state_carries_them(monkeypatch):
    monkeypatch.setattr(held, "models_held", lambda: [{"name": "m", "kind": "Kraken", "memory_bytes": None}])
    assert throttle.machine_state()["models_held"] == [{"name": "m", "kind": "Kraken", "memory_bytes": None}]


def test_a_process_that_is_gone_has_no_size():
    assert held.process_bytes(None) is None and held.process_bytes(0) is None


def test_the_size_cache_forgets_a_process_that_was_not_asked_about_for_a_while(monkeypatch):
    held._RSS.clear()
    held._RSS[111] = (time.monotonic() - 1000, 5)
    monkeypatch.setattr(held.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": "2048\n"})())
    assert held.process_bytes(222) == 2048 * 1024
    assert 111 not in held._RSS and 222 in held._RSS
