"""`ai.where.one-retry-policy` (#5944): ONE retry layer. The SDK's own retries are off, the layer's sends per call are
bounded, the provider's Retry-After is honoured, a 429 is a slow-down (not a breaker failure), a refused key or no credit
opens the breaker at once, and a call already inside the layer is not wrapped in a second one."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

from fichero_server import llm
from fichero_server.llm import LLMConfig, retry
from fichero_server.workflows import circuit_breaker as cb

CLOUD = LLMConfig(provider="openai", model="gpt-test", api_key="k")
LOCAL = LLMConfig(provider="ollama", model="llama3.2", api_base="http://127.0.0.1:11434")


class _Http(Exception):
    def __init__(self, status: int, text: str = "", retry_after: str | None = None):
        super().__init__(text or f"HTTP {status}")
        self.status_code = status
        self.response = type("R", (), {"headers": {"retry-after": retry_after} if retry_after else {}})()


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    waits: list[float] = []

    async def fake_sleep(delay):
        waits.append(delay)

    monkeypatch.setattr(cb.asyncio, "sleep", fake_sleep)
    retry._DEAD.clear()
    retry._SPENT.clear()
    return waits


@pytest.fixture
def waits(_no_waiting):
    return _no_waiting


def _always(status: int, **kw):
    sent = []

    async def once():
        sent.append(1)
        raise _Http(status, **kw)
    return sent, once


def test_the_sdk_retries_are_off_everywhere():
    source = (Path(llm.__file__)).read_text(encoding="utf-8")
    assert not re.search(r'"max_retries":\s*(?!0\b)\d+', source), "an SDK retry is back on a model"
    assert source.count('"max_retries": 0') >= 1


def test_a_call_that_keeps_getting_429_is_sent_exactly_one_plus_max_retries_times(waits):
    sent, once = _always(429)
    with pytest.raises(_Http):
        asyncio.run(retry.resilient(once, CLOUD))
    assert len(sent) == 1 + cb.DEFAULT_MAX_RETRIES == 5
    assert len(waits) == cb.DEFAULT_MAX_RETRIES


def test_a_call_inside_the_layer_is_not_wrapped_in_a_second_one(waits):
    sent, once = _always(503)

    async def outer():
        return await cb.call_with_breaker(lambda: retry.resilient(once, CLOUD), provider="openai",
                                          breaker=cb.ProviderCircuitBreaker(), max_retries=2)
    with pytest.raises(_Http):
        asyncio.run(outer())
    assert len(sent) == 1 + 2  # the outer layer's three sends, not three times the inner's five


def test_the_providers_retry_after_is_a_floor_for_the_wait(waits):
    sent, once = _always(429, retry_after="17")
    with pytest.raises(_Http):
        asyncio.run(retry.resilient(once, CLOUD))
    assert waits and all(w >= 17 for w in waits)


def test_a_retry_after_beyond_the_cap_is_capped(waits):
    sent, once = _always(429, retry_after="99999")
    with pytest.raises(_Http):
        asyncio.run(retry.resilient(once, CLOUD))
    assert max(waits) == cb.RETRY_AFTER_CAP


def test_429s_that_recover_never_open_the_breaker(waits):
    breaker = cb.ProviderCircuitBreaker(threshold=2)
    n = {"i": 0}

    async def flaky():
        n["i"] += 1
        if n["i"] % 3:
            raise _Http(429)
        return "ok"

    for _ in range(4):  # four calls, each with two 429s before its answer: 8 slow-downs, none a breaker failure
        assert asyncio.run(cb.call_with_breaker(flaky, provider="openai", breaker=breaker, max_retries=4)) == "ok"
    assert not breaker.is_open("openai")


def test_no_credit_opens_the_breaker_at_once_and_the_next_call_sends_nothing(waits):
    sent, once = _always(402, text="out of credits")
    with pytest.raises(_Http):
        asyncio.run(retry.resilient(once, CLOUD))
    assert len(sent) == 1 and waits == []  # no retry on a fatal error
    again, once2 = _always(200)
    with pytest.raises(cb.ProviderRateLimitedError):
        asyncio.run(retry.resilient(once2, CLOUD))
    assert again == []


def test_a_model_on_this_mac_is_not_retried_here(waits):
    sent, once = _always(503)
    with pytest.raises(_Http):
        asyncio.run(retry.resilient(once, LOCAL))
    assert len(sent) == 1


def test_a_bad_request_is_raised_at_once(waits):
    sent, once = _always(400, text="bad request")
    with pytest.raises(_Http):
        asyncio.run(retry.resilient(once, CLOUD))
    assert len(sent) == 1 and waits == []


def test_each_try_takes_the_lane_slot_again_so_a_backoff_does_not_hold_it():
    """Source pin: the retried unit is the slot AND the call (`_once` opens `_remote_llm_call_slot`), at every site."""
    source = Path(llm.__file__).read_text(encoding="utf-8")
    assert source.count("await _resilient(_once, config)") == 5
    assert source.count("async def _once") == 5


def test_our_own_call_budget_running_out_is_not_retried(waits):
    sent = []

    async def once():
        sent.append(1)
        raise asyncio.TimeoutError()
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(retry.resilient(once, CLOUD))
    assert len(sent) == 1 and waits == []  # four more tries at the full budget would be minutes


def test_calls_whose_retries_are_spent_fail_the_provider_fast_after_k_in_a_row_and_a_success_resets(waits):
    sent, once = _always(503)
    for _ in range(cb.DEFAULT_BREAKER_THRESHOLD - 1):
        with pytest.raises(_Http):
            asyncio.run(retry.resilient(once, CLOUD))
    ok = []

    async def fine():
        ok.append(1)
        return "ok"
    assert asyncio.run(retry.resilient(fine, CLOUD)) == "ok"  # the run of failures is broken
    for _ in range(cb.DEFAULT_BREAKER_THRESHOLD):
        with pytest.raises(_Http):
            asyncio.run(retry.resilient(once, CLOUD))
    before = len(sent)
    with pytest.raises(cb.ProviderRateLimitedError):
        asyncio.run(retry.resilient(once, CLOUD))
    assert len(sent) == before  # failed fast, nothing sent


def test_a_chat_turn_that_gets_a_429_then_an_answer_is_answered(tmp_path, monkeypatch, waits):
    """The chat's agent loop runs its model call under the one retry layer too: with the SDK retries at 0, one 429 would
    otherwise fail the turn (review 680)."""
    import contextlib

    from langchain_core.messages import AIMessage

    from fichero_server.actions.registry import ActionContext
    from fichero_server.api.routes.system import chat

    @contextlib.asynccontextmanager
    async def slot(config, *, library=None, subject=None):
        yield

    monkeypatch.setattr(llm, "_model_call_slot", slot)
    tries = []

    class Model:
        async def ainvoke(self, messages):
            tries.append(1)
            if len(tries) == 1:
                raise _Http(429, retry_after="1")
            return AIMessage(content="answer")

    library = tmp_path / "P.fichero"
    (library / "recipe").mkdir(parents=True)
    ctx = ActionContext(library_path=str(library))
    answer = asyncio.run(chat._ask(Model(), [], config=CLOUD, ctx=ctx))
    assert answer.content == "answer" and len(tries) == 2 and waits and waits[0] >= 1
