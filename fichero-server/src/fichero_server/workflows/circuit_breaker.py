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
import contextvars
import logging
import os
import random
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

#: True while a call runs inside `call_with_breaker`: the llm layer wraps its own calls in the same retry layer only when
#: this is False, so a call is retried by exactly one layer (`ai.where.one-retry-policy`, #5944).
IN_RETRY_LAYER: contextvars.ContextVar[bool] = contextvars.ContextVar("in_retry_layer", default=False)

# Backoff / breaker defaults. The vision driver overrides these from env
# (FICHERO_VISION_BACKOFF_*, FICHERO_VISION_BREAKER_THRESHOLD) but these are
# the sane defaults used everywhere else.
DEFAULT_MAX_RETRIES = 4
DEFAULT_BASE_DELAY = 1.0
DEFAULT_MAX_DELAY = 30.0
DEFAULT_JITTER = 0.25
DEFAULT_BREAKER_THRESHOLD = 5
DEFAULT_BREAKER_COOLDOWN = 30.0

#: How many calls to ONE provider the whole engine has in flight at once, across every run, recipe, batch and automatic
#: job (`activity.limits.one-cap-per-kind-across-everything`, owner 2026-11-13: never hammer a provider). Every cloud call
#: passes through `call_with_breaker`, so the slot is held here. The default is the network lane's width (4): the lane's own
#: per-provider fairness (`activity.run.lane-cap-per-mac`) is the finer rule for work the lane runs, and a cap under the lane's
#: width would hold a lane slot while a call waits for a provider slot. `FICHERO_CLOUD_CALLS_AT_ONCE` overrides until the
#: setting exists (1-8).
PROVIDER_CALLS_AT_ONCE = min(8, max(1, int(os.environ.get("FICHERO_CLOUD_CALLS_AT_ONCE", "4") or 4)))
#: How many answers in a row (after an in-flight-budget answer cut the cap) raise a provider's cap back by one.
ANSWERS_PER_CAP_STEP = 4


class _Cap:
    """One provider's in-flight cap: it starts at `PROVIDER_CALLS_AT_ONCE`, is halved by an in-flight-budget answer (floor 1)
    and rises by one per `ANSWERS_PER_CAP_STEP` answers, never past where it started (#6671)."""

    def __init__(self, start: int) -> None:
        self.start = self.cap = start
        self.answers = 0


_PROVIDER_SLOTS: dict[str, _Cap] = {}
_IN_FLIGHT: dict[str, int] = {}
_SLOTS_LOCK = threading.Lock()


def _cap_for(provider: str | None) -> _Cap:
    key = provider or "unknown"
    cap = _PROVIDER_SLOTS.get(key)
    if cap is None:
        cap = _PROVIDER_SLOTS[key] = _Cap(PROVIDER_CALLS_AT_ONCE)
    return cap


def provider_cap(provider: str | None) -> int:
    """How many calls to `provider` may be in flight now (the start cap, less what in-flight-budget answers took)."""
    with _SLOTS_LOCK:
        return _cap_for(provider).cap


