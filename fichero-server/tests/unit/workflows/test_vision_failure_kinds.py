"""A failed vision call names WHAT failed, not a guess between four things.

Daniel, 2026-09-02: a paleography run reported "Vision LLM returned empty
response … after retry. Likely a provider safety refusal or sustained timeout;
no transcription artifact saved." One sentence covering a refusal, a timeout, a
rate limit and a genuinely empty answer — "likely … or …" is a guess printed as
a finding. An operator cannot act on it and the UI cannot group by it.

These tests pin the classification, the retry POLICY (only timeout-shaped
failures earn another attempt), and the honest-failure principle: naming a
failure never invents an artifact.
"""

from __future__ import annotations

import asyncio

import pytest

from fichero_server.workflows.circuit_breaker import ProviderRateLimitedError
from fichero_server.workflows.tools.vision_base import (
    VISION_ERROR_EMPTY,
    VISION_ERROR_RATE_LIMITED,
    VISION_ERROR_REFUSAL,
    VISION_ERROR_TIMEOUT,
    VISION_ERROR_UNKNOWN,
    classify_vision_failure,
    describe_vision_failure,
    is_retryable_vision_failure,
)


@pytest.mark.parametrize(
    "exc, expected",
    [
        (asyncio.TimeoutError(), VISION_ERROR_TIMEOUT),
        (TimeoutError(), VISION_ERROR_TIMEOUT),
        (RuntimeError("Read timed out after 120s"), VISION_ERROR_TIMEOUT),
        (RuntimeError("upstream deadline exceeded"), VISION_ERROR_TIMEOUT),
        (RuntimeError("Server disconnected without sending a response"),
         VISION_ERROR_TIMEOUT),
        (RuntimeError("finish_reason: safety"), VISION_ERROR_REFUSAL),
        (RuntimeError("PROHIBITED_CONTENT"), VISION_ERROR_REFUSAL),
        (RuntimeError("the model refused to answer"), VISION_ERROR_REFUSAL),
        (RuntimeError("blocked by content policy"), VISION_ERROR_REFUSAL),
        (RuntimeError("429 Too Many Requests"), VISION_ERROR_RATE_LIMITED),
        (RuntimeError("quota exceeded for this key"), VISION_ERROR_RATE_LIMITED),
        (RuntimeError("socket closed unexpectedly"), VISION_ERROR_UNKNOWN),
    ],
)
def test_each_failure_shape_gets_its_own_kind(exc, expected):
    assert classify_vision_failure(exc) == expected


def test_a_provider_rate_limit_error_is_named_by_TYPE_not_by_wording():
    """The breaker's own exception must classify even when its message says
    nothing recognisable."""
    assert (
        classify_vision_failure(ProviderRateLimitedError("openrouter", failures=5))
        == VISION_ERROR_RATE_LIMITED
    )


def test_no_exception_means_the_model_answered_with_nothing():
    """The model returned; the answer was empty. That is not a transport
    failure and must not be reported as one."""
    assert classify_vision_failure(None) == VISION_ERROR_EMPTY


def test_a_refusal_that_mentions_a_timeout_is_still_a_refusal():
    """Order matters — a refusal re-run costs tokens for the same answer."""
    kind = classify_vision_failure(
        RuntimeError("blocked by safety filter after the request timed out")
    )
    assert kind == VISION_ERROR_REFUSAL


def test_only_timeouts_earn_another_attempt():
    """A refusal repeats deterministically; a rate limit is the circuit
    breaker's job and hammering it holds the breaker open for every other
    file in the run."""
    assert is_retryable_vision_failure(VISION_ERROR_TIMEOUT)
    assert not is_retryable_vision_failure(VISION_ERROR_REFUSAL)
    assert not is_retryable_vision_failure(VISION_ERROR_RATE_LIMITED)
    assert not is_retryable_vision_failure(VISION_ERROR_EMPTY)
    assert not is_retryable_vision_failure(VISION_ERROR_UNKNOWN)


@pytest.mark.parametrize(
    "kind",
    [
        VISION_ERROR_REFUSAL,
        VISION_ERROR_TIMEOUT,
        VISION_ERROR_RATE_LIMITED,
        VISION_ERROR_EMPTY,
        VISION_ERROR_UNKNOWN,
    ],
)
def test_every_kind_has_its_own_operator_sentence(kind):
    sentence = describe_vision_failure(kind)
    assert sentence
    # The thing being replaced: one hedged sentence for four failures.
    assert "Likely a provider safety refusal or sustained timeout" not in sentence


def test_the_kinds_do_not_share_a_sentence():
    sentences = {
        describe_vision_failure(kind)
        for kind in (
            VISION_ERROR_REFUSAL,
            VISION_ERROR_TIMEOUT,
            VISION_ERROR_RATE_LIMITED,
            VISION_ERROR_EMPTY,
        )
    }
    assert len(sentences) == 4, "two failure kinds report the same sentence"


def test_the_detail_rides_along_when_there_is_one():
    sentence = describe_vision_failure(
        VISION_ERROR_TIMEOUT, detail="ReadTimeout: 120s"
    )
    assert "ReadTimeout: 120s" in sentence


def test_the_step_error_payload_carries_a_machine_readable_kind():
    """Pin the field name the UI groups per-model failure chips by."""
    import inspect

    from fichero_server.workflows.tools import vision_base

    source = inspect.getsource(vision_base.process_vision)
    assert '"error_kind": error_kind' in source, (
        "the empty-response failure payload no longer carries error_kind"
    )
    # Honest failure: the empty branch still saves nothing.
    assert '"text": "",' in source
