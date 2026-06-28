"""Whisper should load once per process, not once per transcription call.

Regression coverage for the "heavy process-global model re-instantiated per
call/thread" bug class. Mirrors the embedder cache tests: same identity loads
once, distinct identities load once each, and concurrent callers still build
the model exactly once.
"""

from __future__ import annotations

import sys
import types

import pytest

from fichero.workflows.tools import audio_base


@pytest.fixture(autouse=True)
def _clear_whisper_cache():
    audio_base._WHISPER_MODEL_CACHE.clear()
    yield
    audio_base._WHISPER_MODEL_CACHE.clear()


def _install_counting_whisper(monkeypatch):
    calls = {"n": 0}

    def _load_model(model_size, download_root, device=None):
        calls["n"] += 1
        return {
            "model_size": model_size,
            "download_root": download_root,
            "device": device,
        }

    fake = types.ModuleType("whisper")
    fake.load_model = _load_model
    monkeypatch.setitem(sys.modules, "whisper", fake)
    return calls


def test_same_model_loads_once_across_many_callers(monkeypatch):
    calls = _install_counting_whisper(monkeypatch)
    root = "/tmp/whisper-cache"

    first = audio_base._get_shared_whisper_model("base", root, None)
    second = audio_base._get_shared_whisper_model("base", root, None)
    third = audio_base._get_shared_whisper_model("base", root, None)

    assert first is second is third
    assert calls["n"] == 1


def test_distinct_identities_each_load_once(monkeypatch):
    calls = _install_counting_whisper(monkeypatch)

    a1 = audio_base._get_shared_whisper_model("base", "/tmp/whisper-a", None)
    b1 = audio_base._get_shared_whisper_model("small", "/tmp/whisper-a", None)
    c1 = audio_base._get_shared_whisper_model("base", "/tmp/whisper-b", None)
    a2 = audio_base._get_shared_whisper_model("base", "/tmp/whisper-a", None)

    assert a1 is a2
    assert a1 is not b1
    assert a1 is not c1
    assert calls["n"] == 3


def test_concurrent_callers_load_once(monkeypatch):
    """Double-checked locking: many threads racing still build once."""
    import threading

    calls = _install_counting_whisper(monkeypatch)
    results: list[object] = []
    barrier = threading.Barrier(8)

    def _worker():
        barrier.wait()
        results.append(audio_base._get_shared_whisper_model("base", "/tmp/whisper", None))

    threads = [threading.Thread(target=_worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert calls["n"] == 1
    assert all(result is results[0] for result in results)


def test_models_base_is_the_shared_folder():
    """Whisper downloads to the ONE shared models folder, not a legacy/scattered
    dir (#2269). Regression for the hardcoded `com.fichero.fichero` bundle path
    that sent Whisper to a different folder than embeddings/spaCy.
    """
    from fichero.paths import engine_state_dir

    assert audio_base.MODELS_BASE == engine_state_dir() / "models"
    # No stale bundle id, no ~/.cache, no per-library scattering.
    assert "com.fichero.fichero" not in str(audio_base.MODELS_BASE)
    assert ".cache" not in str(audio_base.MODELS_BASE)
