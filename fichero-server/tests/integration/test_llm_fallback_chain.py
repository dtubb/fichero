"""Integration tests for the LLM fallback chain (#873 — first scoped piece).

Exercises chat_with_fallback / chat_structured_with_fallback through their
real public interface: route Apple Intelligence's typed errors
(AppleUnavailableError subclasses — guardrail, locale) to the user's
configured $large model, fall through transient errors, surface
configuration errors as actionable.

Why integration-level: unit tests in test_chat_structured.py validate
the typed error branches in isolation. These tests validate the *full
chain*: bridge stderr JSON → _raise_from_bridge_stderr typed exception
→ AppleUnavailableError catch → resolve_model_alias → rebuild
LLMConfig → second chat() call → return. Mocked only at the network
boundary (subprocess + LangChain ainvoke); every other layer is real.

No internet calls — fm-bridge subprocess is mocked via
asyncio.create_subprocess_exec patching.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from fichero_server.llm import (
    AppleUnavailableError,
    LLMConfig,
    UnsupportedLocaleError,
    chat,
    chat_structured_with_fallback,
    chat_with_fallback,
    collect_usage,
)


class _Result(BaseModel):
    """Trivial schema so chat_structured has something to validate."""
    answer: str


def _fake_subprocess(stdout: bytes, stderr: bytes, returncode: int = 0):
    """Build an asyncio subprocess mock that mimics fm-bridge."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


def _bridge_unsupported_locale_err() -> bytes:
    """Stderr payload fm-bridge emits when Apple Intelligence rejects
    the prompt's locale (es-LatAm on a model that only ships es-ES, e.g.)."""
    import json
    return json.dumps({
        "kind": "unsupported_language",
        "error": "An unsupported language or locale was used",
    }).encode()


def _bridge_guardrail_err() -> bytes:
    """Stderr payload for safety filter refusal."""
    import json
    return json.dumps({
        "kind": "guardrail",
        "error": "Safety filter rejected prompt",
    }).encode()


def _bridge_decoding_err() -> bytes:
    """Stderr payload for transient decoding failure (NOT Apple-unavailable;
    chunked-retry territory, not fallback territory)."""
    import json
    return json.dumps({
        "kind": "decoding",
        "error": "Failed to deserialize Generable type",
    }).encode()


@pytest.fixture
def apple_cfg():
    return LLMConfig(provider="apple", model="apple-intelligence", timeout=10)


@pytest.fixture(autouse=True)
def fake_fm_bridge_path():
    """Make _apple_intelligence_chat / _structured see a 'binary' so they
    proceed to the subprocess call. is_file + executable bit checks pass."""
    with patch("pathlib.Path.is_file", return_value=True), \
         patch("pathlib.Path.stat") as st:
        st.return_value.st_mode = 0o755
        yield


# =============================================================================
# chat_with_fallback — full chain through the real plain-chat path
# =============================================================================


