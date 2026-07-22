"""Coverage for the previously-untested surface of ``provider_validation``:
the runtime error classifier (``_parse_provider_error``), the call wrapper
(``wrap_provider_call`` / ``ProviderCallError``), and a regression for
whitespace-corrupted API keys (internal tab / carriage return).

The existing ``test_provider_validation.py`` covers key-format, api-base, and
``validate_provider_config`` — this file is disjoint from it, focusing on the
error-handling half of the module (pure logic; ``wrap_provider_call`` driven
with a stub coroutine, no network).
"""

from __future__ import annotations

import pytest

from fichero.llm.provider_validation import (
    ProviderCallError,
    ProviderValidationError,
    _parse_provider_error,
    _validate_api_key_format,
    wrap_provider_call,
)


# ===========================================================================
# Regression: internal whitespace in API keys must be rejected at save time
# ===========================================================================


def test_key_internal_tab_rejected():
    # Regression for the fixed gap: an embedded TAB used to slip through the
    # ' '/'\n'-only check and fail confusingly later at call time.
    with pytest.raises(ProviderValidationError, match="whitespace"):
        _validate_api_key_format("groq", "abc\tdef")


def test_key_internal_carriage_return_rejected():
    with pytest.raises(ProviderValidationError, match="whitespace"):
        _validate_api_key_format("groq", "abc\rdef")


def test_clean_key_still_passes():
    # The broadened check must not create false positives for real keys.
    _validate_api_key_format("groq", "gsk_ABCdef0123456789")  # no raise


# ===========================================================================
# _parse_provider_error — classification buckets (pure)
# ===========================================================================


def test_error_auth_bucket():
    for raw in ["HTTP 401 Unauthorized", "invalid_api_key supplied", "unauthorized"]:
        msg = _parse_provider_error("openai", raw)
        assert "Invalid API key" in msg
        assert "openai" in msg


def test_error_rate_limit_bucket():
    msg = _parse_provider_error("openai", "429 rate_limit reached")
    assert "rate limit exceeded" in msg


def test_error_connection_bucket():
    for raw in ["connection refused", "request timeout", "host unreachable", "network down"]:
        assert "Cannot connect" in _parse_provider_error("groq", raw)


def test_error_server_5xx_bucket():
    # Note: connection keywords ('timeout', 'unreachable', ...) are checked
    # BEFORE the 5xx bucket, so these strings deliberately avoid them.
    for raw in ["500 internal error", "502 bad gateway", "503 service down"]:
        assert "server error" in _parse_provider_error("openai", raw)


def test_error_model_not_found_bucket():
    assert "Model not available" in _parse_provider_error("openai", "The model does not exist")
    assert "Model not available" in _parse_provider_error("openai", "404 not found")


def test_error_quota_bucket():
    assert "quota" in _parse_provider_error("openai", "quota exceeded for the month")


def test_error_generic_fallback():
    msg = _parse_provider_error("openai", "wibble wobble unexpected")
    assert "call failed" in msg
    assert "openai" in msg


def test_error_lowercases_provider_label():
    # Provider name is normalised to lowercase in the returned message.
    msg = _parse_provider_error("OpenAI", "boom")
    assert "openai call failed" in msg


def test_error_truncates_long_original():
    long = "z" * 400
    msg = _parse_provider_error("openai", "401 " + long)
    # Buckets slice the original error to ~100 chars, so the full 400 never
    # leaks into the surfaced message.
    assert long not in msg
    assert len(msg) < 300


# ===========================================================================
# wrap_provider_call — success + failure wrapping (sync -> asyncio.run path)
# ===========================================================================


def test_wrap_success_returns_value():
    async def ok(a, b):
        return a * b

    assert wrap_provider_call("openai", "gpt", ok, 6, 7) == 42


def test_wrap_failure_becomes_provider_call_error():
    async def boom():
        raise RuntimeError("HTTP 401 unauthorized")

    with pytest.raises(ProviderCallError) as exc:
        wrap_provider_call("openai", "gpt-4", boom)
    err = exc.value
    assert err.provider == "openai"
    assert err.model == "gpt-4"
    assert isinstance(err.original_error, RuntimeError)
    # Message is the classified, user-facing form.
    assert "Invalid API key" in str(err)


def test_wrap_preserves_kwargs():
    async def echo(*, name):
        return name

    assert wrap_provider_call("groq", "m", echo, name="hi") == "hi"
