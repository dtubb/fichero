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
import os
from importlib import resources as importlib_resources
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PRICE_TABLE: dict[str, dict[str, Any]] | None = None


_REGISTRY_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
_REGISTRY_MAX_AGE_SECONDS = 7 * 24 * 3600


def _cached_registry_path() -> Path:
    base = os.environ.get("FICHERO_BASE_PATH", "").strip()
    root = Path(base) if base else Path.home() / "Library" / "Application Support" / "Fichero"
    return root / "model_prices.json"


def _refresh_registry_cache(cache: Path) -> bool:
    """Fetch the upstream registry into the cache. True on success.

    Best-effort by design: pricing must never take the engine down or hang a
    call — short timeout, atomic write, and every failure just means the
    previous cache or the vendored snapshot serves instead.
    """
    try:
        import httpx

        response = httpx.get(_REGISTRY_URL, timeout=5.0, follow_redirects=True)
        response.raise_for_status()
        table = response.json()
        if not isinstance(table, dict) or len(table) < 500:
            raise ValueError(f"implausible registry: {type(table).__name__}, {len(table) if isinstance(table, dict) else 0} rows")
        cache.parent.mkdir(parents=True, exist_ok=True)
        tmp = cache.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(table), encoding="utf-8")
        tmp.replace(cache)
        logger.info("Model registry refreshed from upstream (%d models)", len(table))
        return True
    except Exception as exc:
        logger.warning("Model registry refresh failed (%s) — serving cached/vendored data", exc)
        return False


_REFRESH_STARTED = False


def _schedule_registry_refresh(cache: Path) -> None:
    """Refresh the registry cache WITHOUT stalling a request (2026-09-01).

    The refresh is a 5-second-timeout HTTPS GET, and ``_price_table`` is
    reached from ``async def`` route handlers (workflow cost estimation, the
    provider-model catalogs) and from the runner's per-node cost tally.
    Calling ``httpx.get`` there blocked the event loop — the whole engine —
    for up to five seconds, on every fresh install and again each week. That
    is a real slice of "runs feel slow for a single file", and it is entirely
    fixed cost: the answer served afterwards is identical.

    So: serve what is on disk NOW — the stale cache, or the vendored snapshot
    beneath it — and refresh on a daemon thread for the next caller. Nothing
    here buys correctness, only freshness, so nothing here is worth waiting
    for.
    """
    global _REFRESH_STARTED
    if _REFRESH_STARTED:
        return
    _REFRESH_STARTED = True
    import threading

    def _refresh() -> None:
        global _PRICE_TABLE
        if not _refresh_registry_cache(cache):
            return
        # Drop the memo so the next lookup picks the fresh table up. A torn
        # read is impossible: the global is only ever rebound to a complete
        # dict, never mutated in place.
        _PRICE_TABLE = None

    threading.Thread(
        target=_refresh, name="model-registry-refresh", daemon=True
    ).start()


def _price_table() -> dict[str, dict[str, Any]]:
    """The model registry, LIVE-preferring (Daniel, 2026-08-27: "we want to
    make sure we're checking live, not a cached thing from months ago").

    Layers, first hit wins:
      1. A downloaded cache under Application Support, refreshed from the
         upstream registry when older than a week (or absent).
      2. The vendored snapshot shipped in the package — the offline floor.
    """
    global _PRICE_TABLE
    if _PRICE_TABLE is None:
        import time

        table: dict[str, dict[str, Any]] | None = None
        cache = _cached_registry_path()
        try:
            age = time.time() - cache.stat().st_mtime if cache.exists() else None
        except OSError:
            age = None
        if age is None or age > _REGISTRY_MAX_AGE_SECONDS:
            _schedule_registry_refresh(cache)
        try:
            if cache.exists():
                table = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.warning("Cached model registry unreadable (%s) — vendored fallback", exc)
        if table is None:
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


# =============================================================================
# Selectability — which registry rows may be OFFERED as a run's model
# =============================================================================

