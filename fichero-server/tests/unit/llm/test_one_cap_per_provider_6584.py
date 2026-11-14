"""One cap on calls per provider across every run (#6584, `activity.limits.one-cap-per-kind-across-everything`).

Spec: docs/contributor_manual/specs/ui/activity-pane.md. WHY (owner 2026-11-13): a user was told by OpenRouter she was
sending too many requests; nothing capped calls per PROVIDER across runs, batches (5 per batch) and the fan-out. Every
cloud call passes through `call_with_breaker`, so the cap lives there: a stub provider counts how many calls it sees at once.
"""
from __future__ import annotations

import asyncio
import threading

from fichero_server.workflows import circuit_breaker as cb


def _runs(provider: str, calls: int, runs: int, seen: dict) -> None:
    """`runs` workflow-like threads, each on its own loop, together sending `calls` calls to `provider`."""
    lock = threading.Lock()

    async def one_call():
        with lock:
            seen["now"] += 1
            seen["peak"] = max(seen["peak"], seen["now"])
        await asyncio.sleep(0.02)
        with lock:
            seen["now"] -= 1
        return "ok"

    async def a_run(n):
        breaker = cb.ProviderCircuitBreaker()
        await asyncio.gather(*(cb.call_with_breaker(one_call, provider=provider, breaker=breaker) for _ in range(n)))

    per_run = calls // runs
    threads = [threading.Thread(target=lambda: asyncio.run(a_run(per_run))) for _ in range(runs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)


def test_fifty_calls_across_three_runs_to_one_provider_hold_at_most_the_cap(monkeypatch):
    monkeypatch.setattr(cb, "PROVIDER_CALLS_AT_ONCE", 3)
    monkeypatch.setattr(cb, "_PROVIDER_SLOTS", {})
    seen = {"now": 0, "peak": 0}

    _runs("openrouter", 51, 3, seen)

    assert seen["peak"] <= 3, f"{seen['peak']} calls to one provider were in flight at once"
    assert seen["peak"] >= 2, "the cap is a cap, not a serialisation"
    assert cb.calls_in_flight("openrouter") == 0, "every slot is given back"


def test_a_second_providers_calls_are_not_held_by_the_firsts_cap(monkeypatch):
    monkeypatch.setattr(cb, "PROVIDER_CALLS_AT_ONCE", 1)
    monkeypatch.setattr(cb, "_PROVIDER_SLOTS", {})
    seen = {"now": 0, "peak": 0}
    both = threading.Thread(target=lambda: _runs("anthropic", 4, 2, seen))
    both.start()
    _runs("openai", 4, 2, seen)
    both.join(30)

    assert seen["peak"] == 2, "one in flight per provider, two providers at once"
