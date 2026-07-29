"""Tests for the per-provider circuit breaker + backoff (#2543).

Covers the C5 reliability fix: during a long vision fan-out run, a provider
rate-limit/quota error must (a) back off and retry the file on a *retryable*
error, (b) NOT retry on a *terminal* (auth) error, and (c) after K consecutive
quota failures, OPEN the breaker so the remaining files for that provider fail
fast instead of hammering a dead provider for ~99k calls.
"""

from __future__ import annotations

import asyncio

import pytest

from fichero_server.llm import ProviderQuotaError
from fichero_server.workflows.circuit_breaker import (
    DEFAULT_BREAKER_COOLDOWN,
    ProviderCircuitBreaker,
    ProviderRateLimitedError,
    call_with_breaker,
    classify_provider_error,
    compute_backoff_delay,
)


@pytest.fixture
def no_sleep(monkeypatch):
    """Replace circuit_breaker.asyncio.sleep with an instant recorder.

    Returns the list of delays passed to sleep so tests can assert that a
    backoff actually happened and how long it was, without real waiting.
    """
    delays: list[float] = []

    async def _fake_sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(
        "fichero_server.workflows.circuit_breaker.asyncio.sleep", _fake_sleep
    )
    return delays


def _quota_exc() -> ProviderQuotaError:
    return ProviderQuotaError("openai", status_code=429, detail="rate limit")


# ---------------------------------------------------------------------------
# classify_provider_error
# ---------------------------------------------------------------------------


def test_classify_provider_quota_error_is_retryable():
    assert classify_provider_error(_quota_exc()) == "retryable"


def test_classify_429_runtimeerror_is_retryable():
    exc = RuntimeError("HTTP 429: too many requests, rate limit exceeded")
    assert classify_provider_error(exc) == "retryable"


def test_classify_auth_error_is_terminal():
    exc = RuntimeError("401 Unauthorized: invalid api key")
    assert classify_provider_error(exc) == "terminal"


def test_classify_generic_error_is_terminal():
    assert classify_provider_error(ValueError("bad image format")) == "terminal"


# ---------------------------------------------------------------------------
# compute_backoff_delay
# ---------------------------------------------------------------------------


def test_backoff_is_exponential_and_capped():
    delays = [
        compute_backoff_delay(i, base=1.0, cap=8.0, jitter=0.0) for i in range(6)
    ]
    assert delays == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]  # doubles, then capped


def test_backoff_jitter_stays_within_bounds():
    for i in range(6):
        d = compute_backoff_delay(i, base=1.0, cap=30.0, jitter=0.25)
        base = min(30.0, 1.0 * (2 ** i))
        assert base <= d <= base * 1.25


# ---------------------------------------------------------------------------
# call_with_breaker — backoff / retry behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retryable_backs_off_then_succeeds(no_sleep):
    breaker = ProviderCircuitBreaker(threshold=5)
    calls = {"n": 0}

    async def make_coro():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _quota_exc()
        return "OK"

    result = await call_with_breaker(
        lambda: make_coro(),
        provider="openai",
        breaker=breaker,
        base_delay=1.0,
        max_retries=4,
    )

    assert result == "OK"
    assert calls["n"] == 2  # failed once, retried once
    assert len(no_sleep) == 1  # exactly one backoff
    assert not breaker.is_open("openai")


@pytest.mark.asyncio
async def test_terminal_error_does_not_retry(no_sleep):
    breaker = ProviderCircuitBreaker(threshold=5)
    calls = {"n": 0}

    async def make_coro():
        calls["n"] += 1
        raise RuntimeError("401 unauthorized: invalid api key")

    with pytest.raises(RuntimeError, match="401"):
        await call_with_breaker(
            lambda: make_coro(),
            provider="openai",
            breaker=breaker,
            base_delay=1.0,
            max_retries=4,
        )

    assert calls["n"] == 1  # no retry
    assert no_sleep == []  # no backoff
    assert not breaker.is_open("openai")  # terminal errors don't count


@pytest.mark.asyncio
async def test_backoff_is_bounded_by_max_retries(no_sleep):
    # threshold high so the breaker never opens; we only exercise the retry cap.
    breaker = ProviderCircuitBreaker(threshold=100)
    calls = {"n": 0}

    async def make_coro():
        calls["n"] += 1
        raise _quota_exc()

    with pytest.raises(ProviderQuotaError):
        await call_with_breaker(
            lambda: make_coro(),
            provider="openai",
            breaker=breaker,
            base_delay=1.0,
            max_retries=3,
        )

    # 1 initial attempt + 3 retries == 4 calls, then re-raise.
    assert calls["n"] == 4
    assert len(no_sleep) == 3  # backed off before each retry, bounded


# ---------------------------------------------------------------------------
# call_with_breaker — circuit breaker open / fail-fast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_breaker_opens_after_k_failures_then_fails_fast(no_sleep):
    # K=3: three consecutive quota failures should OPEN the breaker, after
    # which further files for that provider must fail fast WITHOUT calling
    # the provider.
    breaker = ProviderCircuitBreaker(threshold=3, cooldown=DEFAULT_BREAKER_COOLDOWN)
    provider_calls = {"n": 0}

    async def make_coro():
        provider_calls["n"] += 1
        raise _quota_exc()

    # Each "file" gets one attempt; we disable per-file retries (max_retries=0)
    # so each file contributes exactly one provider failure, making the
    # consecutive-failure accounting easy to assert.
    async def run_one_file():
        return await call_with_breaker(
            lambda: make_coro(),
            provider="openai",
            breaker=breaker,
            max_retries=0,
        )

    # Files 1 and 2: quota error, breaker not yet open -> ProviderQuotaError.
    for _ in range(2):
        with pytest.raises(ProviderQuotaError):
            await run_one_file()
    assert not breaker.is_open("openai")

    # File 3: third consecutive failure trips the breaker -> fail fast.
    with pytest.raises(ProviderRateLimitedError):
        await run_one_file()
    assert breaker.is_open("openai")

    calls_after_open = provider_calls["n"]  # should be 3 (one per file so far)
    assert calls_after_open == 3

    # Files 4..10: breaker is OPEN -> fail fast, NO further provider calls.
    for _ in range(7):
        with pytest.raises(ProviderRateLimitedError):
            await run_one_file()

    assert provider_calls["n"] == calls_after_open  # no new vision() calls