# Endpoints on which a model can serve an interactive (synchronous) call.
# A registry row that lists endpoints but NONE of these is batch-only: the
# provider will answer a normal chat call with a 404 telling you to post the
# request to its batches endpoint instead. Offering such a model as a default
# is what burned a run (Daniel, 2026-09-01): "Requested model is unavailable
# on this provider… This model is only available through the Batch API."
_INTERACTIVE_ENDPOINT_MARKERS = (
    "chat/completions",
    "completions",
    "responses",
    "messages",
    "generatecontent",
    "predict",
    "ocr",
    "realtime",
    "embeddings",
    "audio",
    "images",
)

# Ids that ANNOUNCE themselves as batch-only. Providers that ship a separate
# batch SKU name it in the id; the registry does not always carry a row for
# those, so the name is the only signal available offline.
_BATCH_ONLY_ID_MARKERS = ("-batch", "batch-", ":batch", "/batch", "_batch")


def is_batch_only_model(model: str) -> bool:
    """True when ``model`` can only be called through a provider's Batch API.

    Two signals, cheapest first:

    1. The model id names itself a batch SKU.
    2. The registry row lists ``supported_endpoints`` and every one of them is
       a batch endpoint.

    A model with NO registry row is never called batch-only — absence of
    evidence is not evidence, and guessing here would hide working models
    (the failure mode of the vision gating this sits beside).
    """
    raw = (model or "").strip().lower()
    if not raw:
        return False
    stem = raw.rsplit("/", 1)[-1]
    if any(marker in stem for marker in _BATCH_ONLY_ID_MARKERS):
        return True
    entry = _resolve_entry(raw)
    if not entry:
        return False
    endpoints = entry.get("supported_endpoints")
    if not isinstance(endpoints, (list, tuple)) or not endpoints:
        return False
    for endpoint in endpoints:
        text = str(endpoint).lower()
        if any(marker in text for marker in _INTERACTIVE_ENDPOINT_MARKERS):
            return False
    return True


# Model-family fragments that are vision-capable across every id in the
# family. Used ONLY as a floor when neither a live catalog nor the vendored
# registry says anything: a live provider catalog (Anthropic's /v1/models,
# Google's ListModels) ships ids WITHOUT capability flags, so a brand-new
# Opus or Gemini fell through as supports_vision=False and vanished from
# every vision picker (Daniel, 2026-09-01: "cannot select a model like Opus
# or Google"). A model the registry explicitly marks non-vision keeps that.
# Family PREFIXES, not exact versions: the whole point is to cover a model
# that shipped after the snapshot, so "claude-3, claude-4" would have needed
# editing on the day Opus 4.8 arrived and would have failed exactly the way
# the registry already fails. The known text-only siblings below carve out
# the exceptions.
_VISION_FAMILY_MARKERS = (
    "claude-", "gemini-", "gemini-pro-vision",
    "gpt-4o", "gpt-4.1", "gpt-4-turbo", "gpt-5", "gpt-6", "o1", "o3", "o4",
    "pixtral", "llava", "qwen-vl", "qwen2-vl", "qwen2.5-vl", "qwen3-vl",
    "-vl-", "-vl:", "vision", "grok-2-vision", "grok-3", "grok-4",
    "internvl", "minicpm-v", "moondream", "phi-4-multimodal",
)

# Families that share a vision-family prefix but are text-only, so the floor
# above does not promote them (embedding/TTS/audio siblings mostly).
_NON_VISION_MARKERS = (
    "embed", "tts", "whisper", "moderation", "rerank", "guard",
    "claude-1", "claude-2", "claude-instant", "gemini-1.0",
    "-audio", "text-only", "gemma",
)


def infer_vision_support(model: str) -> bool:
    """Best-effort "can this model read an image?" from its id alone.

    The floor for catalogs that publish ids without capabilities. Never
    consulted when a source states the capability — see the call sites, which
    all use it as a fallback rather than an override.
    """
    raw = (model or "").strip().lower()
    if not raw:
        return False
    if any(marker in raw for marker in _NON_VISION_MARKERS):
        return False
    return any(marker in raw for marker in _VISION_FAMILY_MARKERS)
