"""
LLM embedding utilities.

Thin wrappers around LangChain embeddings models.
Included by llm.py via re-exports in __all__.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _embedding_provider(model: str) -> str:
    if "/" in model:
        return model.split("/", 1)[0]
    return "openai"


def _enforce_embedding_call_allowed(model: str) -> None:
    from fichero.llm import (
        LocalOnlyViolationError,
        _is_local_or_builtin_provider,
        _paid_remote_fallbacks_enabled,
        is_local_only,
    )

    provider = _embedding_provider(model)
    if _is_local_or_builtin_provider(provider):
        return
    if is_local_only():
        raise LocalOnlyViolationError(provider, model=model, kind="embedding")
    if not _paid_remote_fallbacks_enabled():
        raise RuntimeError(
            "Paid remote AI fallbacks are disabled; refusing embedding call to "
            f"remote provider {provider}/{model}."
        )


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
    from langchain_openai import OpenAIEmbeddings

    # Resolve API key
    if not api_key:
        # Extract provider from model name
        if "/" in model:
            provider = model.split("/")[0]
        else:
            provider = "openai"  # Default for OpenAI models
        from fichero.llm import get_api_key  # lazy import avoids circular dependency
        api_key = get_api_key(provider)

    # Currently we primarily use OpenAI embeddings
    # Could be extended for other providers
    return OpenAIEmbeddings(
        model=model,
        api_key=api_key,
    )


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