def _slow_down_cap(provider: str | None) -> None:
    """The provider said its credit does not fit the calls in flight: halve its cap (floor 1)."""
    with _SLOTS_LOCK:
        cap = _cap_for(provider)
        cap.cap = max(1, cap.cap // 2)
        cap.answers = 0


def _answered(provider: str | None) -> None:
    """A call to `provider` was answered: after `ANSWERS_PER_CAP_STEP` of them a lowered cap rises by one."""
    with _SLOTS_LOCK:
        cap = _cap_for(provider)
        if cap.cap >= cap.start:
            return
        cap.answers += 1
        if cap.answers >= ANSWERS_PER_CAP_STEP:
            cap.cap += 1
            cap.answers = 0


def calls_in_flight(provider: str | None) -> int:
    """How many calls to `provider` hold a slot now (the waiting words: "3 of 3 OpenRouter calls in flight")."""
    with _SLOTS_LOCK:
        return _IN_FLIGHT.get(provider or "unknown", 0)


def _inside_a_lane() -> bool:
    """A call made by a job a lane thread runs: the lane's own width and per-provider fairness (`activity.run.lane-cap-per-mac`)
    already cap it, and a wait here would hold a lane thread; the provider slot is for calls OUTSIDE the lanes (a batch, a
    workflow's fan-out, a chat)."""
    try:
        from fichero_server.execution import jobs

        return getattr(jobs._current, "job_id", None) is not None
    except Exception:  # noqa: BLE001 -- never let the guard itself stop a call
        return False


async def _take_slot(provider: str | None) -> _Cap | None:
    if _inside_a_lane():
        return None
    key = provider or "unknown"
    # Waiting its turn costs no thread (a call stuck at a provider must not hold an executor thread for every waiter):
    # a check under the lock, then a short sleep on this call's own loop.
    while True:
        with _SLOTS_LOCK:
            cap = _cap_for(provider)
            if _IN_FLIGHT.get(key, 0) < cap.cap:
                _IN_FLIGHT[key] = _IN_FLIGHT.get(key, 0) + 1
                return cap
        await asyncio.sleep(0.05)


def _give_slot(provider: str | None, slot: _Cap | None) -> None:
    if slot is None:
        return
    with _SLOTS_LOCK:
        _IN_FLIGHT[provider or "unknown"] = max(0, _IN_FLIGHT.get(provider or "unknown", 0) - 1)


#: Why a provider cannot answer: it asked us to slow down, it has no credit, or it refused the key.
CAUSES = ("rate-limit", "quota", "key")


def _provider_name(provider: str) -> str:
    """How a provider is written to a person: the catalogue's own name (`llm/providers.py`), else the id capitalised."""
    from fichero_server.llm.providers import get_provider_info

    key = (provider or "").strip().lower()
    info = get_provider_info(key) if key else None
    return (info.name if info else None) or key.capitalize() or "The provider"


provider_display = _provider_name  # the name a person reads (`llm/failure.py`)


class ProviderRateLimitedError(RuntimeError):
    """A provider that cannot answer is failed fast, without calling it, so a long run does not burn the rest of its calls
    against it. The subclasses keep the CAUSE (`ai.where.dead-provider-says-why`, ## 950): this class is the rate limit
    (the provider asked us to slow down: waiting helps); `ProviderQuotaExhaustedError` (no credit: adding credit helps) and
    `ProviderKeyRefusedError` (the key was refused: checking it helps) are what a person with no credit or a bad key gets, in
    words that name the provider and the fix, never the breaker's internals. The class stays the one the callers catch."""

    cause = "rate-limit"

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
        super().__init__(self.words(provider))

    @classmethod
    def words(cls, provider: str) -> str:
        name = _provider_name(provider)
        return (f"{name} is asking us to slow down, so this step stopped for now. Run it again in a few minutes, "
                "or choose another model in Settings.")


class ProviderQuotaExhaustedError(ProviderRateLimitedError):
    """The provider has no credit left for this key (HTTP 402, insufficient_quota, a key limit)."""

    cause = "quota"

    @classmethod
    def words(cls, provider: str) -> str:
        name = _provider_name(provider)
        return f"{name} has no credit left for this key. Add credit at {name}, or choose another model in Settings."


class ProviderKeyRefusedError(ProviderRateLimitedError):
    """The provider refused the API key (HTTP 401, an invalid key)."""

    cause = "key"

    @classmethod
    def words(cls, provider: str) -> str:
        name = _provider_name(provider)
        return f"{name} refused the API key. Check the key in Settings › AI, or choose another model."


class ProviderInFlightBudgetError(ProviderRateLimitedError):
    """The provider kept answering that the key's credit does not fit the calls still in flight (OpenRouter 402
    `in_flight_budget_exhausted`, #6671) and the retries are spent. Not a dead provider: the run pauses with its Continue."""

    @classmethod
    def words(cls, provider: str) -> str:
        name = _provider_name(provider)
        return (f"{name} is limiting how many requests can be in flight for this key, so this step paused. "
                "Continue it in a few minutes, or add credit at " + name + ".")


class ProviderCreditStopError(ProviderQuotaExhaustedError):
    """The provider has no credit, or a key's or account's credit limit is reached (#6675), inside a run: the run is paused
    with the cause and its one prompt (Open provider page, Continue, Stop), no page is recorded failed."""

    @classmethod
    def words(cls, provider: str) -> str:
        name = _provider_name(provider)
        return f"{name} has no credit left, or its credit limit is reached, so the run paused. Continue it once that is fixed."


class ProviderKeyStopError(ProviderKeyRefusedError):
    """The provider refused the API key inside a run (#6675): the run is paused with `key-refused` and its Continue."""


#: The errors that mean "the run was asked to pause with a cause": its page is not a failed page, Continue reads it again.
RUN_PAUSING_ERRORS = (ProviderInFlightBudgetError, ProviderCreditStopError, ProviderKeyStopError)

CREDIT_LIMIT_WORDS = ("key limit", "credit limit", "limit exceeded", "limit reached", "spending limit", "spend limit")


def credit_cause(exc: BaseException) -> str:
    """`"credit-limit"` when the provider's words name a limit (a key's or an account's cap), else `"out-of-credit"`."""
    from fichero_server.llm import _extract_exc_message

    try:
        text = _extract_exc_message(exc).lower()
    except Exception:  # pragma: no cover - classification must never crash
        text = str(exc).lower()
    return "credit-limit" if any(k in text for k in CREDIT_LIMIT_WORDS) else "out-of-credit"


_BY_CAUSE: dict[str, type[ProviderRateLimitedError]] = {
    "rate-limit": ProviderRateLimitedError, "quota": ProviderQuotaExhaustedError, "key": ProviderKeyRefusedError}


def provider_stopped_error(provider: str, cause: str = "rate-limit", *, failures: int = 1,
                           detail: str | None = None) -> ProviderRateLimitedError:
    """The error for a provider that cannot answer, of the class that names its cause."""
    return _BY_CAUSE.get(cause, ProviderRateLimitedError)(provider, failures=failures, detail=detail)


#: The longest a provider's Retry-After is waited for: a provider asking for more is waited for this long, then tried again
#: (the retries are bounded, so a provider that keeps asking ends the call after `max_retries` of these waits).
RETRY_AFTER_CAP = 120.0


def retry_after_seconds(exc: BaseException) -> float | None:
    """The provider's own Retry-After (seconds), from the response headers or the exception, capped; None if it gave none."""
    value = getattr(exc, "retry_after", None)
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if value is None and headers is not None:
        try:
            value = headers.get("retry-after") or headers.get("Retry-After")
        except Exception:  # noqa: BLE001
            value = None
    try:
        seconds = float(value)  # an HTTP-date form is not honoured: the backoff covers it
    except (TypeError, ValueError):
        return None
    return min(max(seconds, 0.0), RETRY_AFTER_CAP)


#: The words of a provider that has no credit, and of one that refused the key (a refusal that reached us as text only, a
#: wrapper having dropped the status). ONE list for `classify_provider_error` and `fatal_cause`, so they cannot disagree.
NO_CREDIT_WORDS = ("insufficient_quota", "insufficient quota", "key limit", "credit balance", "out of credits")
KEY_REFUSED_WORDS = ("invalid api key", "invalid_api_key", "incorrect api key", "401 unauthorized", "invalid x-api-key",
                     "authentication_error")


IN_FLIGHT_BUDGET_REASON = "in_flight_budget_exhausted"


def is_in_flight_budget(exc: BaseException) -> bool:
    """An HTTP 402 whose reason is OpenRouter's `in_flight_budget_exhausted`; a 402 with no such reason is not."""
    from fichero_server.llm import _extract_exc_message, _extract_exc_status_code

    if _extract_exc_status_code(exc) != 402:
        return False
    try:
        return IN_FLIGHT_BUDGET_REASON in _extract_exc_message(exc).lower()
    except Exception:  # pragma: no cover - classification must never crash
        return IN_FLIGHT_BUDGET_REASON in str(exc).lower()


def classify_provider_error(exc: BaseException) -> str:
    """Classify a provider exception as ``"slow-down"``, ``"transient"``, ``"fatal"`` or ``"terminal"``
    (`ai.where.one-retry-policy`, #5944).

    * **slow-down**: 429 / rate-limit / too many requests. Wait (the provider's Retry-After, else backoff) and retry. NOT a
      breaker failure: a provider that said "slow down" is alive.
    * **transient**: 5xx, 408, 409, a timeout or a dropped connection. Back off and retry; not a breaker failure.
    * **fatal**: this provider will not answer for this run: no credit (402, ``insufficient_quota``, a key limit) or a
      refused key (401). Opens the breaker at once; no retry.
    * **terminal**: anything else (a bad request, a refusal, a bug, our own call budget running out). Raised at once.
    """
    from fichero_server.llm import _extract_exc_message, _extract_exc_status_code, _is_provider_quota_error

    status = _extract_exc_status_code(exc)
    try:
        text = _extract_exc_message(exc).lower()
    except Exception:  # pragma: no cover - classification must never crash
        text = str(exc).lower()
    if is_in_flight_budget(exc):
        return "slow-down"  # the credit fits fewer calls at once, not none: wait for the in-flight calls, never fatal
    if status in (401, 402) or any(k in text for k in (*NO_CREDIT_WORDS, *KEY_REFUSED_WORDS)):
        return "fatal"
    try:
        is_quota, _status, _detail = _is_provider_quota_error(exc)
    except Exception:  # pragma: no cover
        is_quota = False
    if status == 429 or is_quota:
        return "slow-down"
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return "terminal"  # OUR wall-clock budget for the call ran out: another try would spend the whole budget again
    name = type(exc).__name__.lower()
    if (status is not None and (status >= 500 or status in (408, 409))) or any(
            k in name for k in ("timeout", "connecterror", "connectionerror", "remoteprotocol", "readerror")):
        return "transient"
    return "terminal"


def fatal_cause(exc: BaseException) -> str:
    """For a `fatal` error (`classify_provider_error`): `"key"` when the provider refused the key (401 or its words), else
    `"quota"` (no credit: 402, insufficient_quota, a key limit)."""
    from fichero_server.llm import _extract_exc_message, _extract_exc_status_code

    status = _extract_exc_status_code(exc)
    try:
        text = _extract_exc_message(exc).lower()
    except Exception:  # pragma: no cover - classification must never crash
        text = str(exc).lower()
    if status == 401 or any(k in text for k in KEY_REFUSED_WORDS):
        return "key"
    return "quota"


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
    last_cause: str = "rate-limit"


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
            raise provider_stopped_error(
                provider or "unknown", st.last_cause,
                failures=st.consecutive_failures, detail=st.last_detail,
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
            st.last_cause = "rate-limit"
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

    async def trip(self, provider: str | None, *, detail: str | None = None, cause: str = "quota") -> None:
        """Open the breaker for ``provider`` now: it cannot answer this run (no credit, a refused key), and it keeps why."""
        key = self._key(provider)
        async with self._lock:
            st = self._states.setdefault(key, _ProviderState())
            st.consecutive_failures = max(st.consecutive_failures, self.threshold)
            st.last_detail = detail
            st.last_cause = cause
            if st.opened_at is None:
                st.opened_at = time.monotonic()
                logger.error("Circuit OPEN for provider %s: %s", provider or "unknown", detail or "it cannot answer")

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
        token = IN_RETRY_LAYER.set(True)  # the one layer: a call inside this one does not wrap itself again
        try:
            # One slot per provider across the whole engine: the send waits its turn, and lets go during a back-off.
            slot = await _take_slot(provider)
            try:
                result = await make_coro()
            finally:
                _give_slot(provider, slot)
        except Exception as exc:
            kind = classify_provider_error(exc)
            in_flight = kind == "slow-down" and is_in_flight_budget(exc)
            if in_flight:
                _slow_down_cap(provider)  # the next calls fit the key's credit: half as many at once
            if kind == "fatal":
                await breaker.trip(provider, detail=str(exc), cause=fatal_cause(exc))
                # No credit, a credit limit or a refused key (#6675, `failure.PAUSES`): the run pauses and asks; its page is
                # not a failed page.
                from fichero_server.llm.retry import _pause_the_run_for_credit

                if _pause_the_run_for_credit(provider or "unknown", exc):
                    stop = ProviderKeyStopError if fatal_cause(exc) == "key" else ProviderCreditStopError
                    raise stop(provider or "unknown", failures=attempt + 1, detail=str(exc)) from exc
                raise
            if kind == "terminal":
                raise
            # slow-down or transient: neither is a breaker failure (a provider that said "slow down" is alive); the
            # number of sends is bounded by max_retries alone.
            if attempt >= max_retries and in_flight:
                # Not a failure of the provider: the run pauses with the cause and its Continue (#6671).
                from fichero_server.llm.retry import _pause_the_run_for

                _pause_the_run_for(provider or "unknown", exc)
                raise ProviderInFlightBudgetError(provider or "unknown", failures=attempt + 1, detail=str(exc)) from exc
            if attempt >= max_retries:
                # Retries spent without an answer: THIS is the breaker's failure (K calls in a row that never got
                # through open it), not each 429 on the way.
                await breaker.record_failure(provider, detail=str(exc))
                await breaker.check(provider)
                raise
            delay = compute_backoff_delay(
                attempt, base=base_delay, cap=max_delay, jitter=jitter
            )
            asked = retry_after_seconds(exc)
            if asked is not None:
                delay = max(delay, asked)  # the provider's own Retry-After is a floor
            attempt += 1
            logger.warning(
                "Retryable %s error%s (provider=%s): backing "
                "off %.2fs before retry %d/%d (%s)",
                kind,
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
            _answered(provider)
            return result
        finally:
            IN_RETRY_LAYER.reset(token)
