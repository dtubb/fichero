"""Unit tests for library prefetch / cache warm (#1918).

Covers:
- _prewarm_embeddings() populates _EMBEDDER_CACHE (not a discarded instance)
- prefetch_library_caches() returns a stats dict with expected keys
- prefetch is idempotent (calling twice doesn't raise)
- prefetch on a non-existent package returns gracefully
"""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

import pytest

from fichero_server.db import embeddings as db_embeddings


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


def _install_counting_fastembed(monkeypatch):
    """Stub fastembed with a fake whose TextEmbedding counts constructions.

    Also installs fastembed.common.model_description because
    _register_e5_fastembed_model imports PoolingType unconditionally before
    its _list_supported_models guard can short-circuit.
    """
    calls = {"n": 0}

    class _FakeTextEmbedding:
        def __init__(self, model_name, cache_dir):
            calls["n"] += 1
            self.model_name = model_name

        @staticmethod
        def list_supported_models():
            return [{"model": "fichero-pinned/multilingual-e5-large-mean-v1"}]

        # No _list_supported_models → _register_e5_fastembed_model returns
        # early after importing PoolingType; no add_custom_model call needed.

    fake = types.ModuleType("fastembed")
    fake.TextEmbedding = _FakeTextEmbedding

    fake_common = types.ModuleType("fastembed.common")
    fake_model_desc = types.ModuleType("fastembed.common.model_description")
    fake_model_desc.PoolingType = object()  # stub — never actually called
    fake_model_desc.ModelSource = lambda **kw: None

    monkeypatch.setitem(sys.modules, "fastembed", fake)
    monkeypatch.setitem(sys.modules, "fastembed.common", fake_common)
    monkeypatch.setitem(sys.modules, "fastembed.common.model_description", fake_model_desc)
    return calls


@pytest.fixture(autouse=True)
def _clear_embedder_cache():
    db_embeddings._EMBEDDER_CACHE.clear()
    yield
    db_embeddings._EMBEDDER_CACHE.clear()


# ---------------------------------------------------------------------------
# _prewarm_embeddings → _EMBEDDER_CACHE is populated
# ---------------------------------------------------------------------------


def test_prewarm_populates_embedder_cache(tmp_path, monkeypatch):
    """After _prewarm_embeddings runs, _EMBEDDER_CACHE must be non-empty.

    Previously the function constructed a throwaway TextEmbedding that was
    immediately discarded, so _EMBEDDER_CACHE stayed empty and every
    subsequent _ensure_embedder() still paid the full model-load cost.
    The fix routes through _get_shared_embedder which writes into the cache.
    """
    calls = _install_counting_fastembed(monkeypatch)

    # MODELS_BASE is locally imported inside _prewarm_embeddings, so patch
    # the source module rather than the main module namespace.
    fake_models_base = tmp_path / "models"
    fake_models_base.mkdir()
    with patch("fichero_server.llm.local_models.MODELS_BASE", fake_models_base):
        from fichero_server.api.main import _prewarm_embeddings

        _prewarm_embeddings()

    assert db_embeddings._EMBEDDER_CACHE, (
        "_EMBEDDER_CACHE must be non-empty after _prewarm_embeddings — "
        "the embedder was likely still being discarded as a local variable."
    )
    assert calls["n"] == 1, "TextEmbedding must be constructed exactly once"


def test_prewarm_then_ensure_embedder_is_cache_hit(tmp_path, monkeypatch):
    """_ensure_embedder() is a near-zero-cost dict lookup after _prewarm_embeddings."""
    calls = _install_counting_fastembed(monkeypatch)
    fake_models_base = tmp_path / "models"
    fake_models_base.mkdir()

    with patch("fichero_server.llm.local_models.MODELS_BASE", fake_models_base):
        from fichero_server.api.main import _prewarm_embeddings

        _prewarm_embeddings()

    assert calls["n"] == 1

    # Simulate what _ensure_embedder does: call _get_shared_embedder.
    from fichero_server.db.embeddings import _configured_embedding_space, _get_shared_embedder

    space = _configured_embedding_space()
    cache_dir = str(fake_models_base / "embeddings")
    _get_shared_embedder(space.fastembed_model_name, cache_dir)

    # Must NOT construct a second instance — it's already in the cache.
    assert calls["n"] == 1, (
        "Second _get_shared_embedder call should be a cache hit, "
        "not a second TextEmbedding construction."
    )


# ---------------------------------------------------------------------------
# prefetch_library_caches
# ---------------------------------------------------------------------------


def test_prefetch_library_caches_returns_stats(test_package):
    """prefetch_library_caches returns a dict with the expected keys."""
    from fichero_server.api.main import prefetch_library_caches

    stats = prefetch_library_caches(test_package)

    assert "package_path" in stats
    assert "embedder_warmed" in stats
    assert "lance_tables_opened" in stats
    assert isinstance(stats["lance_tables_opened"], int)
    assert stats["lance_tables_opened"] >= 0


def test_prefetch_library_caches_nonexistent_package(tmp_path):
    """prefetch_library_caches on a missing path returns gracefully (no raise)."""
    from fichero_server.api.main import prefetch_library_caches

    missing = tmp_path / "nonexistent.fichero"
    stats = prefetch_library_caches(missing)

    assert stats["package_path"] == str(missing)
    # embedder_warmed is a bool — exact value depends on whether fastembed
    # is installed and the model is cached; we only assert type + no raise.
    assert isinstance(stats["embedder_warmed"], bool)
    assert isinstance(stats["lance_tables_opened"], int)


def test_prefetch_library_caches_is_idempotent(test_package):
    """Calling prefetch twice on the same library must not raise."""
    from fichero_server.api.main import prefetch_library_caches

    stats1 = prefetch_library_caches(test_package)
    stats2 = prefetch_library_caches(test_package)

    assert stats1["package_path"] == stats2["package_path"]


def test_prefetch_empty_lance_tables_on_fresh_db(test_package):
    """A freshly created library has no LanceDB tables yet — lance_tables_opened is 0."""
    from fichero_server.api.main import prefetch_library_caches

    stats = prefetch_library_caches(test_package)

    assert stats["lance_tables_opened"] == 0, (
        "A brand-new test library has no vector tables; "
        f"got lance_tables_opened={stats['lance_tables_opened']}"
    )
