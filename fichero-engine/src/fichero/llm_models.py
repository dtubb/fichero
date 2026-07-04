"""
LLM model info and cost utilities.

Uses LiteLLM's model registry for pricing and capability data.
Included by llm.py via re-exports in __all__.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Lazy import litellm to avoid import overhead
_litellm = None


def _get_litellm():
    """Lazy-load litellm module."""
    global _litellm
    if _litellm is None:
        import litellm

        _litellm = litellm
        litellm.suppress_debug_info = True
    return _litellm


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
    except Exception as exc:
        logger.exception("LiteLLM model info lookup failed for %s", model)
        raise RuntimeError(f"Could not load model info for {model}") from exc


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
        input_cost = cost_info.get("input_cost_per_token")
        output_cost = cost_info.get("output_cost_per_token")
        if input_cost is None or output_cost is None:
            logger.warning(
                "LiteLLM pricing incomplete for %s: input=%r output=%r",
                model,
                input_cost,
                output_cost,
            )
            return None
        return {
            "input_cost_per_token": input_cost,
            "output_cost_per_token": output_cost,
        }
    return None


def estimate_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """Estimate cost for a completion.

    Args:
        model: Model name
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens

    Returns:
        Estimated cost in USD, or None when pricing is unavailable.
    """
    litellm = _get_litellm()
    try:
        input_cost, output_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
        return input_cost + output_cost
    except Exception as exc:
        logger.exception("LiteLLM cost estimate failed for %s", model)
        return None


def list_models_for_provider(provider: str) -> list[dict[str, Any]]:
    """List available models for a provider from LiteLLM's registry.

    Args:
        provider: Provider type (e.g., "openai", "anthropic")

    Returns:
        List of dicts with model info
    """
    litellm = _get_litellm()

    models = []

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
            return any(
                model_name.startswith(p)
                for p in [
                    "gpt-",
                    "chatgpt-",
                    "o1",
                    "o3",
                    "davinci",
                    "curie",
                    "babbage",
                    "ada",
                    "ft:gpt",
                    "text-embedding",
                    "whisper",
                    "tts",
                    "dall-e",
                ]
            )

        # Anthropic direct models
        if provider == "anthropic":
            return model_name.startswith("claude")

        # Google direct models
        if provider == "google":
            return model_name.startswith("gemini")

        # Mistral direct models
        if provider == "mistral":
            return any(
                model_name.startswith(p)
                for p in [
                    "mistral-",
                    "pixtral-",
                    "codestral",
                    "open-mistral",
                    "open-mixtral",
                ]
            )

        # Cohere direct models
        if provider == "cohere":
            return model_name.startswith("command")

        return False

    for model_name, info in litellm.model_cost.items():
        # Filter by provider
        if is_provider_model(model_name, provider):
            # Clean up model name
            display_name = (
                model_name.replace(f"{provider}/", "")
                if model_name.startswith(f"{provider}/")
                else model_name
            )

            # Get batch pricing if available
            batch_input = info.get("input_cost_per_token_batches")
            batch_output = info.get("output_cost_per_token_batches")
            cache_read = info.get("cache_read_input_token_cost")

            models.append(
                {
                    "model_id": display_name,
                    "full_name": model_name,
                    "description": None,  # Will be filled by curated list if available
                    # Pricing
                    "input_cost_per_million": info.get("input_cost_per_token", 0)
                    * 1_000_000,
                    "output_cost_per_million": info.get("output_cost_per_token", 0)
                    * 1_000_000,
                    "batch_input_cost_per_million": batch_input * 1_000_000
                    if batch_input
                    else None,
                    "batch_output_cost_per_million": batch_output * 1_000_000
                    if batch_output
                    else None,
                    "cache_read_cost_per_million": cache_read * 1_000_000
                    if cache_read
                    else None,
                    # Context windows
                    "max_input_tokens": safe_int(info.get("max_input_tokens")),
                    "max_output_tokens": safe_int(info.get("max_output_tokens"))
                    or safe_int(info.get("max_tokens")),
                    # Mode
                    "mode": info.get("mode", "chat"),
                    # Capabilities
                    "supports_vision": info.get("supports_vision", False),
                    "supports_function_calling": info.get(
                        "supports_function_calling", False
                    ),
                    "supports_audio_input": info.get("supports_audio_input", False),
                    "supports_audio_output": info.get("supports_audio_output", False),
                    "supports_pdf_input": info.get("supports_pdf_input", False),
                    "supports_prompt_caching": info.get(
                        "supports_prompt_caching", False
                    ),
                    "supports_reasoning": info.get("supports_reasoning", False),
                    "supports_web_search": info.get("supports_web_search", False),
                    "supports_streaming": True,  # Most models support streaming
                    "supports_batch_api": batch_input is not None,
                    # Provider info
                    "provider": info.get("litellm_provider", provider),
                }
            )

    # Sort by name
    models.sort(key=lambda m: m["model_id"])
    return models
