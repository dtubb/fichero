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
#: How long past its 30 s a provider's mark of no credit or a refused key still tells a PLAN (`dead_marks`): the person who topped up
#: or fixed the key then replans; a call that succeeds clears the mark at once.
PLAN_MEMORY_SECONDS = 900.0
_SPENT: dict[str, int] = {}  # provider -> calls in a row whose retries were spent; K of them fail the provider fast
#: run id -> {provider, retry_after_seconds, wait_seconds}: the runs asked to pause because their provider is rate-limiting
#: (`activity.limits.rate-limit-backs-off-then-pauses`, owner 2026-11-13): paused with that cause, never a failed page per 429.
_PAUSED_FOR_RATE_LIMIT: dict[str, dict] = {}
#: How many calls in a row to one provider must spend their bounded back-off on 429s before the runs calling it pause (the
#: review's number, 2026-11-13): the back-off IS the automatic retrying; this is where it stops being automatic.
RATE_LIMIT_PAUSE_AFTER = 3
#: The least a paused run's row asks the person to wait before Continue: the provider's Retry-After, never under a minute.
RATE_LIMIT_WAIT_SECONDS = 60.0
#: provider -> consecutive calls whose back-off was spent on 429s (reset by an answer).
_SLOWED: dict[str, int] = {}


def paused_for_rate_limit(run_ids) -> dict | None:
    """The rate-limit pause of the first of `run_ids` asked to pause for one: `{provider, retry_after_seconds}`, else None."""
    return next((_PAUSED_FOR_RATE_LIMIT[r] for r in run_ids if r and r in _PAUSED_FOR_RATE_LIMIT), None)


def forget_rate_limit_pause(run_id: str | None) -> None:
    """The run goes on (Continue): it is no longer paused for a rate limit."""
    if run_id:
        _PAUSED_FOR_RATE_LIMIT.pop(run_id, None)


def _pause_the_run_for(provider: str, exc: BaseException) -> None:
    """The provider is rate-limiting: ask the run this call belongs to to pause at its next boundary, with the cause, so the
    run reads paused with "<Provider> is limiting how fast Fichero can send" and its Continue, not a failed page per 429."""
    from fichero_server.llm.spend import _ask_run_to_pause
    from fichero_server.workflows.circuit_breaker import retry_after_seconds

    run_id = _ask_run_to_pause()
    if run_id:
        asked = retry_after_seconds(exc)
        _PAUSED_FOR_RATE_LIMIT[run_id] = {"provider": provider, "retry_after_seconds": asked,
                                          "wait_seconds": max(asked or 0.0, RATE_LIMIT_WAIT_SECONDS)}


def dead_marks() -> dict[str, tuple[str, float]]:
    """Read-only: each provider marked dead and recently enough for a plan to heed (`ai.cloud.plan-knows-a-dead-key`, #6097), as
    `provider -> (cause, seconds since it was marked)`; the cause is `quota` (no credit), `key` (a refused key) or `rate-limit`."""
    now = time.monotonic()
    return {p: (why, round(now - (until - DEAD_FOR_SECONDS), 1)) for p, (until, why) in dict(_DEAD).items()
            if now < until + PLAN_MEMORY_SECONDS}


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
            _pause_the_run_for(provider, exc)
        elif kind in ("slow-down", "transient"):  # the call's retries are spent: one failure of the provider's, K in a row open it
            _SPENT[provider] = _SPENT.get(provider, 0) + 1
            if _SPENT[provider] >= DEFAULT_BREAKER_THRESHOLD:
                _DEAD[provider] = (time.monotonic() + DEAD_FOR_SECONDS, "rate-limit")
            if kind == "slow-down":
                # A rate limit that outlasts the back-off RATE_LIMIT_PAUSE_AFTER calls in a row pauses the runs calling the
                # provider (owner 2026-11-13): never a tight loop, never a failed page per 429; the fail-fast mark keeps its
                # own K-in-a-row rule above.
                _SLOWED[provider] = _SLOWED.get(provider, 0) + 1
                if _SLOWED[provider] >= RATE_LIMIT_PAUSE_AFTER:
                    _pause_the_run_for(provider, exc)
        raise
    _SLOWED.pop(provider, None)
    _SPENT.pop(provider, None)
    _DEAD.pop(provider, None)  # it answered: whatever marked it dead is over
    return result
