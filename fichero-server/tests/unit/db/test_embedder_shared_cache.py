"""The embedding model is loaded ONCE per process, not per Database/thread.

Regression test for the "expensive process-global resource stored as
per-instance state" class of bug: ``db_manager`` creates a ``Database`` per
(package_path, thread_id), so a per-instance embedder reloaded the ~500 MB model
on every worker thread / page. ``_get_shared_embedder`` must cache it
process-globally and hand the same object to every caller.
"""

from __future__ import annotations

import sys
import types

import pytest

from fichero_server.db import embeddings as db_embeddings


@pytest.fixture(autouse=True)
def _clear_embedder_cache():
    db_embeddings._EMBEDDER_CACHE.clear()
    yield
    db_embeddings._EMBEDDER_CACHE.clear()


def _install_counting_fastembed(monkeypatch):
    """Install a fake ``fastembed`` whose TextEmbedding counts constructions."""
    calls = {"n": 0}

    class _FakeTextEmbedding:
        def __init__(self, model_name, cache_dir):  # noqa: D401
            calls["n"] += 1
            self.model_name = model_name

    fake = types.ModuleType("fastembed")
    fake.TextEmbedding = _FakeTextEmbedding
    monkeypatch.setitem(sys.modules, "fastembed", fake)
    return calls


def test_same_model_loads_once_across_many_callers(monkeypatch):
    calls = _install_counting_fastembed(monkeypatch)

    first = db_embeddings._get_shared_embedder("model-A", "/tmp/cache")
    second = db_embeddings._get_shared_embedder("model-A", "/tmp/cache")
    third = db_embeddings._get_shared_embedder("model-A", "/tmp/cache")

    assert first is second is third, "all callers must share one embedder object"
    assert calls["n"] == 1, "model must be constructed exactly once"


def test_distinct_models_each_load_once(monkeypatch):
    calls = _install_counting_fastembed(monkeypatch)

    a1 = db_embeddings._get_shared_embedder("model-A", "/tmp/cache")
    b1 = db_embeddings._get_shared_embedder("model-B", "/tmp/cache")
    a2 = db_embeddings._get_shared_embedder("model-A", "/tmp/cache")

    assert a1 is a2
    assert a1 is not b1
    assert calls["n"] == 2, "one construction per distinct model name"


def test_concurrent_callers_load_once(monkeypatch):
    """Double-checked locking: many threads racing load the model once."""
    import threading

    calls = _install_counting_fastembed(monkeypatch)
    results: list[object] = []
    barrier = threading.Barrier(8)

    def _worker():
        barrier.wait()  # maximise the race
        results.append(db_embeddings._get_shared_embedder("model-A", "/tmp/cache"))

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["n"] == 1, "concurrent threads must still construct exactly once"
    assert all(r is results[0] for r in results)
