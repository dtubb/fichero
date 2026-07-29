"""
LLM embedding utilities.

Thin wrappers around LangChain embeddings models.
Included by llm.py via re-exports in __all__.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)


@lru_cache(maxsize=32)
def _build_embeddings_client(model: str, api_key: str | None) -> Any:
    """Construct (and cache) one OpenAIEmbeddings client per (model, key).

    ponytail: at 100k images the embed path was rebuilding a fresh
    OpenAIEmbeddings client — and its httpx connection pool — on every call
    (#2545 N1). Cache keyed by (model, api_key) so a key rotation lands on a
    new entry; ``clear_embeddings_client_cache()`` drops stale clients when a
    credential changes. maxsize bounds the rare multi-model/multi-key case.
    """
    from langchain_openai import OpenAIEmbeddings

    return OpenAIEmbeddings(model=model, api_key=api_key)


def clear_embeddings_client_cache() -> None:
    """Drop cached embedding clients (call on credential change)."""
    _build_embeddings_client.cache_clear()


def _embedding_provider(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    return "openai"


def _enforce_embedding_call_allowed(model: str) -> None:
    """Gate explicit remote embedding calls on local-only mode (#2234).

    Previously gated on _paid_remote_fallbacks_enabled() in addition to
    is_local_only(), which made EXPLICIT remote embedding configs behave
    differently from explicit remote chat/vision configs (both of which only
    check local-only mode). This asymmetry was a bug: a user who deliberately
    sets an OpenAI embedding model should not be blocked by the fallback flag.
    The paid-fallback flag is for automatic provider escalation, not user intent.
    """
    from fichero_server.llm import (
        LocalOnlyViolationError,
        _is_local_or_builtin_provider,
        is_local_only,
    )

    provider = _embedding_provider(model)
    if _is_local_or_builtin_provider(provider):
        return
    if is_local_only():
        raise LocalOnlyViolationError(provider, model=model, kind="embedding")


# =============================================================================
# Embeddings
# =============================================================================


def _get_langchain_embeddings(
    model: str = "text-embedding-3-small", api_key: str | None = None
):
    """Get LangChain embeddings model.

    Args:
        model: Embedding model name
        api_key: Optional API key

    Returns:
        LangChain embeddings instance
    """
    # Resolve API key
    if not api_key:
        # Extract provider from model name
        if "/" in model:
            provider = model.split("/")[0]
        else:
            provider = "openai"  # Default for OpenAI models
        from fichero_server.llm import get_api_key  # lazy import avoids circular dependency
        api_key = get_api_key(provider)

    # Currently we primarily use OpenAI embeddings; the cached builder reuses
    # one client per (model, key) instead of rebuilding per call (#2545 N1).
    return _build_embeddings_client(model, api_key)


def embed(
    texts: list[str],
    model: str = "text-embedding-3-small",
    api_key: str | None = None,
) -> list[list[float]]:
    """Create embeddings for texts using LangChain.

    Args:
        texts: List of texts to embed
        model: Embedding model (default: OpenAI text-embedding-3-small)
        api_key: Optional API key (uses keychain/env if not provided)

    Returns:
        List of embedding vectors
    """
    _enforce_embedding_call_allowed(model)
    embeddings = _get_langchain_embeddings(model, api_key)
    return embeddings.embed_documents(texts)


async def aembed(
    texts: list[str],
    model: str = "text-embedding-3-small",
    api_key: str | None = None,
) -> list[list[float]]:
    """Async version of embed using LangChain."""
    _enforce_embedding_call_allowed(model)
    embeddings = _get_langchain_embeddings(model, api_key)
    return await embeddings.aembed_documents(texts)
