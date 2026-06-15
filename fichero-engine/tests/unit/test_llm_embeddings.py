from __future__ import annotations

from unittest.mock import patch

import pytest

from fichero.llm import LocalOnlyViolationError
from fichero import llm_embeddings


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
            "fichero.llm_embeddings._get_langchain_embeddings",
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
            "fichero.llm_embeddings._get_langchain_embeddings",
            return_value=FakeEmbeddings(),
        ):
            result = llm_embeddings.embed(["hola"], model="text-embedding-3-small")

    assert result == [[0.1, 0.2]]
