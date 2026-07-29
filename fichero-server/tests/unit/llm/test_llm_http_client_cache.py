"""Regression tests for shared LLM transport client reuse.

The LangChain model object is still built per call so temperature / max token
settings stay request-specific. The expensive transport client should be reused
per provider/base_url/model/api_key identity on the same event loop.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from fichero_server import llm


@pytest.fixture(autouse=True)
def _clear_http_client_cache():
    llm._HTTPX_ASYNC_CLIENT_CACHE.clear()
    llm._HTTPX_ASYNC_CLIENT_CACHE_NO_LOOP.clear()
    yield
    llm._HTTPX_ASYNC_CLIENT_CACHE.clear()
    llm._HTTPX_ASYNC_CLIENT_CACHE_NO_LOOP.clear()


class _FakeAsyncClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.mark.asyncio
async def test_shared_http_client_is_reused_for_same_identity():
    instances: list[_FakeAsyncClient] = []

    class _TrackingAsyncClient(_FakeAsyncClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            instances.append(self)

    cfg = llm.LLMConfig(
        provider="openrouter",
        model="gpt-4o-mini",
        api_key="key-1",
        api_base="https://openrouter.ai/api/v1",
        temperature=0.2,
        max_tokens=128,
    )

    with patch("httpx.AsyncClient", _TrackingAsyncClient):
        first = llm.get_langchain_model(cfg)
        second = llm.get_langchain_model(cfg)

    assert len(instances) == 1
    assert first.http_async_client is second.http_async_client is instances[0]
    assert first.http_async_client.kwargs["event_hooks"]["request"]


@pytest.mark.asyncio
async def test_shared_http_client_distinguishes_different_identities():
    instances: list[_FakeAsyncClient] = []

    class _TrackingAsyncClient(_FakeAsyncClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            instances.append(self)

    cfg_a = llm.LLMConfig(
        provider="openrouter",
        model="gpt-4o-mini",
        api_key="key-1",
        api_base="https://openrouter.ai/api/v1",
    )
    cfg_b = llm.LLMConfig(
        provider="openrouter",
        model="gpt-4o-mini",
        api_key="key-2",
        api_base="https://openrouter.ai/api/v1",
    )

    with patch("httpx.AsyncClient", _TrackingAsyncClient):
        first = llm.get_langchain_model(cfg_a)
        second = llm.get_langchain_model(cfg_b)
        third = llm.get_langchain_model(cfg_a)

    assert len(instances) == 2
    assert first.http_async_client is third.http_async_client
    assert first.http_async_client is not second.http_async_client
    assert {client.kwargs["event_hooks"]["request"][0].__name__ for client in instances} == {
        "_openrouter_strip_parallel_tool_use"
    }
