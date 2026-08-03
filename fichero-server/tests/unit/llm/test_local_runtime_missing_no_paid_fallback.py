"""A missing on-device runtime must not become a paid cloud call (#4502).

`LocalModelRuntimeMissingError` subclasses `AppleUnavailableError`, which is
exactly what `chat_with_fallback` / `chat_structured_with_fallback` catch to
walk the tier chain — paid tiers included. So at the catch site "the MLX
runtime is not installed" was indistinguishable from "Apple's guardrail refused
this prompt", and the chain proceeded with a `logger.warning`.

Those two failures deserve opposite answers:

- **Guardrail / unsupported locale** — Apple cannot serve this CONTENT. Nothing
  the user installs changes that, and escaping to a frontier model is the
  documented intent: academic text trips a consumer safety filter.
- **Runtime missing** — someone chose MLX, and the reasons to choose MLX are
  free, on-device, private. Answering "your runtime is not installed" with a
  paid cloud call bills them AND ships the data off-device: it substitutes the
  exact thing they rejected. It is a provisioning problem with a fix.

The default posture was already safe (paid fallbacks default OFF), so this only
ever bit the user who enabled them and later assumed local meant local.
**Neither direction was tested.** That is what this file is for.

Nothing here makes a network call: the primary always raises, and any fallback
attempt is recorded by a stub instead of dialled.
"""

from __future__ import annotations

import pytest

from fichero_server.llm import (
    AppleUnavailableError,
    GuardrailViolationError,
    LLMConfig,
    LocalModelHardwareError,
    LocalModelRuntimeMissingError,
    chat_with_fallback,
)


# Real provider identifiers, checked against the registry rather than invented.
# The managed MLX provider is `omlx` (is_local=True); "mlx" is not a registered
# provider at all, and an unregistered name resolves as NON-local — so a test
# written against it would have asserted the wrong thing in the safe direction
# and looked fine.
LOCAL = LLMConfig(provider="omlx", model="some-local-model")
PAID_TIER = ("openrouter", "google/gemini-3-flash-preview")
LOCAL_TIER = ("ollama", "llama3")


@pytest.fixture
def calls(monkeypatch):
    """Record every provider `chat` is asked to dial; never dial anything."""
    seen: list[tuple[str, str]] = []

    async def _chat(prompt, config, system=None, permissive_guardrails=False, **kw):
        seen.append((config.provider, config.model))
        if config.provider == LOCAL.provider and config.model == LOCAL.model:
            raise _chat.primary_error
        return f"response from {config.provider}"

    _chat.primary_error = LocalModelRuntimeMissingError("runtime not provisioned")
    monkeypatch.setattr("fichero_server.llm.chat", _chat)
    return seen, _chat


@pytest.fixture
def paid_fallbacks_on(monkeypatch):
    """The configuration where this bites: the user turned paid fallbacks ON."""
    monkeypatch.setenv("FICHERO_ALLOW_PAID_AI_FALLBACKS", "1")
    monkeypatch.delenv("FICHERO_LOCAL_ONLY", raising=False)


def _offer_tier(monkeypatch, provider, model):
    """Make the fallback chain offer exactly one tier."""
    monkeypatch.setattr("fichero_server.llm._fallback_tier_order", lambda: ["large"])
    monkeypatch.setattr(
        "fichero_server.llm._build_fallback_config",
        lambda config, tier: LLMConfig(provider=provider, model=model),
    )


