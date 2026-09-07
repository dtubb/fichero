"""Integration tests: Apple-unavailable failures propagate LOUD through the
real chat_with_fallback / chat_structured_with_fallback chain — no ladder.

The tier fallback ladder (Apple-unavailable → $medium → $large) was removed on
Daniel's ruling (2026-09-07): "get rid of fallback ladders, fail loudly." These
tests validate the full chain — fm-bridge stderr JSON → typed exception →
AppleUnavailableError → propagate — mocked only at the network boundary
(subprocess + LangChain). A cloud model is patched in ONLY to assert it is
NEVER dialled: the selected model runs, and its failure surfaces with the
specific cause. The one same-model behaviour that stays (Ruling A) is the
structured decode retry — same Apple model, one re-roll, then loud.

No internet calls — the fm-bridge subprocess is mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from fichero_server.llm import (
    AppleUnavailableError,
    GuardrailViolationError,
    LLMConfig,
    StructuredDecodeError,
    UnsupportedLocaleError,
    chat,
    chat_structured_with_fallback,
    chat_with_fallback,
)


class _Result(BaseModel):
    answer: str


def _fake_subprocess(stdout: bytes, stderr: bytes, returncode: int = 0):
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


def _bridge_unsupported_locale_err() -> bytes:
    import json
    return json.dumps({
        "kind": "unsupported_language",
        "error": "An unsupported language or locale was used",
    }).encode()


def _bridge_guardrail_err() -> bytes:
    import json
    return json.dumps({
        "kind": "guardrail",
        "error": "Safety filter rejected prompt",
    }).encode()


def _bridge_decoding_err() -> bytes:
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
    with patch("pathlib.Path.is_file", return_value=True), \
         patch("pathlib.Path.stat") as st:
        st.return_value.st_mode = 0o755
        yield


# =============================================================================
# chat_with_fallback — the selected model runs, failures propagate loud
# =============================================================================


class TestChatWithFallbackChain:
    @pytest.mark.asyncio
    async def test_unsupported_locale_raises_loud_and_never_dials_cloud(self, apple_cfg):
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_unsupported_locale_err(), returncode=1,
        )
        cloud = MagicMock()
        cloud.ainvoke = AsyncMock()

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.get_langchain_model", return_value=cloud) as glm:
            with pytest.raises(UnsupportedLocaleError, match="unsupported_language"):
                await chat_with_fallback("hola, prompt en español", config=apple_cfg)

        glm.assert_not_called()
        cloud.ainvoke.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_guardrail_raises_loud_and_never_dials_cloud(self, apple_cfg):
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_guardrail_err(), returncode=1,
        )
        cloud = MagicMock()
        cloud.ainvoke = AsyncMock()

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.get_langchain_model", return_value=cloud) as glm:
            with pytest.raises(AppleUnavailableError):
                await chat_with_fallback("text", config=apple_cfg)

        glm.assert_not_called()
        cloud.ainvoke.assert_not_awaited()


# =============================================================================
# chat_structured_with_fallback — loud raise; same-model decode retry (Ruling A)
# =============================================================================


class TestChatStructuredWithFallbackChain:
    @pytest.mark.asyncio
    async def test_guardrail_raises_loud_and_never_dials_cloud(self, apple_cfg):
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_guardrail_err(), returncode=1,
        )
        base_model = MagicMock()

        with patch("asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)), \
             patch("fichero_server.llm.get_langchain_model",
                   return_value=base_model) as glm:
            with pytest.raises(AppleUnavailableError):
                await chat_structured_with_fallback(
                    prompt="x", schema=_Result, config=apple_cfg,
                )

        glm.assert_not_called()

    @pytest.mark.asyncio
    async def test_decoding_error_retries_same_apple_then_raises_loud(self, apple_cfg):
        """A `decoding` kind is retryable (Ruling A) — retried ONCE on the SAME
        Apple model. The bridge keeps failing, so it raises loud, and no cloud
        model is ever built."""
        proc = _fake_subprocess(
            stdout=b"", stderr=_bridge_decoding_err(), returncode=1,
        )
        exec_mock = AsyncMock(return_value=proc)
        base_model = MagicMock()

        with patch("asyncio.create_subprocess_exec", new=exec_mock), \
             patch("fichero_server.llm.get_langchain_model",
                   return_value=base_model) as glm:
            with pytest.raises(StructuredDecodeError):
                await chat_structured_with_fallback(
                    prompt="x", schema=_Result, config=apple_cfg,
                )

        # Two Apple subprocess attempts (initial + one same-model retry); the
        # cloud model is never built.
        assert exec_mock.await_count == 2
        glm.assert_not_called()

    @pytest.mark.asyncio
    async def test_apple_success_path_returns_parsed(self, apple_cfg):
        """When Apple Intelligence succeeds, the parsed instance is returned
        directly — no retry, no substitution."""
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
    """The AppleUnavailableError base still catches both subclasses in real call
    chains — the architectural promise of #868, independent of the ladder."""

    @pytest.mark.asyncio
    async def test_base_catches_both_subclasses(self, apple_cfg):
        for stderr_payload in [_bridge_guardrail_err(),
                               _bridge_unsupported_locale_err()]:
            proc = _fake_subprocess(
                stdout=b"", stderr=stderr_payload, returncode=1,
            )
            with patch("asyncio.create_subprocess_exec",
                       new=AsyncMock(return_value=proc)):
                with pytest.raises(AppleUnavailableError):
                    await chat("x", config=apple_cfg)
