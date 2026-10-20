"""The llm layer's share of the one retry layer (`ai.where.one-retry-policy`, #5944).

Provider SDK retries are OFF (`llm._build_langchain_model`: `max_retries=0`); the one retry layer is
`workflows.circuit_breaker.call_with_breaker`: bounded retries, the provider's Retry-After honoured, a 429 a slow-down
and not a breaker failure, a refused key or no credit opening the breaker at once. A workflow's vision tool already runs
its calls inside that layer; every other model call (chat, structured, tools, the line reader, a check) is wrapped here.
A call already inside the layer is not wrapped again, so a call is retried by exactly one layer.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

#: How long a provider that cannot answer this run (no credit, a refused key) is failed fast for, process-wide.
DEAD_FOR_SECONDS = 30.0
_DEAD: dict[str, float] = {}  # provider -> monotonic time until which it is failed fast; no lock: a dict set is atomic


async def resilient(make_coro: Callable[[], Awaitable[T]], config) -> T:
    """Run one model call (a fresh awaitable per try) under the one retry layer. A model on this Mac is not retried here:
    its own no-progress rule and `page_retry` own that."""
    from fichero_server.llm import _runs_on_this_mac
    from fichero_server.workflows.circuit_breaker import (
        IN_RETRY_LAYER, ProviderCircuitBreaker, ProviderRateLimitedError, call_with_breaker, classify_provider_error)

    if IN_RETRY_LAYER.get() or _runs_on_this_mac(config):
        return await make_coro()
    provider = (config.provider or "unknown").lower()
    if _DEAD.get(provider, 0.0) > time.monotonic():
        raise ProviderRateLimitedError(provider, failures=1, detail="no credit or the key was refused")
    breaker = ProviderCircuitBreaker()  # per call: the retries are what is bounded here; process-wide state is `_DEAD`
    try:
        return await call_with_breaker(make_coro, provider=provider, breaker=breaker, label=config.model)
    except Exception as exc:
        if breaker.is_open(provider) or classify_provider_error(exc) == "fatal":
            _DEAD[provider] = time.monotonic() + DEAD_FOR_SECONDS
        raise