class TestChatWithFallbackChain:
    """End-to-end through the real chat_with_fallback function. Mocks
    only at asyncio.create_subprocess_exec (Apple) + get_langchain_model
    (cloud) — every layer in between (the typed error mapper, the
    AppleUnavailableError except clause, resolve_model_alias) is the
    production code path."""

    @pytest.mark.asyncio
    async def test_unsupported_locale_routes_to_large(self, apple_cfg):
        """Live bug from #868: Spanish-LatAm on macOS without es-MX
        support → bridge raises UnsupportedLocaleError → fallback runs."""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_unsupported_locale_err(), returncode=1,
        )
        cloud = MagicMock()
        cloud_response = MagicMock()
        cloud_response.content = "Spanish narrative from cloud"
        cloud_response.usage_metadata = None
        cloud.ainvoke = AsyncMock(return_value=cloud_response)

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.resolve_model_alias",
                   return_value=("anthropic", "claude-sonnet-4-6")), \
             patch("fichero_server.llm._paid_remote_fallbacks_enabled", return_value=True), \
             patch("fichero_server.llm.get_langchain_model", return_value=cloud):
            result = await chat_with_fallback(
                "hola, esto es un prompt en español",
                config=apple_cfg,
            )

        assert result == "Spanish narrative from cloud"
        cloud.ainvoke.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_guardrail_routes_to_large(self, apple_cfg):
        """Safety filter refusal → fallback runs (#838 path, regression
        guard after AppleUnavailableError refactor)."""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_guardrail_err(), returncode=1,
        )
        cloud = MagicMock()
        cloud_response = MagicMock()
        cloud_response.content = "completed via cloud"
        cloud_response.usage_metadata = None
        cloud.ainvoke = AsyncMock(return_value=cloud_response)

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.resolve_model_alias",
                   return_value=("openai", "gpt-5")), \
             patch("fichero_server.llm._paid_remote_fallbacks_enabled", return_value=True), \
             patch("fichero_server.llm.get_langchain_model", return_value=cloud):
            result = await chat_with_fallback("text", config=apple_cfg)

        assert result == "completed via cloud"

    @pytest.mark.asyncio
    async def test_guardrail_fallback_logs_loud_cost_warning(self, apple_cfg, caplog):
        """#1001: the silent swap to a paid cloud provider must be loud —
        WARNING level + explicit cost language so it isn't a billing
        surprise on every catalogue run."""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_guardrail_err(), returncode=1,
        )
        cloud = MagicMock()
        cloud_response = MagicMock()
        cloud_response.content = "ok"
        cloud_response.usage_metadata = None
        cloud.ainvoke = AsyncMock(return_value=cloud_response)

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.resolve_model_alias",
                   return_value=("openai", "gpt-5")), \
             patch("fichero_server.llm._paid_remote_fallbacks_enabled", return_value=True), \
             patch("fichero_server.llm.get_langchain_model", return_value=cloud), \
             caplog.at_level(logging.WARNING, logger="fichero_server.llm"):
            await chat_with_fallback("text", config=apple_cfg)

        fallback_warnings = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING and "PAID" in r.message
        ]
        assert fallback_warnings, (
            "expected a loud WARNING-level cost notice, got: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )
        assert "incurs cost" in fallback_warnings[0].message

    @pytest.mark.asyncio
    async def test_local_builtin_fallback_not_labeled_paid(self, apple_cfg, caplog):
        """#1560: when the $large fallback resolves to an on-device /
        builtin provider (e.g. Apple Intelligence or a local omlx/ollama
        server — all free), the cost note must NOT claim it is PAID or
        that it incurs cost. Mislabeling free local inference as paid is a
        false billing scare on every catalogue run."""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_guardrail_err(), returncode=1,
        )
        cloud = MagicMock()
        cloud_response = MagicMock()
        cloud_response.content = "ok"
        cloud_response.usage_metadata = None
        cloud.ainvoke = AsyncMock(return_value=cloud_response)

        # $large resolves to a LOCAL provider — free, on-device.
        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.resolve_model_alias",
                   return_value=("ollama", "llama3.1")), \
             patch("fichero_server.llm.get_langchain_model", return_value=cloud), \
             caplog.at_level(logging.WARNING, logger="fichero_server.llm"):
            await chat_with_fallback("text", config=apple_cfg)

        msgs = [r.message for r in caplog.records]
        assert not any("PAID" in m or "incurs cost" in m for m in msgs), (
            f"local fallback wrongly labeled PAID: {msgs}"
        )
        assert any("no API cost" in m for m in msgs), (
            f"expected a free/on-device cost note, got: {msgs}"
        )

    @pytest.mark.asyncio
    async def test_decoding_error_routes_to_large(self, apple_cfg):
        """Grammar-decode failures ARE fallback-eligible since #949/#962:
        StructuredDecodeError is an AppleUnavailableError subclass so the
        chunk escapes to $large instead of being lost. (Pre-#962 these were
        plain RuntimeError and skipped the fallback — extract_all dropped
        ~10% of chunks. This test guards the corrected contract.)"""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_decoding_err(), returncode=1,
        )
        cloud = MagicMock()
        cloud_response = MagicMock()
        cloud_response.content = "completed via cloud"
        cloud_response.usage_metadata = None
        cloud.ainvoke = AsyncMock(return_value=cloud_response)

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.resolve_model_alias",
                   return_value=("openai", "gpt-5")), \
             patch("fichero_server.llm._paid_remote_fallbacks_enabled", return_value=True), \
             patch("fichero_server.llm.get_langchain_model", return_value=cloud):
            result = await chat_with_fallback("text", config=apple_cfg)

        assert result == "completed via cloud"

    @pytest.mark.asyncio
    async def test_no_large_configured_surfaces_original(self, apple_cfg):
        """When $large isn't configured, the original AppleUnavailableError
        surfaces — caller knows it was Apple's refusal, not a missing key."""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_unsupported_locale_err(), returncode=1,
        )

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.resolve_model_alias",
                   side_effect=ValueError("no $large configured")):
            with pytest.raises(UnsupportedLocaleError, match="unsupported_language"):
                await chat_with_fallback("text", config=apple_cfg)

    @pytest.mark.asyncio
    async def test_fallback_logs_usage_on_cloud_call(self, apple_cfg):
        """The cloud retry's usage_metadata flows through the
        collect_usage() bucket — proves cost-tracking spans the
        fallback boundary cleanly."""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_guardrail_err(), returncode=1,
        )
        cloud = MagicMock()
        cloud_response = MagicMock()
        cloud_response.content = "ok"
        cloud_response.usage_metadata = {
            "input_tokens": 100, "output_tokens": 30, "total_tokens": 130,
        }
        cloud.ainvoke = AsyncMock(return_value=cloud_response)

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.resolve_model_alias",
                   return_value=("openai", "gpt-5")), \
             patch("fichero_server.llm._paid_remote_fallbacks_enabled", return_value=True), \
             patch("fichero_server.llm.get_langchain_model", return_value=cloud):
            with collect_usage() as bucket:
                await chat_with_fallback("text", config=apple_cfg)

        # Bucket should contain the cloud call's usage. The Apple
        # subprocess errored before _log_apple_usage_estimate fired,
        # so we expect exactly one entry — the cloud retry.
        assert len(bucket) == 1
        assert bucket[0]["provider"] == "openai"
        assert bucket[0]["input_tokens"] == 100


