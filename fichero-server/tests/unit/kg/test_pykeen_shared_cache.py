"""PyKEEN models should load once per library path, not per prediction.

Regression coverage for the process-global cache added to
``fichero_server.kg.pykeen_predictor.load_model``. Mirrors the embedder cache tests:
same library path loads once, distinct library paths load once each, and
concurrent callers still deserialize the model exactly once.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from types import SimpleNamespace
import types

import pytest

from fichero_server.kg import pykeen_predictor


@pytest.fixture(autouse=True)
def _clear_model_cache():
    pykeen_predictor._MODEL_CACHE.clear()
    yield
    pykeen_predictor._MODEL_CACHE.clear()


def _install_counting_torch(monkeypatch):
    calls = {"n": 0}

    def _load(path, weights_only=False):
        calls["n"] += 1
        return {"path": path, "weights_only": weights_only}

    fake = types.SimpleNamespace(load=_load)
    monkeypatch.setitem(sys.modules, "torch", fake)
    return calls


def _seed_model_artifact(db_path: Path) -> SimpleNamespace:
    model_dir = db_path.parent / "pykeen"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "trained_model.pkl").write_bytes(b"mock-pykeen")
    return SimpleNamespace(path=db_path)


def test_same_library_loads_once_across_many_callers(tmp_path, monkeypatch):
    calls = _install_counting_torch(monkeypatch)
    db = _seed_model_artifact(tmp_path / "library-a" / "db.sqlite")

    first = pykeen_predictor.load_model(db)
    second = pykeen_predictor.load_model(db)
    third = pykeen_predictor.load_model(db)

    assert first is second is third
    assert calls["n"] == 1
    assert first["weights_only"] is True


def test_load_model_uses_torch_weights_only(tmp_path, monkeypatch):
    _install_counting_torch(monkeypatch)
    db = _seed_model_artifact(tmp_path / "library-sec" / "db.sqlite")

    model = pykeen_predictor.load_model(db)

    assert model["weights_only"] is True


def test_distinct_libraries_each_load_once(tmp_path, monkeypatch):
    calls = _install_counting_torch(monkeypatch)
    db_a = _seed_model_artifact(tmp_path / "library-a" / "db.sqlite")
    db_b = _seed_model_artifact(tmp_path / "library-b" / "db.sqlite")

    a1 = pykeen_predictor.load_model(db_a)
    b1 = pykeen_predictor.load_model(db_b)
    a2 = pykeen_predictor.load_model(db_a)

    assert a1 is a2
    assert a1 is not b1
    assert calls["n"] == 2


def test_concurrent_callers_load_once(tmp_path, monkeypatch):
    """Double-checked locking: many threads racing still build once."""
    calls = _install_counting_torch(monkeypatch)
    db = _seed_model_artifact(tmp_path / "library-a" / "db.sqlite")
    results: list[object] = []
    barrier = threading.Barrier(8)

    def _worker():
        barrier.wait()
        results.append(pykeen_predictor.load_model(db))

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls["n"] == 1
    assert all(result is results[0] for result in results)
