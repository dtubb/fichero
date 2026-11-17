"""OpenRouter's in-flight budget answer slows a run down, never fails it (#6671).

Spec: docs/contributor_manual/specs/ai/where-models-run.md `ai.where.one-retry-policy`,
docs/contributor_manual/specs/ui/activity-pane.md `activity.limits.rate-limit-backs-off-then-pauses`. WHY (owner 2026-11-17):
OpenRouter answered HTTP 402 `in_flight_budget_exhausted` under load; every 402 was fatal, the breaker opened at once and
30 of 37 pages failed. A fake provider stands in for it; no network, no key.
"""
from __future__ import annotations

import asyncio

import pytest

from fichero_server.execution.cancellation import clear_pause, pause_requested
from fichero_server.llm import retry
from fichero_server.workflows import circuit_breaker as cb
from fichero_server.workflows.node_context import set_current_node


class _InFlight(Exception):
    status_code = 402

    def __init__(self):
        super().__init__("402: This request would exceed your available credits given your current in-flight requests. "
                         "Retry after in-flight requests settle, or add credits.")
        self.body = {"error": {"code": 402, "metadata": {"reason": "in_flight_budget_exhausted"}}}


class _NoCredit(Exception):
    status_code = 402

    def __init__(self):
        super().__init__("402: Insufficient credits. Add more using https://openrouter.ai/credits")


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(cb, "PROVIDER_CALLS_AT_ONCE", 4)
    monkeypatch.setattr(cb, "_PROVIDER_SLOTS", {})
    monkeypatch.setattr(retry, "_PAUSED_FOR_RATE_LIMIT", {})
    yield
    clear_pause("run-6671")


def test_an_in_flight_402_is_a_slow_down_and_a_plain_402_stays_fatal():
    assert cb.classify_provider_error(_InFlight()) == "slow-down"
    assert cb.classify_provider_error(_NoCredit()) == "fatal"


def test_the_cap_halves_to_a_floor_of_one_and_rises_slowly_on_answers():
    cb._slow_down_cap("openrouter")
    assert cb.provider_cap("openrouter") == 2
    cb._slow_down_cap("openrouter")
    cb._slow_down_cap("openrouter")
    assert cb.provider_cap("openrouter") == 1
    for _ in range(3):
        cb._answered("openrouter")
    assert cb.provider_cap("openrouter") == 1, "slowly: not on every answer"
    cb._answered("openrouter")
    assert cb.provider_cap("openrouter") == 2
    for _ in range(40):
        cb._answered("openrouter")
    assert cb.provider_cap("openrouter") == 4, "never above where it started"


def test_a_provider_that_answers_in_flight_under_load_still_finishes_every_page():
    state = {"now": 0}

    async def one_page():
        if state["now"] >= 2:  # the key's credit fits two calls in flight
            raise _InFlight()
        state["now"] += 1
        try:
            await asyncio.sleep(0.01)
        finally:
            state["now"] -= 1
        return "ok"

    async def go():
        breaker = cb.ProviderCircuitBreaker()
        return await asyncio.gather(*(cb.call_with_breaker(one_page, provider="openrouter", breaker=breaker, max_retries=8,
                                                           base_delay=0.005, max_delay=0.02) for _ in range(12)))

    assert asyncio.run(go()) == ["ok"] * 12
    assert cb.provider_cap("openrouter") <= 4


def test_when_the_retries_are_spent_the_run_pauses_and_the_breaker_stays_closed():
    async def always():
        raise _InFlight()

    breaker = cb.ProviderCircuitBreaker()

    async def go():
        set_current_node("read", run_id="run-6671")
        with pytest.raises(cb.ProviderInFlightBudgetError):
            await cb.call_with_breaker(always, provider="openrouter", breaker=breaker, max_retries=2, base_delay=0.001,
                                       max_delay=0.002)

    asyncio.run(go())
    assert not breaker.is_open("openrouter"), "a provider that says wait is alive"
    assert pause_requested("run-6671")
    assert retry.paused_for_rate_limit(["run-6671"])["provider"] == "openrouter"


def test_a_plain_402_stops_at_the_first_send():
    sends = []

    async def broke():
        sends.append(1)
        raise _NoCredit()

    breaker = cb.ProviderCircuitBreaker()
    with pytest.raises(_NoCredit):
        asyncio.run(cb.call_with_breaker(broke, provider="openrouter", breaker=breaker, base_delay=0.001))
    assert len(sends) == 1 and breaker.is_open("openrouter")
