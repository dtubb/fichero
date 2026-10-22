"""A provider that cannot answer keeps its CAUSE (`ai.where.dead-provider-says-why`, review ## 950, #5944): no credit, a refused
key and a rate limit are three different things to tell a person. After the first refusal the provider is failed fast for a
while; every later call raises THAT cause's error, in plain words (no 'circuit open', no '$large'), and the vision tool
classes it by cause. A person with no credit or a bad key is never told to wait for a quota to reset."""
from __future__ import annotations

import asyncio

import pytest

from fichero_server.llm import LLMConfig, retry
from fichero_server.workflows import circuit_breaker as cb
from fichero_server.workflows.tools import vision_base as vb

CLOUD = LLMConfig(provider="anthropic", model="claude-test", api_key="k")
INTERNALS = ("circuit", "$large", "consecutive", "quota/rate-limit failures", "skipping remaining files")


class _Http(Exception):
    def __init__(self, status: int, text: str = ""):
        super().__init__(text or f"HTTP {status}")
        self.status_code = status


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    async def no_sleep(_delay):
        return None

    monkeypatch.setattr(cb.asyncio, "sleep", no_sleep)
    retry._DEAD.clear()
    retry._SPENT.clear()
    yield
    retry._DEAD.clear()
    retry._SPENT.clear()


def _refuse(status: int, text: str = ""):
    async def once():
        raise _Http(status, text)

    return once


def _two_calls(status: int, text: str = ""):
    """The first call is refused by the provider; the second is made while the provider is failed fast."""
    with pytest.raises(_Http):
        asyncio.run(retry.resilient(_refuse(status, text), CLOUD))
    sent = []

    async def never():
        sent.append(1)

    with pytest.raises(cb.ProviderRateLimitedError) as caught:
        asyncio.run(retry.resilient(never, CLOUD))
    assert not sent, "the failed-fast call reached the provider"
    return caught.value


def _plain(error: Exception) -> str:
    text = str(error)
    assert not any(word in text.lower() for word in INTERNALS), text
    assert "Anthropic" in text
    return text


def test_no_credit_stays_a_quota_error_and_says_to_add_credit_not_to_wait():
    error = _two_calls(402, "Your credit balance is too low")
    assert isinstance(error, cb.ProviderQuotaExhaustedError) and error.cause == "quota"
    text = _plain(error)
    assert "credit" in text and "wait" not in text.lower()


def test_a_refused_key_stays_a_key_error_and_says_to_check_the_key():
    error = _two_calls(401, "invalid x-api-key")
    assert isinstance(error, cb.ProviderKeyRefusedError) and error.cause == "key"
    text = _plain(error)
    assert "key" in text and "wait" not in text.lower()


def test_a_rate_limit_that_keeps_coming_stays_a_rate_limit_and_may_say_to_wait():
    for _ in range(cb.DEFAULT_BREAKER_THRESHOLD):
        with pytest.raises(_Http):
            asyncio.run(retry.resilient(_refuse(429, "slow down"), CLOUD))
    sent = []

    async def never():
        sent.append(1)

    with pytest.raises(cb.ProviderRateLimitedError) as caught:
        asyncio.run(retry.resilient(never, CLOUD))
    error = caught.value
    assert error.cause == "rate-limit" and not isinstance(error, (cb.ProviderQuotaExhaustedError, cb.ProviderKeyRefusedError))
    assert "slow down" in _plain(error) and not sent


def test_the_breaker_itself_raises_the_cause_it_tripped_on():
    breaker = cb.ProviderCircuitBreaker()
    asyncio.run(breaker.trip("anthropic", detail="402", cause="quota"))
    with pytest.raises(cb.ProviderQuotaExhaustedError):
        asyncio.run(breaker.check("anthropic"))


def test_fatal_cause_reads_the_status_and_the_words():
    assert cb.fatal_cause(_Http(401)) == "key" and cb.fatal_cause(_Http(402)) == "quota"
    assert cb.fatal_cause(_Http(400, "insufficient_quota")) == "quota"
    assert cb.fatal_cause(_Http(400, "Incorrect API key provided")) == "key"


@pytest.mark.parametrize(("error", "kind"), [
    (cb.ProviderQuotaExhaustedError("anthropic", failures=1), vb.VISION_ERROR_NO_CREDIT),
    (cb.ProviderKeyRefusedError("anthropic", failures=1), vb.VISION_ERROR_KEY_REFUSED),
    (cb.ProviderRateLimitedError("anthropic", failures=3), vb.VISION_ERROR_RATE_LIMITED),
])
def test_vision_classes_a_dead_provider_by_cause_and_never_retries_it(error, kind):
    assert vb.classify_vision_failure(error) == kind
    assert not vb.is_retryable_vision_failure(kind)
    sentence = vb.describe_vision_failure(kind)
    assert not any(word in sentence.lower() for word in INTERNALS)
    if kind != vb.VISION_ERROR_RATE_LIMITED:
        assert "wait" not in sentence.lower() and "later" not in sentence.lower()
