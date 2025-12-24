"""
Fichero Unified LLM Interface

Shared interface for all LLM operations using LiteLLM.
Used by chat API, workflows, and future MCP tools.

Capabilities:
- Chat: Conversational AI with streaming support
- Vision: Image understanding (GPT-4o, Claude 3, Gemini, etc.)
- Embeddings: Vector embeddings for semantic search
- Tools: Function/tool calling
- Structured Output: JSON mode, schema validation

Usage:
    from fichero.llm import chat, vision, embed, LLMConfig

    # Simple chat
    config = LLMConfig(provider="openai", model="gpt-4o-mini")
    response = await chat("Hello!", config)

    # Vision
    response = await vision(
        images=["https://example.com/image.jpg"],
        prompt="Describe this image",
        config=config
    )

    # Embeddings
    vectors = embed(["text to embed"])

    # Streaming
    async for chunk in chat("Hello!", config, stream=True):
        print(chunk, end="")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import AsyncIterator, Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Lazy import litellm to avoid import overhead
_litellm = None


def _get_litellm():
    """Lazy-load litellm module."""
    global _litellm
    if _litellm is None:
        import litellm
        _litellm = litellm
        # Reduce litellm logging noise
        litellm.suppress_debug_info = True
    return _litellm


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class LLMConfig:
    """Configuration for LLM calls."""
    provider: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 2048
    api_key: str | None = None
    api_base: str | None = None
    timeout: int = 60
    extra: dict[str, Any] = field(default_factory=dict)

    def get_model_name(self) -> str:
        """Get LiteLLM-format model name (provider/model)."""
        # Some providers need special handling
        if self.provider in ("ollama", "lmstudio"):
            return f"ollama/{self.model}"
        if self.provider == "huggingface":
            return f"huggingface/{self.model}"
        return f"{self.provider}/{self.model}"


# =============================================================================
# API Key Resolution
# =============================================================================

def get_api_key(provider: str) -> str | None:
    """Get API key for a provider.

    Checks in order:
    1. macOS Keychain (if available)
    2. Environment variable

    Args:
        provider: Provider type name (e.g., "openai")

    Returns:
        API key or None if not found
    """
    from fichero.providers import get_provider_info

    # Try keychain first
    try:
        from fichero.keychain import get_api_key as _keychain_get
        key = _keychain_get(provider)
        if key:
            return key
    except ImportError:
        pass

    # Fall back to environment variable
    info = get_provider_info(provider)
    if info and info.api_key_env:
        return os.environ.get(info.api_key_env)

    return None


def _resolve_api_key(config: LLMConfig) -> str | None:
    """Resolve API key from config or lookup."""
    if config.api_key:
        return config.api_key
    return get_api_key(config.provider)


# =============================================================================
# Chat
# =============================================================================

async def chat(
    prompt: str | list[dict[str, Any]],
    config: LLMConfig,
    stream: bool = False,
    system: str | None = None,
) -> str | AsyncIterator[str]:
    """Send a chat message.

    Args:
        prompt: User message (string) or full messages list
        config: LLM configuration
        stream: If True, return async generator of chunks
        system: Optional system message

    Returns:
        Response string, or async generator if streaming
    """
    litellm = _get_litellm()

    # Build messages
    if isinstance(prompt, str):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
    else:
        messages = prompt

    # Build kwargs
    kwargs = {
        "model": config.get_model_name(),
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
        **config.extra,
    }

    # Add API key if available
    api_key = _resolve_api_key(config)
    if api_key:
        kwargs["api_key"] = api_key

    # Add custom base URL if set
    if config.api_base:
        kwargs["api_base"] = config.api_base

    if stream:
        return _stream_chat(litellm, kwargs)
    else:
        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content


async def _stream_chat(litellm, kwargs: dict) -> AsyncIterator[str]:
    """Stream chat response."""
    kwargs["stream"] = True
    response = await litellm.acompletion(**kwargs)
    async for chunk in response:
        content = chunk.choices[0].delta.content
        if content:
            yield content


# =============================================================================
# Vision
# =============================================================================

async def vision(
    images: list[str],
    prompt: str,
    config: LLMConfig,
) -> str:
    """Analyze images with a vision model.

    Args:
        images: List of image URLs or base64 data URIs
        prompt: Analysis prompt
        config: LLM configuration (must use vision-capable model)

    Returns:
        Analysis text
    """
    litellm = _get_litellm()

    # Build multimodal message content
    content = [{"type": "text", "text": prompt}]
    for img in images:
        content.append({
            "type": "image_url",
            "image_url": {"url": img}
        })

    messages = [{"role": "user", "content": content}]

    kwargs = {
        "model": config.get_model_name(),
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
        **config.extra,
    }

    api_key = _resolve_api_key(config)
    if api_key:
        kwargs["api_key"] = api_key

    if config.api_base:
        kwargs["api_base"] = config.api_base

    response = await litellm.acompletion(**kwargs)
    return response.choices[0].message.content


# =============================================================================
# Embeddings
# =============================================================================

def embed(
    texts: list[str],
    model: str = "text-embedding-3-small",
    api_key: str | None = None,
) -> list[list[float]]:
    """Create embeddings for texts.

    Args:
        texts: List of texts to embed
        model: Embedding model (default: OpenAI text-embedding-3-small)
        api_key: Optional API key (uses keychain/env if not provided)

    Returns:
        List of embedding vectors
    """
    litellm = _get_litellm()

    kwargs = {"model": model, "input": texts}

    # Resolve API key
    if not api_key:
        # Extract provider from model name
        if "/" in model:
            provider = model.split("/")[0]
        else:
            provider = "openai"  # Default for OpenAI models
        api_key = get_api_key(provider)

    if api_key:
        kwargs["api_key"] = api_key

    response = litellm.embedding(**kwargs)
    return [item["embedding"] for item in response.data]


async def aembed(
    texts: list[str],
    model: str = "text-embedding-3-small",
    api_key: str | None = None,
) -> list[list[float]]:
    """Async version of embed."""
    litellm = _get_litellm()

    kwargs = {"model": model, "input": texts}

    if not api_key:
        if "/" in model:
            provider = model.split("/")[0]
        else:
            provider = "openai"
        api_key = get_api_key(provider)

    if api_key:
        kwargs["api_key"] = api_key

    response = await litellm.aembedding(**kwargs)
    return [item["embedding"] for item in response.data]


# =============================================================================
# Tools / Function Calling
# =============================================================================

async def chat_with_tools(
    prompt: str | list[dict[str, Any]],
    tools: list[dict[str, Any]],
    config: LLMConfig,
) -> dict[str, Any]:
    """Chat with tool/function calling support.

    Args:
        prompt: User message or messages list
        tools: OpenAI-format tool definitions
        config: LLM configuration

    Returns:
        Dict with 'content' and 'tool_calls' keys
    """
    litellm = _get_litellm()

    if isinstance(prompt, str):
        messages = [{"role": "user", "content": prompt}]
    else:
        messages = prompt

    kwargs = {
        "model": config.get_model_name(),
        "messages": messages,
        "tools": tools,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
        **config.extra,
    }

    api_key = _resolve_api_key(config)
    if api_key:
        kwargs["api_key"] = api_key

    if config.api_base:
        kwargs["api_base"] = config.api_base

    response = await litellm.acompletion(**kwargs)
    message = response.choices[0].message

    return {
        "content": message.content,
        "tool_calls": message.tool_calls or [],
    }


# =============================================================================
# Structured Output
# =============================================================================

async def structured_output(
    prompt: str,
    schema: type[BaseModel],
    config: LLMConfig,
) -> BaseModel:
    """Get structured output matching a Pydantic schema.

    Args:
        prompt: User prompt
        schema: Pydantic model class defining expected structure
        config: LLM configuration

    Returns:
        Instance of the schema class
    """
    litellm = _get_litellm()

    # Build system prompt with schema
    schema_json = schema.model_json_schema()
    system = f"""Respond with valid JSON matching this schema:
{schema_json}