class TestAMissingRuntimeDoesNotBecomeABilledCall:
    """The transition that was untested in either direction."""

    @pytest.mark.asyncio
    async def test_no_paid_call_is_made_when_the_local_runtime_is_missing(
        self, calls, paid_fallbacks_on, monkeypatch
    ):
        seen, _chat = calls
        _offer_tier(monkeypatch, *PAID_TIER)

        with pytest.raises(LocalModelRuntimeMissingError):
            await chat_with_fallback("hello", LOCAL)

        assert PAID_TIER not in seen, (
            "a missing on-device runtime reached a PAID provider. Someone chose "
            "MLX for free/private/on-device; billing them for it substitutes the "
            "thing they rejected"
        )
        assert seen == [(LOCAL.provider, LOCAL.model)]

    @pytest.mark.asyncio
    async def test_the_original_error_is_raised_not_swallowed(
        self, calls, paid_fallbacks_on, monkeypatch
    ):
        """Prefer raising over substituting. The user needs to hear "install the
        runtime", which is actionable; a silent cloud answer hides the fix."""
        _offer_tier(monkeypatch, *PAID_TIER)

        with pytest.raises(LocalModelRuntimeMissingError) as caught:
            await chat_with_fallback("hello", LOCAL)
        assert "runtime not provisioned" in str(caught.value)

    @pytest.mark.asyncio
    async def test_hardware_failure_is_treated_the_same_way(
        self, calls, paid_fallbacks_on, monkeypatch
    ):
        """"This hardware cannot run it" is the same class of answer as "it is
        not installed": local, fixable-or-not by the user, and not a licence to
        start charging them."""
        seen, _chat = calls
        _chat.primary_error = LocalModelHardwareError("unsupported hardware")
        _offer_tier(monkeypatch, *PAID_TIER)

        with pytest.raises(LocalModelHardwareError):
            await chat_with_fallback("hello", LOCAL)
        assert PAID_TIER not in seen

    @pytest.mark.asyncio
    async def test_a_LOCAL_fallback_is_still_allowed(
        self, calls, paid_fallbacks_on, monkeypatch
    ):
        """The fix must not become "never fall back". Falling to another
        on-device tier keeps every property MLX was chosen for, so it is the
        one escalation that is not a substitution."""
        seen, _chat = calls
        _offer_tier(monkeypatch, *LOCAL_TIER)

        result = await chat_with_fallback("hello", LOCAL)

        assert result == "response from ollama"
        assert LOCAL_TIER in seen


class TestTheGuardrailPathIsUnchanged:
    """The fix must not break the fallback that IS intended.

    Apple's filter refusing scholarly text is a content failure, not a
    provisioning one — escaping to a frontier model is the documented design
    (#838). If this ever fails, #4502 has over-corrected into a regression.
    """

    @pytest.mark.asyncio
    async def test_a_guardrail_violation_still_falls_back_to_paid(
        self, calls, paid_fallbacks_on, monkeypatch
    ):
        seen, _chat = calls
        _chat.primary_error = GuardrailViolationError("safety filter refused")
        _offer_tier(monkeypatch, *PAID_TIER)

        result = await chat_with_fallback("hello", LOCAL)

        assert result.startswith("response from openrouter")
        assert PAID_TIER in seen

    @pytest.mark.asyncio
    async def test_a_generic_apple_failure_still_falls_back_to_paid(
        self, calls, paid_fallbacks_on, monkeypatch
    ):
        seen, _chat = calls
        _chat.primary_error = AppleUnavailableError("unsupported locale")
        _offer_tier(monkeypatch, *PAID_TIER)

        await chat_with_fallback("hello", LOCAL)
        assert PAID_TIER in seen


class TestTheDefaultPostureStaysSafe:
    @pytest.mark.asyncio
    async def test_paid_fallbacks_off_blocks_paid_for_any_cause(
        self, calls, monkeypatch
    ):
        """Belt and braces: with the flag off, even a guardrail violation must
        not reach a paid tier. Pinned because the #4502 fix touches the same
        function, and a regression here would be invisible."""
        seen, _chat = calls
        _chat.primary_error = GuardrailViolationError("safety filter refused")
        monkeypatch.setenv("FICHERO_ALLOW_PAID_AI_FALLBACKS", "0")
        _offer_tier(monkeypatch, *PAID_TIER)

        with pytest.raises(GuardrailViolationError):
            await chat_with_fallback("hello", LOCAL)
        assert PAID_TIER not in seen


class TestThePredicateItself:
    def test_runtime_missing_is_recognised(self):
        from fichero_server.llm import _local_runtime_missing

        assert _local_runtime_missing(LocalModelRuntimeMissingError("x")) is True
        assert _local_runtime_missing(LocalModelHardwareError("x")) is True

    def test_a_content_failure_is_not(self):
        from fichero_server.llm import _local_runtime_missing

        assert _local_runtime_missing(GuardrailViolationError("x")) is False
        assert _local_runtime_missing(AppleUnavailableError("x")) is False
        assert _local_runtime_missing(None) is False
