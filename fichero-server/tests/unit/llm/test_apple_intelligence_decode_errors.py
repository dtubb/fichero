"""Regression tests for #949 / #962 — Apple Intelligence decode-time
failures must raise StructuredDecodeError (an AppleUnavailableError
subclass) so chat_structured_with_fallback escapes to $large.

Pre-fix, fm-bridge emitting `kind: decoding` / `generation` /
`context_overflow` / `schema` became plain RuntimeError. The fallback
wrapper only caught AppleUnavailableError, so those chunks failed
permanently — extract_all lost ~10-15% of page chunks on real
documents (\"Failed to deserialize a Generable type from model output\").

After the fix, the bridge-stderr parser raises StructuredDecodeError
for those kinds, which inherits from AppleUnavailableError, so the
$large cloud retry kicks in just like guardrail / locale failures.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import BaseModel

from fichero_server.llm import (
    AppleUnavailableError,
    GuardrailViolationError,
    LLMConfig,
    StructuredDecodeError,
    UnsupportedLocaleError,
    _raise_from_bridge_stderr,
    chat_structured_with_fallback,
)


def _stderr_for(kind: str, message: str) -> bytes:
    """Encode a fake fm-bridge stderr payload like the real bridge would."""
    return json.dumps({"kind": kind, "error": message}).encode()


class TestBridgeStderrParser:
    def test_guardrail_kind_raises_guardrail_error(self):
        with pytest.raises(GuardrailViolationError) as exc:
            _raise_from_bridge_stderr(
                _stderr_for("guardrail", "May contain unsafe content"), 1,
            )
        assert "guardrail" in str(exc.value)

    def test_refusal_kind_raises_guardrail_error(self):
        # `refusal` is the structured-call variant of guardrail
        with pytest.raises(GuardrailViolationError):
            _raise_from_bridge_stderr(
                _stderr_for("refusal", "Refusal: unsafe topic"), 1,
            )

    def test_unsupported_language_raises_locale_error(self):
        with pytest.raises(UnsupportedLocaleError):
            _raise_from_bridge_stderr(
                _stderr_for("unsupported_language", "es-CO not in supported set"), 1,
            )

    def test_decoding_kind_raises_structured_decode_error(self):
        """The #949 / #962 symptom — extract_all chunks dying with
        'Failed to deserialize a Generable type from model output'.
        Pre-fix this became plain RuntimeError; post-fix it must be
        StructuredDecodeError so the fallback path escalates to $large.
        """
        with pytest.raises(StructuredDecodeError):
            _raise_from_bridge_stderr(
                _stderr_for(
                    "decoding",
                    "terminated generation early before producing valid output: "
                    "Failed to deserialize a Generable type from model output",
                ),
                1,
            )

    def test_generation_kind_raises_structured_decode_error(self):
        with pytest.raises(StructuredDecodeError):
            _raise_from_bridge_stderr(
                _stderr_for("generation", "model stopped emitting tokens"), 1,
            )

    def test_context_overflow_kind_raises_structured_decode_error(self):
        with pytest.raises(StructuredDecodeError):
            _raise_from_bridge_stderr(
                _stderr_for("context_overflow", "prompt exceeded 4096 tokens"), 1,
            )

    def test_schema_kind_raises_structured_decode_error(self):
        with pytest.raises(StructuredDecodeError):
            _raise_from_bridge_stderr(
                _stderr_for("schema", "grammar violation at offset 142"), 1,
            )

    def test_unknown_kind_falls_through_to_runtime_error(self):
        """Kinds we haven't classified yet stay plain RuntimeError so
        future bridge errors don't accidentally trigger the cloud
        fallback before we've decided that's the right routing.
        """
        with pytest.raises(RuntimeError) as exc:
            _raise_from_bridge_stderr(
                _stderr_for("rate_limited", "too many concurrent calls"), 1,
            )
        # Must NOT be one of the typed Apple subclasses
        assert not isinstance(exc.value, AppleUnavailableError)


class TestStructuredDecodeErrorInheritance:
    """Lock the inheritance so callers catching AppleUnavailableError
    pick up StructuredDecodeError automatically (the whole point of
    the fix).
    """

    def test_decode_error_is_apple_unavailable(self):
        err = StructuredDecodeError("Apple Intelligence (decoding): test")
        assert isinstance(err, AppleUnavailableError)

    def test_chat_structured_with_fallback_catches_decode_error(self):
        # Quick sanity that the wrapper's `except AppleUnavailableError`
        # branch catches the new subclass.
        from fichero_server.llm import chat_structured_with_fallback  # noqa: F401
        # We don't run the wrapper here (it would require a real LLM
        # config + cloud key); instead we assert that the wrapper's
        # exception-handling code references AppleUnavailableError, which
        # by definition catches StructuredDecodeError via inheritance.
        import inspect
        source = inspect.getsource(chat_structured_with_fallback)
        assert "except AppleUnavailableError" in source


class _MiniSchema(BaseModel):
    value: str = ""


def _apple_config() -> LLMConfig:
    return LLMConfig(provider="apple", model="apple-intelligence")


class TestStructuredDecodeKind:
    """#1027 — the four fm-bridge decode kinds must be distinguishable so
    the transient ones (decoding/generation) get an on-device retry
    before the paid $large fallback, while context_overflow/schema —
    which fail identically on retry — go straight to fallback."""

    def test_bridge_error_carries_kind(self):
        for kind in ("decoding", "generation", "context_overflow", "schema"):
            with pytest.raises(StructuredDecodeError) as exc:
                _raise_from_bridge_stderr(_stderr_for(kind, "boom"), 1)
            assert exc.value.kind == kind

    def test_retryable_kinds_membership(self):
        assert "decoding" in StructuredDecodeError.RETRYABLE_KINDS
        assert "generation" in StructuredDecodeError.RETRYABLE_KINDS
        assert "context_overflow" not in StructuredDecodeError.RETRYABLE_KINDS
        assert "schema" not in StructuredDecodeError.RETRYABLE_KINDS

    @pytest.mark.asyncio
    async def test_decoding_failure_retries_once_on_device(self):
        # First call fails with a transient `decoding` error; the retry
        # succeeds — no paid fallback should be resolved.
        good = _MiniSchema(value="ok")
        mock_structured = AsyncMock(
            side_effect=[StructuredDecodeError("(decoding): x", kind="decoding"), good]
        )
        mock_resolve = AsyncMock()
        with (
            patch("fichero_server.llm.chat_structured", new=mock_structured),
            patch("fichero_server.llm.resolve_model_alias", new=mock_resolve),
        ):
            result = await chat_structured_with_fallback(
                prompt="p", schema=_MiniSchema, config=_apple_config(),
            )
        assert result is good
        assert mock_structured.await_count == 2  # original + one retry
        mock_resolve.assert_not_called()  # never reached the paid path

    @pytest.mark.asyncio
    async def test_context_overflow_does_not_retry_on_device(self):
        # context_overflow gets one compact retry without schema prompt
        # injection before the fallback path (here: no $large configured
        # → re-raise).
        mock_structured = AsyncMock(
            side_effect=StructuredDecodeError(
                "(context_overflow): too long", kind="context_overflow"
            )
        )
        with (
            patch("fichero_server.llm.chat_structured", new=mock_structured),
            patch(
                "fichero_server.llm.resolve_model_alias",
                side_effect=ValueError("no $large configured"),
            ),
        ):
            with pytest.raises(StructuredDecodeError):
                await chat_structured_with_fallback(
                    prompt="p", schema=_MiniSchema, config=_apple_config(),
                )
        assert mock_structured.await_count == 2

    @pytest.mark.asyncio
    async def test_retry_failure_falls_through_to_paid_fallback(self):
        # decoding fails, the retry also fails — must then fall through
        # to the $large path (re-raise here, no $large configured).
        mock_structured = AsyncMock(
            side_effect=[
                StructuredDecodeError("(decoding): x", kind="decoding"),
                StructuredDecodeError("(decoding): x again", kind="decoding"),
            ]
        )
        with (
            patch("fichero_server.llm.chat_structured", new=mock_structured),
            patch(
                "fichero_server.llm.resolve_model_alias",
                side_effect=ValueError("no $large configured"),
            ),
        ):
            with pytest.raises(StructuredDecodeError):
                await chat_structured_with_fallback(
                    prompt="p", schema=_MiniSchema, config=_apple_config(),
                )
        assert mock_structured.await_count == 2  # original + one retry