Only output the JSON, no other text."""

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    kwargs = {
        "model": config.get_model_name(),
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
        "response_format": {"type": "json_object"},
        **config.extra,
    }

    api_key = _resolve_api_key(config)
    if api_key:
        kwargs["api_key"] = api_key

    if config.api_base:
        kwargs["api_base"] = config.api_base

    response = await litellm.acompletion(**kwargs)
    content = response.choices[0].message.content

    import json
    data = json.loads(content)
    return schema(**data)


# =============================================================================
# Model Info & Costs
# =============================================================================

def get_model_info(model: str) -> dict[str, Any] | None:
    """Get information about a model from LiteLLM's registry.

    Args:
        model: Model name (e.g., "gpt-4o", "openai/gpt-4o")

    Returns:
        Dict with model info (max_tokens, costs, etc.) or None
    """
    litellm = _get_litellm()
    try:
        return litellm.get_model_info(model)
    except Exception:
        return None


def get_model_cost(model: str) -> dict[str, float] | None:
    """Get cost per token for a model.

    Args:
        model: Model name

    Returns:
        Dict with 'input_cost_per_token' and 'output_cost_per_token'
    """
    litellm = _get_litellm()

    # Check LiteLLM's cost map
    cost_info = litellm.model_cost.get(model)
    if cost_info:
        return {
            "input_cost_per_token": cost_info.get("input_cost_per_token", 0),
            "output_cost_per_token": cost_info.get("output_cost_per_token", 0),
        }
    return None


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate cost for a completion.

    Args:
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Estimated cost in USD
    """
    litellm = _get_litellm()
    try:
        input_cost, output_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        return input_cost + output_cost
    except Exception:
        return 0.0


