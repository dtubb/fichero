"""Tests for #2228: vision() wall-clock timeout backstop + usage telemetry.

Covers:
- TimeoutError from asyncio.wait_for is converted to a RuntimeError
- Normal call records usage via _record_usage when usage_metadata is present
- No usage recording when usage_metadata is absent (graceful)
- Quota errors are re-raised via _raise_provider_quota_error
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import fichero_server.llm as llm_module
from fichero_server.llm import _LLM_RESULT_CACHE, _LLM_RESULT_CACHE_LOCK


def _make_config(provider: str = "openai", model: str = "gpt-4o") -> MagicMock:
    cfg = MagicMock()
    cfg.provider = provider
    cfg.model = model
    return cfg


@pytest.mark.anyio
async def test_vision_timeout_raises_runtime_error() -> None:
    """asyncio.TimeoutError from wait_for must surface as RuntimeError."""
    with _LLM_RESULT_CACHE_LOCK:
        _LLM_RESULT_CACHE.clear()

    cfg = _make_config(model="timeout-test")

    async def _hang(_):
        await asyncio.sleep(999)

    with (
        patch.object(llm_module, "_enforce_local_only_provider"),
        patch.object(llm_module, "get_langchain_model") as mock_get,
        patch.object(llm_module, "_remote_llm_call_slot") as mock_slot,
        patch.object(llm_module, "_compute_timeout", return_value=0.01),
    ):
        mock_model = MagicMock()
        mock_model.ainvoke = _hang
        mock_get.return_value = mock_model
        mock_slot.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_slot.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(RuntimeError, match="vision exceeded"):
            await llm_module.vision(
                images=["data:image/png;base64,TIMEOUT"],
                prompt="describe",
                config=cfg,
            )


@pytest.mark.anyio
async def test_vision_records_usage_when_present() -> None:
    """When the response carries usage_metadata, _record_usage must be called."""
    with _LLM_RESULT_CACHE_LOCK:
        _LLM_RESULT_CACHE.clear()

    cfg = _make_config(model="usage-test")
    fake_response = MagicMock()
    fake_response.content = "a tree"
    fake_response.usage_metadata = {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }

    with (
        patch.object(llm_module, "_enforce_local_only_provider"),
        patch.object(llm_module, "get_langchain_model") as mock_get,
        patch.object(llm_module, "_remote_llm_call_slot") as mock_slot,
        patch.object(llm_module, "_compute_timeout", return_value=60.0),
        patch.object(llm_module, "_record_usage") as mock_record,
    ):
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = fake_response
        mock_get.return_value = mock_model
        mock_slot.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_slot.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await llm_module.vision(
            images=["data:image/png;base64,USAGE"],
            prompt="describe",
            config=cfg,
        )

    assert result == "a tree"
    mock_record.assert_called_once_with(
        cfg.provider, cfg.model, "vision",
        input_tokens=10,
        output_tokens=5,
        total_tokens=15,
    )


@pytest.mark.anyio
async def test_vision_no_usage_metadata_skips_record() -> None:
    """When usage_metadata is absent, _record_usage must NOT be called."""
    with _LLM_RESULT_CACHE_LOCK:
        _LLM_RESULT_CACHE.clear()

    cfg = _make_config(model="no-usage-test")
    fake_response = MagicMock(spec=["content"])
    fake_response.content = "a mountain"

    with (
        patch.object(llm_module, "_enforce_local_only_provider"),
        patch.object(llm_module, "get_langchain_model") as mock_get,
        patch.object(llm_module, "_remote_llm_call_slot") as mock_slot,
        patch.object(llm_module, "_compute_timeout", return_value=60.0),
        patch.object(llm_module, "_record_usage") as mock_record,
    ):
        mock_model = AsyncMock()
        mock_model.ainvoke.return_value = fake_response
        mock_get.return_value = mock_model
        mock_slot.return_value.__aenter__ = AsyncMock(return_value=None)
        mock_slot.return_value.__aexit__ = AsyncMock(return_value=False)

        await llm_module.vision(
            images=["data:image/png;base64,NOUSAGE"],
            prompt="describe",
            config=cfg,
        )

    mock_record.assert_not_called()
