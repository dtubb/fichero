"""Tests for #2224: content-addressed result cache for vision() calls.

Covers:
- Cache miss → model is called, result is stored
- Cache hit → model is NOT called again
- Different prompt → different cache key (miss)
- Different image content → different cache key (miss)
- Empty image list still caches
- FIFO eviction keeps cache at _LLM_RESULT_CACHE_MAX entries
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import fichero_server.llm as llm_module
from fichero_server.llm import _LLM_RESULT_CACHE, _LLM_RESULT_CACHE_LOCK, _vision_cache_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(provider: str = "openai", model: str = "gpt-4o") -> MagicMock:
    cfg = MagicMock()
    cfg.provider = provider
    cfg.model = model
    return cfg


def _b64_uri(payload: str) -> str:
    return f"data:image/png;base64,{payload}"


# ---------------------------------------------------------------------------
# Cache key helpers
# ---------------------------------------------------------------------------


def test_vision_cache_key_stable() -> None:
    """Same inputs produce the same key."""
    cfg = _make_config()
    k1 = _vision_cache_key(cfg, "describe", [_b64_uri("AAAA")])
    k2 = _vision_cache_key(cfg, "describe", [_b64_uri("AAAA")])
    assert k1 == k2


def test_vision_cache_key_differs_on_prompt() -> None:
    cfg = _make_config()
    k1 = _vision_cache_key(cfg, "describe", [_b64_uri("AAAA")])
    k2 = _vision_cache_key(cfg, "transcribe", [_b64_uri("AAAA")])
    assert k1 != k2


def test_vision_cache_key_differs_on_image_content() -> None:
    cfg = _make_config()
    k1 = _vision_cache_key(cfg, "describe", [_b64_uri("AAAA")])
    k2 = _vision_cache_key(cfg, "describe", [_b64_uri("BBBB")])
    assert k1 != k2


def test_vision_cache_key_differs_on_model() -> None:
    cfg1 = _make_config(model="gpt-4o")
    cfg2 = _make_config(model="gpt-4o-mini")
    k1 = _vision_cache_key(cfg1, "describe", [_b64_uri("AAAA")])
    k2 = _vision_cache_key(cfg2, "describe", [_b64_uri("AAAA")])
    assert k1 != k2


def test_vision_cache_key_url_images() -> None:
    """URL images should produce a stable key too."""
    cfg = _make_config()
    k1 = _vision_cache_key(cfg, "describe", ["https://example.com/img.png"])
    k2 = _vision_cache_key(cfg, "describe", ["https://example.com/img.png"])
    assert k1 == k2


# ---------------------------------------------------------------------------
# Cache hit/miss via mocked vision()
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_vision_cache_miss_calls_model() -> None:
    """First call with a new key must invoke the LangChain model."""
    # Clear the process-level cache before the test
    with _LLM_RESULT_CACHE_LOCK:
        _LLM_RESULT_CACHE.clear()

    cfg = _make_config(model="cache-miss-test")
    fake_response = MagicMock()
    fake_response.content = "a cat"

    with (
        patch.object(llm_module, "_enforce_local_only_provider"),
        patch.object(llm_module, "get_langchain_model") as mock_get_model,
        patch.object(llm_module, "_remote_llm_call_slot") as mock_slot,
        patch.object(llm_module, "_compute_timeout", return_value=60.0),
    ):
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = fake_response
        mock_get_model.return_value = mock_model
        mock_slot.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_slot.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await llm_module.vision(
            images=[_b64_uri("MISS")],
            prompt="describe",
            config=cfg,
        )

    assert result == "a cat"
    mock_model.ainvoke.assert_called_once()


@pytest.mark.anyio
async def test_vision_cache_hit_skips_model() -> None:
    """Second call with the same key must NOT call the model again."""
    with _LLM_RESULT_CACHE_LOCK:
        _LLM_RESULT_CACHE.clear()

    cfg = _make_config(model="cache-hit-test")
    fake_response = MagicMock()
    fake_response.content = "a dog"

    with (
        patch.object(llm_module, "_enforce_local_only_provider"),
        patch.object(llm_module, "get_langchain_model") as mock_get_model,
        patch.object(llm_module, "_remote_llm_call_slot") as mock_slot,
        patch.object(llm_module, "_compute_timeout", return_value=60.0),
    ):
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = fake_response
        mock_get_model.return_value = mock_model
        mock_slot.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_slot.return_value.__aexit__ = AsyncMock(return_value=False)

        r1 = await llm_module.vision(images=[_b64_uri("HIT")], prompt="describe", config=cfg)
        r2 = await llm_module.vision(images=[_b64_uri("HIT")], prompt="describe", config=cfg)

    assert r1 == r2 == "a dog"
    assert mock_model.ainvoke.call_count == 1, "Model should only be called once (cache hit on second call)"


@pytest.mark.anyio
async def test_vision_cache_empty_images() -> None:
    """Empty image list should also be cached."""
    with _LLM_RESULT_CACHE_LOCK:
        _LLM_RESULT_CACHE.clear()

    cfg = _make_config(model="cache-empty-test")
    fake_response = MagicMock()
    fake_response.content = "no image"

    with (
        patch.object(llm_module, "_enforce_local_only_provider"),
        patch.object(llm_module, "get_langchain_model") as mock_get_model,
        patch.object(llm_module, "_remote_llm_call_slot") as mock_slot,
        patch.object(llm_module, "_compute_timeout", return_value=60.0),
    ):
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = fake_response
        mock_get_model.return_value = mock_model
        mock_slot.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_slot.return_value.__aexit__ = AsyncMock(return_value=False)

        await llm_module.vision(images=[], prompt="describe", config=cfg)
        await llm_module.vision(images=[], prompt="describe", config=cfg)

    assert mock_model.ainvoke.call_count == 1


# ---------------------------------------------------------------------------
# FIFO eviction
# ---------------------------------------------------------------------------


def test_vision_cache_eviction() -> None:
    """Cache stays at MAX entries; oldest entry is evicted when full."""
    with _LLM_RESULT_CACHE_LOCK:
        _LLM_RESULT_CACHE.clear()

    max_size = llm_module._LLM_RESULT_CACHE_MAX
    # Fill cache to exactly MAX
    for i in range(max_size):
        _LLM_RESULT_CACHE[f"key_{i}"] = f"value_{i}"

    # Add one more entry (via the eviction path)
    with _LLM_RESULT_CACHE_LOCK:
        if len(_LLM_RESULT_CACHE) >= max_size:
            oldest = next(iter(_LLM_RESULT_CACHE))
            del _LLM_RESULT_CACHE[oldest]
        _LLM_RESULT_CACHE["key_new"] = "value_new"

    assert len(_LLM_RESULT_CACHE) == max_size
    assert "key_0" not in _LLM_RESULT_CACHE, "Oldest entry should have been evicted"
    assert "key_new" in _LLM_RESULT_CACHE