def list_models_for_provider(provider: str) -> list[dict[str, Any]]:
    """List available models for a provider from LiteLLM's registry.

    Args:
        provider: Provider type (e.g., "openai", "anthropic")

    Returns:
        List of dicts with model info
    """
    litellm = _get_litellm()

    models = []
    prefix = f"{provider}/"

    def safe_int(val) -> int | None:
        """Safely convert value to int, return None if not possible."""
        if val is None:
            return None
        if isinstance(val, int):
            return val
        if isinstance(val, str):
            try:
                return int(val)
            except ValueError:
                return None
        return None

    def is_provider_model(model_name: str, provider: str) -> bool:
        """Check if model belongs to provider (using LiteLLM naming conventions)."""
        # Check explicit provider prefix
        if model_name.startswith(f"{provider}/"):
            return True

        # Provider-specific patterns (for direct API models without prefix)
        if "/" in model_name:
            return False  # Has different provider prefix

        # OpenAI direct models
        if provider == "openai":
            return any(model_name.startswith(p) for p in [
                "gpt-", "chatgpt-", "o1", "o3", "davinci", "curie", "babbage",
                "ada", "ft:gpt", "text-embedding", "whisper", "tts", "dall-e"
            ])

        # Anthropic direct models
        if provider == "anthropic":
            return model_name.startswith("claude")

        # Google direct models
        if provider == "google":
            return model_name.startswith("gemini")

        # Mistral direct models
        if provider == "mistral":
            return any(model_name.startswith(p) for p in [
                "mistral-", "pixtral-", "codestral", "open-mistral", "open-mixtral"
            ])

        # Cohere direct models
        if provider == "cohere":
            return model_name.startswith("command")

        return False

    for model_name, info in litellm.model_cost.items():
        # Filter by provider
        if is_provider_model(model_name, provider):
            # Clean up model name
            display_name = model_name.replace(f"{provider}/", "") if model_name.startswith(f"{provider}/") else model_name

            # Get batch pricing if available
            batch_input = info.get("input_cost_per_token_batches")
            batch_output = info.get("output_cost_per_token_batches")
            cache_read = info.get("cache_read_input_token_cost")

            models.append({
                "model_id": display_name,
                "full_name": model_name,
                "description": None,  # Will be filled by curated list if available

                # Pricing
                "input_cost_per_million": info.get("input_cost_per_token", 0) * 1_000_000,
                "output_cost_per_million": info.get("output_cost_per_token", 0) * 1_000_000,
                "batch_input_cost_per_million": batch_input * 1_000_000 if batch_input else None,
                "batch_output_cost_per_million": batch_output * 1_000_000 if batch_output else None,
                "cache_read_cost_per_million": cache_read * 1_000_000 if cache_read else None,

                # Context windows
                "max_input_tokens": safe_int(info.get("max_input_tokens")),
                "max_output_tokens": safe_int(info.get("max_output_tokens")) or safe_int(info.get("max_tokens")),

                # Mode
                "mode": info.get("mode", "chat"),

                # Capabilities
                "supports_vision": info.get("supports_vision", False),
                "supports_function_calling": info.get("supports_function_calling", False),
                "supports_audio_input": info.get("supports_audio_input", False),
                "supports_audio_output": info.get("supports_audio_output", False),
                "supports_pdf_input": info.get("supports_pdf_input", False),
                "supports_prompt_caching": info.get("supports_prompt_caching", False),
                "supports_reasoning": info.get("supports_reasoning", False),
                "supports_web_search": info.get("supports_web_search", False),
                "supports_streaming": True,  # Most models support streaming
                "supports_batch_api": batch_input is not None,

                # Provider info
                "provider": info.get("litellm_provider", provider),
            })

    # Sort by name
    models.sort(key=lambda m: m["model_id"])
    return models


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Config
    "LLMConfig",
    # Chat
    "chat",
    # Vision
    "vision",
    # Embeddings
    "embed",
    "aembed",
    # Tools
    "chat_with_tools",
    # Structured
    "structured_output",
    # Model info
    "get_model_info",
    "get_model_cost",
    "estimate_cost",
    "list_models_for_provider",
    # Key resolution
    "get_api_key",
]
