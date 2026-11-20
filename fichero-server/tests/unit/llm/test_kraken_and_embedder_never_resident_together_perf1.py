"""The embedder and Kraken are never loaded together (owner rule 2026-11-19): one releases the other, or the work waits."""
import pytest

from fichero_server.db import embed_process, embeddings
from fichero_server.execution.throttle import MemoryShortError
from fichero_server.llm import kraken_runtime


class _Embedder:
    closed = False

    def close(self):
        self.closed = True


@pytest.fixture
def clean(monkeypatch):
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {})
    monkeypatch.setattr(embeddings, "_EMBEDDER_IN_USE", {})
    monkeypatch.setattr(embeddings, "_EMBEDDER_LAST_USE", {})
    monkeypatch.setattr(kraken_runtime, "_RESIDENT", {})
    monkeypatch.setattr(kraken_runtime, "_a_run_has_pages_in_flight", lambda: False)
    monkeypatch.setattr(embeddings, "_LOAD_FAILURES", {})
    monkeypatch.setattr(embed_process, "in_process", lambda: True)


def test_kraken_loading_releases_an_idle_embedder(clean):
    held = _Embedder()
    embeddings._EMBEDDER_CACHE["m"] = held
    kraken_runtime._resident_locked("segment", "blla", lambda: object())
    assert held.closed and "m" not in embeddings._EMBEDDER_CACHE


def test_kraken_loading_waits_while_an_embed_holds_the_embedder(clean):
    held = _Embedder()
    embeddings._EMBEDDER_CACHE["m"] = held
    embeddings._EMBEDDER_IN_USE["m"] = 1
    with pytest.raises(MemoryShortError):
        kraken_runtime._resident_locked("segment", "blla", lambda: pytest.fail("loaded beside the embedder"))
    assert not held.closed and not kraken_runtime._RESIDENT


def test_the_embedder_loading_releases_resident_kraken(clean, monkeypatch):
    kraken_runtime._RESIDENT["segment"] = ("blla", object())
    loaded = []
    monkeypatch.setattr(embed_process, "load_text_embedding", lambda *a: loaded.append(not kraken_runtime._RESIDENT) or _Embedder())
    embeddings._get_shared_embedder("m", "/nowhere")
    assert loaded == [True]


def test_the_embedder_waits_while_a_kraken_page_runs(clean, monkeypatch):
    kraken_runtime._RESIDENT["segment"] = ("blla", object())
    monkeypatch.setattr(kraken_runtime, "_a_run_has_pages_in_flight", lambda: True)
    monkeypatch.setattr(embed_process, "load_text_embedding", lambda *a: pytest.fail("loaded beside Kraken"))
    with pytest.raises(MemoryShortError):
        embeddings._get_shared_embedder("m", "/nowhere")
    assert kraken_runtime._RESIDENT


def test_the_embedder_waits_while_the_page_gate_is_held(clean, monkeypatch):
    kraken_runtime._RESIDENT["segment"] = ("blla", object())
    monkeypatch.setattr(embed_process, "load_text_embedding", lambda *a: pytest.fail("loaded beside Kraken"))
    assert kraken_runtime._INFERENCE_LOCK.acquire(blocking=False)
    try:
        with pytest.raises(MemoryShortError):
            embeddings._get_shared_embedder("m", "/nowhere")
    finally:
        kraken_runtime._INFERENCE_LOCK.release()
