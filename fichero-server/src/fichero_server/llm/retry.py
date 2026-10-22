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
_DEAD: dict[str, tuple[float, str]] = {}  # provider -> (monotonic time until which it is failed fast, why); no lock: a dict set is atomic
_SPENT: dict[str, int] = {}  # provider -> calls in a row whose retries were spent; K of them fail the provider fast


async def resilient(make_coro: Callable[[], Awaitable[T]], config) -> T:
    """Run one model call (a fresh awaitable per try) under the one retry layer. A model on this Mac is not retried here:
    its own no-progress rule and `page_retry` own that."""
    from fichero_server.llm import _runs_on_this_mac
    from fichero_server.workflows.circuit_breaker import (
        DEFAULT_BREAKER_THRESHOLD, IN_RETRY_LAYER, ProviderCircuitBreaker, call_with_breaker, classify_provider_error, fatal_cause,
        provider_stopped_error)

    if IN_RETRY_LAYER.get() or _runs_on_this_mac(config):
        return await make_coro()
    provider = (config.provider or "unknown").lower()
    until, why = _DEAD.get(provider, (0.0, "rate-limit"))
    if until > time.monotonic():
        raise provider_stopped_error(provider, why)  # the cause it died of: no credit, a refused key, or a rate limit
    breaker = ProviderCircuitBreaker()  # per call: the retries are what is bounded here; process-wide state is below
    try:
        result = await call_with_breaker(make_coro, provider=provider, breaker=breaker, label=config.model)
    except Exception as exc:
        kind = classify_provider_error(exc)
        if kind == "fatal":
            _DEAD[provider] = (time.monotonic() + DEAD_FOR_SECONDS, fatal_cause(exc))
        elif breaker.is_open(provider):
            _DEAD[provider] = (time.monotonic() + DEAD_FOR_SECONDS, "rate-limit")
        elif kind in ("slow-down", "transient"):  # the call's retries are spent: one failure of the provider's, K in a row open it
            _SPENT[provider] = _SPENT.get(provider, 0) + 1
            if _SPENT[provider] >= DEFAULT_BREAKER_THRESHOLD:
                _DEAD[provider] = (time.monotonic() + DEAD_FOR_SECONDS, "rate-limit")
        raise
    _SPENT.pop(provider, None)
    return result
