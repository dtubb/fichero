"""A rate limit backs off, then PAUSES the run with its cause; never a tight loop (#6584, #6354).

Spec: docs/contributor_manual/specs/ui/activity-pane.md `activity.limits.rate-limit-backs-off-then-pauses`,
docs/contributor_manual/specs/ai/run-failure-alerts.md decision 9. WHY (owner 2026-11-13): OpenRouter told a user she was
sending too many requests while her run went on failing page after page. At the one retry layer: a stub provider answering
429 with a Retry-After sees gaps of at least that between sends; when the back-off is spent the run this call belongs to is
asked to pause and the pause carries the provider; a provider that answers clears it.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from fichero_server.execution.cancellation import clear_pause, pause_requested
from fichero_server.llm import retry
from fichero_server.workflows import circuit_breaker as cb
from fichero_server.workflows.node_context import set_current_node


class _TooMany(Exception):
    status_code = 429

    def __init__(self, retry_after):
        super().__init__("429 Too Many Requests: rate limit exceeded")
        self.retry_after = retry_after


class _Config:
    provider = "openrouter"
    model = "stub"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(retry, "_DEAD", {})
    monkeypatch.setattr(retry, "_SPENT", {})
    monkeypatch.setattr(retry, "_PAUSED_FOR_RATE_LIMIT", {})
    monkeypatch.setattr(cb, "compute_backoff_delay", lambda *a, **k: 0.0)  # the provider's Retry-After alone paces the sends
    monkeypatch.setattr(retry, "_runs_on_this_mac", lambda config: False, raising=False)
    import fichero_server.llm as llm
    monkeypatch.setattr(llm, "_runs_on_this_mac", lambda config: False)
    yield
    clear_pause("run-429")


def test_a_rate_limited_provider_is_waited_for_then_the_run_pauses_with_the_cause(monkeypatch):
    sends: list[float] = []

    async def call():
        sends.append(time.monotonic())
        raise _TooMany(0.3)

    async def go():
        set_current_node("read", run_id="run-429")
        with pytest.raises(_TooMany):
            await retry.resilient(call, _Config())

    asyncio.run(go())

    assert len(sends) == 1 + cb.DEFAULT_MAX_RETRIES, "one send and the bounded retries, then no more"
    gaps = [b - a for a, b in zip(sends, sends[1:])]
    assert all(g >= 0.29 for g in gaps), f"a send came sooner than the provider's Retry-After: {gaps}"
    assert pause_requested("run-429"), "the run was asked to pause, not left to fail page after page"
    assert retry.paused_for_rate_limit(["run-429"]) == {"provider": "openrouter", "retry_after_seconds": 0.3}
    assert "openrouter" not in retry.dead_marks(), "one spent call does not mark the provider dead; K in a row do (#950)"


def test_the_pause_is_forgotten_when_the_run_continues_and_a_good_answer_clears_the_mark(monkeypatch):
    retry._PAUSED_FOR_RATE_LIMIT["run-429"] = {"provider": "openrouter", "retry_after_seconds": None}
    retry.forget_rate_limit_pause("run-429")
    assert retry.paused_for_rate_limit(["run-429"]) is None

    async def ok():
        return "vecino"

    assert asyncio.run(retry.resilient(ok, _Config())) == "vecino"
    assert "openrouter" not in retry.dead_marks()


def test_the_words_name_the_provider_and_the_fix_without_a_code():
    from fichero_server.llm.failure import _build

    failure = _build("rate-limited", None, None, "", step="Read lines", provider="openrouter")
    assert failure.kind == "rate-limited"
    assert "limiting how fast" in failure.words and "429" not in failure.words
    assert "continue" in failure.fix.lower()
    assert "resume" in [a.kind for a in failure.actions]