@pytest.mark.asyncio
async def test_different_providers_have_independent_breakers(no_sleep):
    breaker = ProviderCircuitBreaker(threshold=2, cooldown=DEFAULT_BREAKER_COOLDOWN)

    async def fail_openai():
        raise _quota_exc()

    google_calls = {"n": 0}

    async def ok_google():
        google_calls["n"] += 1
        return "GOOGLE_OK"

    # Trip openai's breaker. First failure (count=1 < 2) surfaces the
    # underlying quota error; the second failure trips the breaker and
    # fails fast.
    with pytest.raises(ProviderQuotaError):
        await call_with_breaker(
            lambda: fail_openai(),
            provider="openai",
            breaker=breaker,
            max_retries=0,
        )
    with pytest.raises(ProviderRateLimitedError):
        await call_with_breaker(
            lambda: fail_openai(),
            provider="openai",
            breaker=breaker,
            max_retries=0,
        )
    assert breaker.is_open("openai")
    assert not breaker.is_open("google")

    # openai fails fast...
    with pytest.raises(ProviderRateLimitedError):
        await call_with_breaker(
            lambda: fail_openai(),
            provider="openai",
            breaker=breaker,
            max_retries=0,
        )

    # ...but google is unaffected and succeeds.
    result = await call_with_breaker(
        lambda: ok_google(),
        provider="google",
        breaker=breaker,
        max_retries=0,
    )
    assert result == "GOOGLE_OK"
    assert google_calls["n"] == 1


@pytest.mark.asyncio
async def test_success_resets_consecutive_failure_count(no_sleep):
    breaker = ProviderCircuitBreaker(threshold=3)
    seq = ["fail", "ok", "fail", "fail"]  # never 3-in-a-row
    idx = {"i": 0}

    async def make_coro():
        action = seq[idx["i"]]
        idx["i"] += 1
        if action == "fail":
            raise _quota_exc()
        return "OK"

    # File A: fail then (retry) ok -> success resets the counter.
    res = await call_with_breaker(
        lambda: make_coro(),
        provider="openai",
        breaker=breaker,
        base_delay=1.0,
        max_retries=2,
    )
    assert res == "OK"
    # File B: two more failures — but the counter was reset, so 2 < 3 -> the
    # breaker stays CLOSED (proves consecutive, not cumulative, counting).
    with pytest.raises(ProviderQuotaError):
        await call_with_breaker(
            lambda: make_coro(),
            provider="openai",
            breaker=breaker,
            base_delay=1.0,
            max_retries=1,
        )
    assert not breaker.is_open("openai")


# ---------------------------------------------------------------------------
# call_with_breaker — semaphore is released during backoff sleep
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semaphore_released_during_backoff_sleep(monkeypatch):
    breaker = ProviderCircuitBreaker(threshold=5)
    sem = asyncio.Semaphore(1)
    await sem.acquire()  # the caller holds the only slot (mimics _run_one)
    assert sem.locked()

    free_during_sleep = {"observed": False}

    async def _observing_sleep(_delay):
        # While the file is backing off, the slot must be FREE so siblings
        # can run. Semaphore(1) starts locked; release() makes locked() False.
        free_during_sleep["observed"] = not sem.locked()

    monkeypatch.setattr(
        "fichero_server.workflows.circuit_breaker.asyncio.sleep", _observing_sleep
    )

    calls = {"n": 0}

    async def make_coro():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _quota_exc()
        return "OK"

    result = await call_with_breaker(
        lambda: make_coro(),
        provider="openai",
        breaker=breaker,
        semaphore=sem,
        base_delay=1.0,
        max_retries=2,
    )

    assert result == "OK"
    assert free_during_sleep["observed"] is True  # slot freed during sleep
    assert sem.locked()  # re-acquired afterwards; net count preserved


@pytest.mark.asyncio
async def test_breaker_open_upfront_does_not_call_provider(no_sleep):
    breaker = ProviderCircuitBreaker(threshold=1)
    # Trip the breaker with one failure.
    await breaker.record_failure("openai")
    assert breaker.is_open("openai")

    called = {"n": 0}

    async def make_coro():
        called["n"] += 1
        return "SHOULD_NOT_RUN"

    with pytest.raises(ProviderRateLimitedError):
        await call_with_breaker(
            lambda: make_coro(),
            provider="openai",
            breaker=breaker,
            max_retries=3,
        )
    assert called["n"] == 0  # never called the provider


@pytest.mark.asyncio
async def test_half_open_probe_after_cooldown(monkeypatch):
    # cooldown=0 means the breaker immediately allows a half-open probe.
    breaker = ProviderCircuitBreaker(threshold=1, cooldown=0.0)
    await breaker.record_failure("openai")
    assert breaker.is_open("openai")

    called = {"n": 0}

    async def ok():
        called["n"] += 1
        return "RECOVERED"

    # With cooldown elapsed, check() allows a single probe through -> success.
    result = await call_with_breaker(
        lambda: ok(),
        provider="openai",
        breaker=breaker,
        max_retries=0,
    )
    assert result == "RECOVERED"
    assert called["n"] == 1
    assert not breaker.is_open("openai")  # success reset the breaker
