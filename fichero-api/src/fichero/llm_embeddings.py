"""
LLM embedding utilities.

Thin wrappers around LangChain embeddings models.
Included by llm.py via re-exports in __all__.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


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
    embeddings = _get_langchain_embeddings(model, api_key)
    return embeddings.embed_documents(texts)


async def aembed(
    texts: list[str],
    model: str = "text-embedding-3-small",
    api_key: str | None = None,
) -> list[list[float]]:
    """Async version of embed using LangChain."""
    embeddings = _get_langchain_embeddings(model, api_key)
    return await embeddings.aembed_documents(texts)
