"""
LLM model info and cost utilities.

Pricing and capability data come from a VENDORED snapshot of LiteLLM's
model registry (resources/model_prices.json) — the 84 MB litellm package
existed in this codebase solely for that one JSON file (Daniel, 2026-08-27:
"can we get rid of litellm completely?"). Refresh the snapshot from
https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
Included by llm.py via re-exports in __all__.
"""

from __future__ import annotations

import json
import logging
from importlib import resources as importlib_resources
from typing import Any

logger = logging.getLogger(__name__)

_PRICE_TABLE: dict[str, dict[str, Any]] | None = None


def _price_table() -> dict[str, dict[str, Any]]:
    """Lazy-load the vendored model registry (2,700+ entries, ~1.4 MB)."""
    global _PRICE_TABLE
    if _PRICE_TABLE is None:
        ref = importlib_resources.files("fichero_server.resources") / "model_prices.json"
        table = json.loads(ref.read_text(encoding="utf-8"))
        # LiteLLM ships a schema-documentation entry alongside the real rows.
        table.pop("sample_spec", None)
        _PRICE_TABLE = table
    return _PRICE_TABLE


def _resolve_entry(model: str) -> dict[str, Any] | None:
    """Exact key first, then the un-prefixed form ("openai/gpt-4o" → "gpt-4o")."""
    table = _price_table()
    entry = table.get(model)
    if entry is None and "/" in model:
        entry = table.get(model.split("/", 1)[1])
    return entry


# =============================================================================
# Model Info & Costs
# =============================================================================


def get_model_info(model: str) -> dict[str, Any] | None:
    """Get information about a model from the vendored registry.

    Args:
        model: Model name (e.g., "gpt-4o", "openai/gpt-4o")

    Returns:
        Dict with model info (max_tokens, costs, etc.)

    Raises:
        RuntimeError: when the model has no registry entry — same loud
        contract the litellm-backed version had.
    """
    entry = _resolve_entry(model)
    if entry is None:
        logger.error("Model info lookup failed for %s (not in vendored registry)", model)
        raise RuntimeError(f"Could not load model info for {model}")
    return entry


def get_model_cost(model: str) -> dict[str, float] | None:
    """Get cost per token for a model.

    Args:
        model: Model name

    Returns:
        Dict with 'input_cost_per_token' and 'output_cost_per_token'
    """
    cost_info = _resolve_entry(model)
    if cost_info:
        input_cost = cost_info.get("input_cost_per_token")
        output_cost = cost_info.get("output_cost_per_token")
        if input_cost is None or output_cost is None:
            logger.warning(
                "Registry pricing incomplete for %s: input=%r output=%r",
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
    costs = get_model_cost(model)
    if costs is None:
        logger.warning("Cost estimate unavailable for %s (no registry pricing)", model)
        return None
    return (
        input_tokens * costs["input_cost_per_token"]
        + output_tokens * costs["output_cost_per_token"]
    )


def list_models_for_provider(provider: str) -> list[dict[str, Any]]:
    """List available models for a provider from LiteLLM's registry.

    Args:
        provider: Provider type (e.g., "openai", "anthropic")

    Returns:
        List of dicts with model info
    """
    models = []

    def per_million(value: Any) -> float | None:
        """Convert per-token pricing to per-million, preserving unknowns."""
        if value is None:
            return None
        return value * 1_000_000

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

    for model_name, info in _price_table().items():
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
                    "input_cost_per_million": per_million(
                        info.get("input_cost_per_token")
                    ),
                    "output_cost_per_million": per_million(
                        info.get("output_cost_per_token")
                    ),
                    "batch_input_cost_per_million": per_million(batch_input),
                    "batch_output_cost_per_million": per_million(batch_output),
                    "cache_read_cost_per_million": per_million(cache_read),
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
