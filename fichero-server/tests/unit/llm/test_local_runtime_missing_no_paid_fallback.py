"""A missing on-device runtime — and every other Apple-unavailable cause —
now FAILS LOUD, never a silent switch to a different or paid model.

Originally (#4502) this file guarded a nuanced rule inside the tier ladder: a
missing MLX runtime must not escalate to a PAID tier even when paid fallbacks
were enabled, while a guardrail refusal still could. Daniel's 2026-09-07 ruling
removed the ladder wholesale ("get rid of fallback ladders, fail loudly"), so
the nuance collapses into one rule: `chat_with_fallback` calls the SELECTED
model once and any failure — runtime missing, hardware, guardrail, locale —
propagates with its specific cause. No second attempt, no different model, no
local-runtime swap the user did not pick.

Nothing here makes a network call: the stubbed `chat` records the one provider
it is asked to dial and raises.
"""

from __future__ import annotations

import pytest

from fichero_server.llm import (
    AppleUnavailableError,
    GuardrailViolationError,
    LLMConfig,
    LocalModelHardwareError,
    LocalModelRuntimeMissingError,
    UnsupportedLocaleError,
    chat_with_fallback,
)


# The managed MLX provider is `omlx` (is_local=True) — a real registry id.
LOCAL = LLMConfig(provider="omlx", model="some-local-model")


@pytest.fixture
def calls(monkeypatch):
    """Record every provider `chat` is asked to dial; never dial anything."""
    seen: list[tuple[str, str]] = []

    async def _chat(prompt, config, system=None, permissive_guardrails=False, **kw):
        seen.append((config.provider, config.model))
        raise _chat.primary_error

    _chat.primary_error = LocalModelRuntimeMissingError("runtime not provisioned")
    monkeypatch.setattr("fichero_server.llm.chat", _chat)
    return seen, _chat


class TestEveryFailureIsLoudAndCallsOneModel:
    @pytest.mark.asyncio
    async def test_missing_local_runtime_raises_and_never_bills(self, calls):
        seen, _chat = calls
        with pytest.raises(LocalModelRuntimeMissingError, match="runtime not provisioned"):
            await chat_with_fallback("hello", LOCAL)
        # Exactly one call, to the selected model — no fallback of any kind.
        assert seen == [(LOCAL.provider, LOCAL.model)]

    @pytest.mark.asyncio
    async def test_hardware_failure_raises_loud(self, calls):
        seen, _chat = calls
        _chat.primary_error = LocalModelHardwareError("unsupported hardware")
        with pytest.raises(LocalModelHardwareError):
            await chat_with_fallback("hello", LOCAL)
        assert seen == [(LOCAL.provider, LOCAL.model)]

    @pytest.mark.asyncio
    async def test_guardrail_violation_raises_loud_not_a_substitution(self, calls):
        """The old ladder escaped a guardrail refusal to a paid model. That
        silent substitution is gone: it now raises loud, one call only."""
        seen, _chat = calls
        _chat.primary_error = GuardrailViolationError("safety filter refused")
        with pytest.raises(GuardrailViolationError):
            await chat_with_fallback("hello", LOCAL)
        assert seen == [(LOCAL.provider, LOCAL.model)]

    @pytest.mark.asyncio
    async def test_unsupported_locale_raises_loud(self, calls):
        seen, _chat = calls
        _chat.primary_error = UnsupportedLocaleError("unsupported locale")
        with pytest.raises(UnsupportedLocaleError):
            await chat_with_fallback("hello", LOCAL)
        assert seen == [(LOCAL.provider, LOCAL.model)]


class TestThePredicateItself:
    """`_local_runtime_missing` is retained (used by model_comparison) even
    though the ladder that consulted it is gone."""

    def test_runtime_missing_is_recognised(self):
        from fichero_server.llm import _local_runtime_missing

        assert _local_runtime_missing(LocalModelRuntimeMissingError("x")) is True
        assert _local_runtime_missing(LocalModelHardwareError("x")) is True

    def test_a_content_failure_is_not(self):
        from fichero_server.llm import _local_runtime_missing

        assert _local_runtime_missing(GuardrailViolationError("x")) is False
        assert _local_runtime_missing(AppleUnavailableError("x")) is False
        assert _local_runtime_missing(None) is False
