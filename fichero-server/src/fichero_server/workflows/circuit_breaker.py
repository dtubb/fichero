"""Per-provider circuit breaker + backoff for vision/LLM fan-out (#2543).

During a long fan-out run (e.g. transcribing ~100k files) a provider
rate-limit / quota error (HTTP 429, ProviderQuotaError) used to be logged
per file while the loop kept calling the *dead* provider for every one of
the remaining files. No backoff, no circuit breaker — the run could burn
~99k doomed calls.

This module adds two cooperating pieces, designed to be shared across the
bounded-concurrent ``asyncio.gather`` tasks that drive vision fan-out:

  * **Exponential backoff with jitter** on *retryable* (429 / quota /
    rate-limit) errors, bounded by a max number of retries and a max
    delay. Terminal errors (auth / invalid-key / other non-429) are NOT
    retried — they propagate immediately.

  * **A per-provider circuit breaker** that OPENS after ``threshold``
    consecutive quota failures for a provider. While OPEN, further calls
    for that provider *fail fast* with a clear ``ProviderRateLimitedError``
    instead of hammering the provider. A single half-open probe is allowed
    once ``cooldown`` seconds have elapsed, so a transient rate-limit can
    recover without aborting the whole run.

Concurrency: the breaker is created **per run** and shared across the
concurrent tasks, so every state mutation is guarded by an
``asyncio.Lock`` bound to the running loop. Counters are only ever touched
inside the lock, so there are no lost updates under ``asyncio.gather``.

Reuses ``fichero_server.llm``'s quota classification (``ProviderQuotaError`` and
``_is_provider_quota_error``) so the workflow layer and the LLM layer agree
on what a rate-limit/quota error looks like. That import is deferred to call
time to avoid an import cycle (``fichero_server.llm`` is heavy and the vision tools
already import it lazily).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Backoff / breaker defaults. The vision driver overrides these from env
# (FICHERO_VISION_BACKOFF_*, FICHERO_VISION_BREAKER_THRESHOLD) but these are
# the sane defaults used everywhere else.
DEFAULT_MAX_RETRIES = 4
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0
DEFAULT_JITTER = 0.25
DEFAULT_BREAKER_THRESHOLD = 5
DEFAULT_BREAKER_COOLDOWN = 30.0


class ProviderRateLimitedError(RuntimeError):
    """Raised when a provider's circuit breaker is OPEN — fail fast.

    Subsequent files for the rate-limited provider raise this *without*
    calling the provider, so a long run does not silently burn the rest of
    its calls against a dead provider. The message is deliberately loud so
    it surfaces in the per-file error and the aggregated run error.
    """

    def __init__(
        self,
        provider: str,
        *,
        failures: int,
        detail: str | None = None,
    ) -> None:
        self.provider = provider
        self.failures = failures
        self.detail = detail
        super().__init__(
            f"Provider {provider} rate-limited, circuit open after "
            f"{failures} consecutive quota/rate-limit failures — skipping "
            "remaining files for this provider this run. Set a different "
            "$large provider in Settings or wait for the quota to reset."
        )


def classify_provider_error(exc: BaseException) -> str:
    """Classify a provider exception as ``"retryable"`` or ``"terminal"``.

    Retryable = 429 / quota / rate-limit / "too many requests" — back off
    and retry, and count toward the circuit breaker. Terminal = auth,
    invalid key, other non-429 4xx, or anything else — propagate
    immediately (the caller records the per-file error and moves on).

    Reuses ``fichero_server.llm``'s quota detection so the two layers stay in
    sync. The import is deferred to avoid an import cycle.
    """
    from fichero_server.llm import ProviderQuotaError, _is_provider_quota_error

    if isinstance(exc, ProviderQuotaError):
        return "retryable"
    try:
        is_quota, _status, _detail = _is_provider_quota_error(exc)
    except Exception:  # pragma: no cover - classification must never crash
        is_quota = False
    return "retryable" if is_quota else "terminal"


def compute_backoff_delay(
    attempt: int,
    *,
    base: float = DEFAULT_BASE_DELAY,
    cap: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
) -> float:
    """Exponential backoff with additive jitter, bounded by ``cap``.

    ``attempt`` is 0-based: attempt 0 -> ``base``, attempt 1 -> ``2*base``,
    capped at ``cap``. Jitter adds up to ``jitter`` of the (capped) delay so
    concurrent tasks do not retry in lock-step (thundering herd).
    """
    delay = min(cap, base * (2 ** max(0, attempt)))
    if jitter:
        delay += random.uniform(0.0, delay * jitter)
    return delay


@dataclass
class _ProviderState:
    consecutive_failures: int = 0
    opened_at: float | None = None
    last_detail: str | None = None


class ProviderCircuitBreaker:
    """Shared, asyncio-safe per-provider circuit breaker for one run.

    OPENs after ``threshold`` consecutive quota failures for a provider.
    While OPEN, :meth:`check` raises :class:`ProviderRateLimitedError`. A
    single half-open probe is allowed once ``cooldown`` seconds have
    elapsed since the breaker opened; a success on that probe resets the
    breaker, a further failure re-opens it.

    All mutations are guarded by an ``asyncio.Lock`` so the breaker is safe
    to share across ``asyncio.gather`` tasks.
    """

    def __init__(
        self,
        *,
        threshold: int = DEFAULT_BREAKER_THRESHOLD,
        cooldown: float = DEFAULT_BREAKER_COOLDOWN,
    ) -> None:
        self.threshold = max(1, int(threshold))
        self.cooldown = max(0.0, float(cooldown))
        self._states: dict[str, _ProviderState] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _key(provider: str | None) -> str:
        return (provider or "unknown").strip().lower() or "unknown"

    async def check(self, provider: str | None) -> None:
        """Fail fast if the breaker is OPEN for ``provider``.

        Honours a half-open probe: once ``cooldown`` has elapsed since the
        breaker opened, the gate is tentatively closed for a single caller
        to test recovery. Raises :class:`ProviderRateLimitedError` while
        OPEN and still cooling down.
        """
        key = self._key(provider)
        async with self._lock:
            st = self._states.get(key)
            if st is None or st.opened_at is None:
                return
            if (time.monotonic() - st.opened_at) >= self.cooldown:
                # Half-open probe: tentatively close the gate. The next
                # failure re-opens; a success resets.
                st.opened_at = None
                logger.info(
                    "Circuit half-open probe for provider %s (cooldown elapsed)",
                    provider or "unknown",
                )
                return
            raise ProviderRateLimitedError(
                provider or "unknown",
                failures=st.consecutive_failures,
                detail=st.last_detail,
            )

    async def record_success(self, provider: str | None) -> None:
        """Reset the consecutive-failure count for ``provider``."""
        key = self._key(provider)
        async with self._lock:
            st = self._states.get(key)
            if st is not None:
                st.consecutive_failures = 0
                st.opened_at = None
                st.last_detail = None

    async def record_failure(
        self,
        provider: str | None,
        *,
        detail: str | None = None,
    ) -> bool:
        """Record one quota failure for ``provider``.

        Returns ``True`` iff the breaker is OPEN after this failure. Logs
        loudly the moment the breaker trips so the run surfaces the cause.
        """
        key = self._key(provider)
        async with self._lock:
            st = self._states.get(key)
            if st is None:
                st = _ProviderState()
                self._states[key] = st
            st.consecutive_failures += 1
            st.last_detail = detail
            if st.consecutive_failures >= self.threshold and st.opened_at is None:
                st.opened_at = time.monotonic()
                logger.error(
                    "Circuit OPEN for provider %s after %d consecutive "
                    "quota/rate-limit failures — failing fast for the "
                    "remaining files this run.",
                    provider or "unknown",
                    st.consecutive_failures,
                )
            return st.opened_at is not None

    def is_open(self, provider: str | None) -> bool:
        """Cheap, lock-free snapshot of whether ``provider`` is OPEN."""
        st = self._states.get(self._key(provider))
        return bool(st and st.opened_at is not None)


async def call_with_breaker(
    make_coro,
    *,
    provider: str | None,
    breaker: ProviderCircuitBreaker,
    semaphore: asyncio.Semaphore | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    jitter: float = DEFAULT_JITTER,
    label: str = "",
):
    """Run ``make_coro()`` with per-provider breaker + exponential backoff.

    ``make_coro`` is a zero-arg callable returning a *fresh* awaitable on
    each call (so retries re-issue the request). Behaviour:

      * Fail fast up front: if the breaker is already OPEN for ``provider``,
        raise :class:`ProviderRateLimitedError` without calling
        ``make_coro`` at all.
      * On a **retryable** (429 / quota / rate-limit) error: record a
        breaker failure; if that opens the breaker, fail fast; otherwise
        back off (exponential + jitter, bounded by ``max_retries`` /
        ``max_delay``) and retry.
      * On a **terminal** error (auth / non-429): re-raise immediately.
      * On success: reset the provider's failure count and return.

    Semaphore handling (#2543): if a ``semaphore`` is supplied it is
    *released* during each backoff sleep and re-acquired afterwards, so a
    backed-off file never pins a concurrency slot while it waits — other
    providers' files can use the slot during the sleep.
    """
    await breaker.check(provider)
    attempt = 0
    while True:
        try:
            result = await make_coro()
        except Exception as exc:
            if classify_provider_error(exc) != "retryable":
                raise
            # Retryable quota/rate-limit error: count it and re-check the
            # breaker. If this failure tripped it (or it was already open),
            # check() raises ProviderRateLimitedError -> fail fast.
            await breaker.record_failure(provider, detail=str(exc))
            await breaker.check(provider)
            if attempt >= max_retries:
                # Exhausted retries without tripping the breaker — surface
                # the underlying error to the per-file handler.
                raise
            delay = compute_backoff_delay(
                attempt, base=base_delay, cap=max_delay, jitter=jitter
            )
            attempt += 1
            logger.warning(
                "Retryable rate-limit/quota error%s (provider=%s): backing "
                "off %.2fs before retry %d/%d (%s)",
                f" for {label}" if label else "",
                provider or "unknown",
                delay,
                attempt,
                max_retries,
                exc,
            )
            if semaphore is not None:
                # Free the slot for the duration of the sleep so a backed-off
                # file does not starve other providers' files.
                semaphore.release()
                try:
                    await asyncio.sleep(delay)
                finally:
                    await semaphore.acquire()
            else:
                await asyncio.sleep(delay)
            continue
        else:
            await breaker.record_success(provider)
            return result
