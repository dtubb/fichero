"""The embedding model is held only while something needs it (#5283).

`search.embedding-model-only-while-needed`, ruled 2026-10-01. WHY: bge-m3 is about 1.5 GB of the
engine's 1.8 GB (measured 2026-09-30), and the engine loaded it after launch and held it until quit
whether or not anything was embedded or searched. Now it loads on an embed or a semantic search and
is released after a quiet spell; an embed in progress holds it. If this regresses, every session
pays 1.5 GB again: a reference kept somewhere (a Database's own attribute was the old one) keeps
the model alive after its release, and the release looks done while the memory stays.
"""

from __future__ import annotations

import gc
import sys
import time
import types
import weakref

import pytest

from fichero_server.db import embeddings


@pytest.fixture(autouse=True)
def _fake_model(monkeypatch):
    """A fastembed whose models count their loads and can be watched for collection."""
    loads: list[weakref.ref] = []

    class _FakeTextEmbedding:
        def __init__(self, model_name, cache_dir, threads=None, **kwargs):
            loads.append(weakref.ref(self))

        def embed(self, texts):
            for _ in texts:
                yield [0.6, 0.8]

    monkeypatch.setitem(sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=_FakeTextEmbedding))
    monkeypatch.setattr(embeddings, "_register_fastembed_model_for_space", lambda _space: None)
    monkeypatch.setattr(embeddings, "_EMBEDDER_CACHE", {})
    monkeypatch.setattr(embeddings, "_EMBEDDER_LAST_USE", {})
    monkeypatch.setattr(embeddings, "_EMBEDDER_IN_USE", {})
    monkeypatch.setattr(embeddings, "_RELEASER", None)  # a fresh releaser per test, on this test's clock
    yield loads


def _alive(loads) -> int:
    gc.collect()
    return sum(1 for ref in loads if ref() is not None)


def test_a_model_nobody_used_for_the_idle_spell_is_released_and_loads_again_when_needed(_fake_model):
    with embeddings.leased_embedder("model-A", "/tmp/cache"):
        pass
    assert _alive(_fake_model) == 1
    assert embeddings.release_idle_embedders(idle_seconds=0) == ["model-A"]
    assert _alive(_fake_model) == 0, "released means the memory goes, not only the cache entry"
    with embeddings.leased_embedder("model-A", "/tmp/cache"):
        pass
    assert len(_fake_model) == 2, "the next use loads it again"


def test_a_model_used_recently_is_kept(_fake_model):
    with embeddings.leased_embedder("model-A", "/tmp/cache"):
        pass
    assert embeddings.release_idle_embedders(idle_seconds=600) == []
    assert _alive(_fake_model) == 1


def test_a_model_in_use_is_never_released_under_its_embed(_fake_model):
    with embeddings.leased_embedder("model-A", "/tmp/cache") as model:
        assert embeddings.release_idle_embedders(idle_seconds=0) == []
        assert list(model.embed(["still here"])) == [[0.6, 0.8]]
    assert embeddings.release_idle_embedders(idle_seconds=0) == ["model-A"]


def test_a_database_that_embedded_does_not_keep_the_model_alive(_fake_model, db):
    assert db._embed_text("a query") == pytest.approx([0.6, 0.8])
    assert db._embed_texts(["one", "two"]) == [pytest.approx([0.6, 0.8])] * 2
    assert len(_fake_model) == 1, "loaded once, shared"
    embeddings.release_idle_embedders(idle_seconds=0)
    assert _alive(_fake_model) == 0, "a Database held its own reference to the model"


def test_the_model_is_released_by_itself_after_the_idle_spell(_fake_model, monkeypatch):
    monkeypatch.setattr(embeddings, "EMBEDDER_IDLE_SECONDS", 0.2)
    with embeddings.leased_embedder("model-A", "/tmp/cache"):
        pass
    for _ in range(100):
        if _alive(_fake_model) == 0:
            break
        time.sleep(0.05)
    assert _alive(_fake_model) == 0, "nothing released the model once it went quiet"
