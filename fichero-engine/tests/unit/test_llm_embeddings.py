from __future__ import annotations

from unittest.mock import patch

import pytest

from fichero.llm import LocalOnlyViolationError
from fichero.llm import embeddings as llm_embeddings


def test_remote_embeddings_allowed_when_paid_fallbacks_disabled(monkeypatch) -> None:
    """#2234: paid-fallback flag must NOT gate explicit remote embeddings.

    Before the fix, disabling FICHERO_PAID_FALLBACKS blocked even deliberate
    remote embedding configs. After the fix, only local-only mode blocks them.
    """
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)

    class FakeEmbeddings:
        def embed_documents(self, texts):
            return [[0.1, 0.2] for _ in texts]

    with patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=False):
        with patch(
            "fichero.llm.embeddings._get_langchain_embeddings",
            return_value=FakeEmbeddings(),
        ):
            # Must NOT raise — user explicitly chose a remote model
            result = llm_embeddings.embed(["hola"], model="text-embedding-3-small")

    assert result == [[0.1, 0.2]]


def test_remote_embeddings_refuse_when_local_only_enabled(monkeypatch) -> None:
    monkeypatch.setenv("FICHERO_LOCAL_ONLY", "1")

    with pytest.raises(LocalOnlyViolationError, match="embedding call to remote provider"):
        llm_embeddings.embed(["hola"], model="text-embedding-3-small")


def test_remote_embeddings_run_when_paid_fallbacks_enabled(monkeypatch) -> None:
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)

    class FakeEmbeddings:
        def embed_documents(self, texts):
            return [[0.1, 0.2] for _ in texts]

    with patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=True):
        with patch(
            "fichero.llm.embeddings._get_langchain_embeddings",
            return_value=FakeEmbeddings(),
        ):
            result = llm_embeddings.embed(["hola"], model="text-embedding-3-small")

    assert result == [[0.1, 0.2]]


class TestEmbeddingsClientCache:
    """#2545 N1: the embed path reuses one client per (model, key) instead of
    rebuilding per call, and credential changes drop stale clients."""

    def setup_method(self):
        llm_embeddings.clear_embeddings_client_cache()

    def teardown_method(self):
        llm_embeddings.clear_embeddings_client_cache()

    def test_same_model_and_key_returns_cached_instance(self):
        c1 = llm_embeddings._get_langchain_embeddings("text-embedding-3-small", "k1")
        c2 = llm_embeddings._get_langchain_embeddings("text-embedding-3-small", "k1")
        assert c1 is c2  # cached, not rebuilt

    def test_different_key_returns_new_instance(self):
        c1 = llm_embeddings._get_langchain_embeddings("text-embedding-3-small", "k1")
        c2 = llm_embeddings._get_langchain_embeddings("text-embedding-3-small", "k2")
        assert c1 is not c2

    def test_clear_cache_forces_rebuild(self):
        c1 = llm_embeddings._get_langchain_embeddings("text-embedding-3-small", "k1")
        llm_embeddings.clear_embeddings_client_cache()
        c2 = llm_embeddings._get_langchain_embeddings("text-embedding-3-small", "k1")
        assert c1 is not c2

    def test_clear_api_key_cache_invalidates_embedding_clients(self):
        """A credential rotation (clear_api_key_cache) must also drop clients."""
        from fichero.llm import clear_api_key_cache

        c1 = llm_embeddings._get_langchain_embeddings("text-embedding-3-small", "k1")
        clear_api_key_cache()
        c2 = llm_embeddings._get_langchain_embeddings("text-embedding-3-small", "k1")
        assert c1 is not c2