# =============================================================================
# chat_structured_with_fallback — full chain through the structured path
# =============================================================================


class TestChatStructuredWithFallbackChain:
    """Same end-to-end shape, but for the structured-output path.
    Mocks subprocess + with_structured_output wrapper."""

    @pytest.mark.asyncio
    async def test_unsupported_locale_routes_to_large(self, apple_cfg):
        """extract_all hitting es-LatAm on Apple should silently route
        to $large + return a parsed Pydantic instance — the live bug
        we shipped #868 for."""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_unsupported_locale_err(), returncode=1,
        )
        # Cloud path returns the include_raw=True dict shape.
        cloud_raw = MagicMock(usage_metadata=None)
        cloud_invoke_result = {
            "raw": cloud_raw,
            "parsed": _Result(answer="from-cloud"),
            "parsing_error": None,
        }
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(return_value=cloud_invoke_result)
        base_model = MagicMock()
        base_model.profile = {"structured_output": True}
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.resolve_model_alias",
                   return_value=("anthropic", "claude-sonnet-4-6")), \
             patch("fichero_server.llm.get_langchain_model", return_value=base_model), \
             patch("fichero_server.llm._paid_remote_fallbacks_enabled", return_value=True):
            result = await chat_structured_with_fallback(
                prompt="extract entities from this text",
                schema=_Result,
                config=apple_cfg,
            )

        assert result == _Result(answer="from-cloud")

    @pytest.mark.asyncio
    async def test_guardrail_routes_to_large_structured(self, apple_cfg):
        """Same chain for safety refusal."""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_guardrail_err(), returncode=1,
        )
        cloud_raw = MagicMock(usage_metadata=None)
        cloud_invoke_result = {
            "raw": cloud_raw,
            "parsed": _Result(answer="safe-version"),
            "parsing_error": None,
        }
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(return_value=cloud_invoke_result)
        base_model = MagicMock()
        base_model.profile = {"structured_output": True}
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.resolve_model_alias",
                   return_value=("openai", "gpt-5")), \
             patch("fichero_server.llm.get_langchain_model", return_value=base_model), \
             patch("fichero_server.llm._paid_remote_fallbacks_enabled", return_value=True):
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=apple_cfg,
            )

        assert isinstance(result, _Result)

    @pytest.mark.asyncio
    async def test_decoding_error_routes_to_large_structured(self, apple_cfg):
        """Grammar-decode failures route through $large on the structured
        path too (#949/#962). StructuredDecodeError is an
        AppleUnavailableError subclass precisely so extract_all's chunks
        escape to the cloud model instead of being silently dropped."""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_decoding_err(), returncode=1,
        )
        cloud_raw = MagicMock(usage_metadata=None)
        cloud_invoke_result = {
            "raw": cloud_raw,
            "parsed": _Result(answer="recovered via cloud"),
            "parsing_error": None,
        }
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(return_value=cloud_invoke_result)
        base_model = MagicMock()
        base_model.profile = {"structured_output": True}
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.resolve_model_alias",
                   return_value=("anthropic", "claude-sonnet-4-6")), \
             patch("fichero_server.llm.get_langchain_model", return_value=base_model), \
             patch("fichero_server.llm._paid_remote_fallbacks_enabled", return_value=True):
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=apple_cfg,
            )

        assert result == _Result(answer="recovered via cloud")

    @pytest.mark.asyncio
    async def test_apple_success_path_returns_parsed(self, apple_cfg):
        """When Apple Intelligence succeeds (no error, valid JSON),
        chat_structured_with_fallback returns the parsed Pydantic
        instance directly — no fallback triggered."""
        import json
        bridge_payload = {
            "response_json": json.dumps({"answer": "from-apple"}),
            "model": "apple-intelligence",
        }
        proc = _fake_subprocess(
            stdout=json.dumps(bridge_payload).encode(),
            stderr=b"",
            returncode=0,
        )

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)):
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=apple_cfg,
            )

        assert result == _Result(answer="from-apple")


# =============================================================================
# Hierarchy correctness across the full stack
# =============================================================================


class TestErrorHierarchyEndToEnd:
    """Confirms the AppleUnavailableError base catches both subclasses
    in real call chains — the architectural promise of #868."""

    @pytest.mark.asyncio
    async def test_base_catches_both_subclasses(self, apple_cfg):
        """A generic except-AppleUnavailableError handler outside the
        wrappers should catch both guardrail + locale errors equally —
        proves the hierarchy works at the public-API boundary."""
        for stderr_payload in [_bridge_guardrail_err(),
                               _bridge_unsupported_locale_err()]:
            proc = _fake_subprocess(
                stdout=b"", stderr=stderr_payload, returncode=1,
            )
            with patch("asyncio.create_subprocess_exec",
                       new=AsyncMock(return_value=proc)):
                with pytest.raises(AppleUnavailableError):
                    await chat("x", config=apple_cfg)
