"""Owner ruling 2026-10-25 (#6127): when the hosted reader fails on a page it is retried with backoff (the one retry layer,
`ai.where.one-retry-policy`, #5944), then the page is FAILED, with no text for it: Kraken's text is never put in its place.

Driven through `process_vision` and the real `call_with_breaker`; only the provider's call and the sleep are stubbed.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.workflows import circuit_breaker as cb
from fichero_server.workflows.circuit_breaker import DEFAULT_MAX_RETRIES
from tests.unit.workflows.test_a_stopped_page_is_not_a_failed_page_5935 import _read
from tests.unit.workflows.test_parallel_fanout_no_semaphore_deadlock import _fresh_vision_semaphore  # noqa: F401 -- autouse


@pytest.mark.asyncio
async def test_a_hosted_call_that_fails_every_try_is_retried_with_backoff_then_the_page_is_failed(tmp_path, monkeypatch):
    waits: list[float] = []

    async def fake_sleep(delay):
        waits.append(delay)

    monkeypatch.setattr(cb.asyncio, "sleep", fake_sleep)
    vision = AsyncMock(side_effect=RuntimeError("429 Too Many Requests"))
    saved = AsyncMock(return_value=None)
    with patch("fichero_server.workflows.tools.vision_base.save_artifact", new=saved):
        result = await _read(tmp_path, vision)
    assert vision.await_count == 1 + DEFAULT_MAX_RETRIES  # the first try and every retry, no more (5)
    assert len(waits) == DEFAULT_MAX_RETRIES and waits == sorted(waits) and waits[-1] > waits[0]  # backing off
    (page,) = result["results"]
    assert "error" in page and page["error"]  # the page failed, with its reason
    assert saved.await_count == 0 and not any(result.get("texts") or [])  # and has no text: nothing written in Kraken's place
