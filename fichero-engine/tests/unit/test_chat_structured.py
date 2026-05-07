"""Unit tests for chat_structured / chat_structured_with_fallback and the
Pydantic→Apple schema converter (#847).

Covers:
- _pydantic_to_apple_schema: nested objects, arrays, optional fields,
  $ref / $defs resolution, anyOf-with-null Optional handling.
- chat_structured provider dispatch: Apple → fm-bridge subprocess (mocked),
  LangChain → with_structured_output (mocked).
- chat_structured_with_fallback: GuardrailViolationError on Apple
  triggers retry against the $large provider returned by
  resolve_default_provider.
"""

from __future__ import annotations

from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from fichero.llm import (
    AppleUnavailableError,
    GuardrailViolationError,
    LLMConfig,
    UnsupportedLocaleError,
    _pydantic_to_apple_schema,
    _raise_from_bridge_stderr,
    apple_intelligence_supports_locale,
    chat_structured,
    chat_structured_with_fallback,
)


# =============================================================================
# _pydantic_to_apple_schema
# =============================================================================


class _Person(BaseModel):
    name: str
    age: int


class _Place(BaseModel):
    name: str
    notes: Optional[str] = None


class _Extraction(BaseModel):
    """Top-level schema with nested $ref + arrays + optionals."""

    people: list[_Person]
    places: list[_Place] = Field(default_factory=list)
    summary: Optional[str] = Field(default=None, description="one-liner")


class TestPydanticToAppleSchema:
    """Validate the JSON-Schema → Apple schema-tree converter. Apple's
    DynamicGenerationSchema expects properties as a list of `{name,
    schema, optional}` instead of Pydantic's properties-dict + separate
    required list, and it doesn't follow $ref (we inline)."""

    def test_object_root_emits_name_and_properties_list(self):
        out = _pydantic_to_apple_schema(_Extraction)
        assert out["type"] == "object"
        assert out["name"] == "_Extraction"
        # properties is a list, not a dict (Apple's shape)
        assert isinstance(out["properties"], list)
        names = [p["name"] for p in out["properties"]]
        assert names == ["people", "places", "summary"]

    def test_array_property_resolves_items_ref(self):
        out = _pydantic_to_apple_schema(_Extraction)
        people_prop = next(p for p in out["properties"] if p["name"] == "people")
        people_schema = people_prop["schema"]
        assert people_schema["type"] == "array"
        # items is the inlined _Person object — not a $ref
        items = people_schema["items"]
        assert items["type"] == "object"
        assert items["name"] == "_Person"
        item_props = {p["name"]: p for p in items["properties"]}
        assert set(item_props.keys()) == {"name", "age"}
        assert item_props["name"]["schema"]["type"] == "string"
        assert item_props["age"]["schema"]["type"] == "integer"

    def test_optional_property_marked_optional(self):
        """Pydantic's `summary: Optional[str] = None` lands as anyOf
        [str, null] in JSON Schema. The converter strips the null
        branch, recurses on string, and marks the property optional
        because it isn't in the model's `required` list."""
        out = _pydantic_to_apple_schema(_Extraction)
        summary = next(p for p in out["properties"] if p["name"] == "summary")
        assert summary.get("optional") is True
        assert summary["schema"]["type"] == "string"

    def test_optional_inside_nested_object(self):
        """`notes: Optional[str] = None` on _Place should also flatten."""
        out = _pydantic_to_apple_schema(_Extraction)
        places = next(p for p in out["properties"] if p["name"] == "places")
        item_props = {p["name"]: p for p in places["schema"]["items"]["properties"]}
        assert item_props["notes"].get("optional") is True
        assert item_props["notes"]["schema"]["type"] == "string"

    def test_required_property_not_marked_optional(self):
        out = _pydantic_to_apple_schema(_Extraction)
        people = next(p for p in out["properties"] if p["name"] == "people")
        assert "optional" not in people  # required, no flag

    def test_field_description_propagates(self):
        out = _pydantic_to_apple_schema(_Extraction)
        summary = next(p for p in out["properties"] if p["name"] == "summary")
        assert summary["description"] == "one-liner"


# =============================================================================
# chat_structured dispatch
# =============================================================================


class _Result(BaseModel):
    answer: str


class TestChatStructuredDispatch:
    @pytest.mark.asyncio
    async def test_apple_provider_routes_to_fm_bridge(self):
        """When provider=apple, chat_structured invokes
        _apple_intelligence_structured (which subprocesses fm-bridge).
        We mock that helper to confirm dispatch + parameter pass-through."""
        cfg = LLMConfig(provider="apple", model="apple-intelligence")
        with patch(
            "fichero.llm._apple_intelligence_structured",
            new=AsyncMock(return_value=_Result(answer="hi")),
        ) as mock_apple:
            result = await chat_structured(
                prompt="say hi",
                schema=_Result,
                config=cfg,
                system="be brief",
                include_schema_in_prompt=False,
            )
        assert result == _Result(answer="hi")
        mock_apple.assert_awaited_once()
        # include_schema_in_prompt threads through as a kwarg
        kwargs = mock_apple.await_args.kwargs
        assert kwargs.get("include_schema_in_prompt") is False

    @pytest.mark.asyncio
    async def test_non_apple_picks_json_schema_when_profile_advertises_it(self):
        """Profile-driven method selection (#844 item 7): when
        model.profile.structured_output is True, prefer json_schema —
        faster + cheaper than tool-calling. Native OpenAI/Anthropic/
        Gemini advertise this; OpenRouter-passthrough models often
        don't."""
        cfg = LLMConfig(provider="openai", model="gpt-5")

        invoke_result = _Result(answer="from-openai")
        ainvoke_mock = AsyncMock(return_value=invoke_result)
        structured_model = MagicMock()
        structured_model.ainvoke = ainvoke_mock
        base_model = MagicMock()
        base_model.profile = {"structured_output": True}
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("fichero.llm.get_langchain_model", return_value=base_model):
            result = await chat_structured(
                prompt="hi", schema=_Result, config=cfg, system="ye",
            )

        assert result is invoke_result
        base_model.with_structured_output.assert_called_once_with(
            _Result, method="json_schema"
        )

    @pytest.mark.asyncio
    async def test_non_apple_falls_back_to_function_calling_without_profile(self):
        """When the model has no .profile attribute (older provider
        package) or profile.structured_output is False, fall back to
        function_calling — the lowest-common-denominator that every
        tool-capable provider supports."""
        cfg = LLMConfig(provider="openai", model="some-old-model")

        invoke_result = _Result(answer="ok")
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(return_value=invoke_result)
        base_model = MagicMock(spec=["with_structured_output"])  # no profile attr
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("fichero.llm.get_langchain_model", return_value=base_model):
            await chat_structured(
                prompt="hi", schema=_Result, config=cfg,
            )

        base_model.with_structured_output.assert_called_once_with(
            _Result, method="function_calling"
        )

    @pytest.mark.asyncio
    async def test_non_apple_provider_includes_system_message(self):
        """`system` becomes a SystemMessage prepended to the LangChain
        message list."""
        cfg = LLMConfig(provider="openai", model="gpt-5")

        captured_messages: list = []

        async def capture(messages):
            captured_messages.extend(messages)
            return _Result(answer="ok")

        structured_model = MagicMock()
        structured_model.ainvoke = capture
        base_model = MagicMock()
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("fichero.llm.get_langchain_model", return_value=base_model):
            await chat_structured(
                prompt="user prompt",
                schema=_Result,
                config=cfg,
                system="instructions",
            )

        # Two messages: SystemMessage("instructions"), HumanMessage("user prompt")
        from langchain_core.messages import HumanMessage, SystemMessage
        assert len(captured_messages) == 2
        assert isinstance(captured_messages[0], SystemMessage)
        assert captured_messages[0].content == "instructions"
        assert isinstance(captured_messages[1], HumanMessage)
        assert captured_messages[1].content == "user prompt"


# =============================================================================
# chat_structured_with_fallback
# =============================================================================


class TestChatStructuredWithFallback:
    @pytest.mark.asyncio
    async def test_passthrough_when_apple_succeeds(self):
        cfg = LLMConfig(provider="apple", model="apple-intelligence")
        with patch(
            "fichero.llm.chat_structured",
            new=AsyncMock(return_value=_Result(answer="ok")),
        ) as mock_call:
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=cfg
            )
        assert result == _Result(answer="ok")
        # Called once — no fallback needed
        assert mock_call.await_count == 1

    @pytest.mark.asyncio
    async def test_falls_back_to_large_on_guardrail(self):
        """Apple raises GuardrailViolationError → resolve $large alias →
        rebuild LLMConfig from (provider, model) → call chat_structured
        again with the new config. Same pattern as chat_with_fallback (#838)."""
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")

        call_count = {"n": 0}

        async def fake_chat_structured(prompt, schema, config, system=None, include_schema_in_prompt=None, use_case=None):
            call_count["n"] += 1
            if config.provider == "apple":
                raise GuardrailViolationError("safety filter")
            assert config.provider == "openai"
            assert config.model == "gpt-5"
            return _Result(answer="from-large")

        with patch("fichero.llm.chat_structured", new=fake_chat_structured), \
             patch("fichero.llm.resolve_model_alias", return_value=("openai", "gpt-5")):
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=apple_cfg
            )

        assert result == _Result(answer="from-large")
        assert call_count["n"] == 2  # apple call + large fallback

    @pytest.mark.asyncio
    async def test_reraises_when_no_large_configured(self):
        """If resolve_model_alias raises ValueError (no $large set up),
        the original GuardrailViolationError propagates unchanged."""
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")

        with patch(
            "fichero.llm.chat_structured",
            new=AsyncMock(side_effect=GuardrailViolationError("blocked")),
        ), patch(
            "fichero.llm.resolve_model_alias",
            side_effect=ValueError("no $large"),
        ):
            with pytest.raises(GuardrailViolationError, match="blocked"):
                await chat_structured_with_fallback(
                    prompt="x", schema=_Result, config=apple_cfg
                )

    @pytest.mark.asyncio
    async def test_reraises_when_large_equals_current(self):
        """If $large resolves to the same provider+model we just tried,
        no point retrying — re-raise to surface the guardrail."""
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")

        with patch(
            "fichero.llm.chat_structured",
            new=AsyncMock(side_effect=GuardrailViolationError("blocked")),
        ), patch(
            "fichero.llm.resolve_model_alias",
            return_value=("apple", "apple-intelligence"),
        ):
            with pytest.raises(GuardrailViolationError):
                await chat_structured_with_fallback(
                    prompt="x", schema=_Result, config=apple_cfg
                )

    @pytest.mark.asyncio
    async def test_non_guardrail_errors_propagate(self):
        """Generic transport / decoding errors are NOT routed through
        the fallback — only AppleUnavailableError subclasses are. Bare
        RuntimeError from the bridge (e.g. context_overflow, decoding)
        bubbles up for the caller to log and recover."""
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")
        with patch(
            "fichero.llm.chat_structured",
            new=AsyncMock(side_effect=RuntimeError("decoding failure")),
        ):
            with pytest.raises(RuntimeError, match="decoding failure"):
                await chat_structured_with_fallback(
                    prompt="x", schema=_Result, config=apple_cfg
                )

    @pytest.mark.asyncio
    async def test_falls_back_to_large_on_unsupported_locale(self):
        """Apple raises UnsupportedLocaleError → resolve $large → retry.
        Same fallback path as guardrail — both inherit AppleUnavailableError
        so chat_structured_with_fallback's single `except` catches both (#868)."""
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")

        async def fake_chat_structured(prompt, schema, config, system=None, include_schema_in_prompt=None, use_case=None):
            if config.provider == "apple":
                raise UnsupportedLocaleError(
                    "Apple Intelligence (unsupported_language): es-CO not supported"
                )
            assert config.provider == "openai"
            assert config.model == "gpt-5"
            return _Result(answer="from-large")

        with patch("fichero.llm.chat_structured", new=fake_chat_structured), \
             patch("fichero.llm.resolve_model_alias", return_value=("openai", "gpt-5")):
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=apple_cfg
            )

        assert result == _Result(answer="from-large")

    @pytest.mark.asyncio
    async def test_unsupported_locale_reraises_when_no_large(self):
        """No $large configured → original UnsupportedLocaleError surfaces
        unchanged so the caller knows it was an Apple locale rejection,
        not a missing API key."""
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")
        with patch(
            "fichero.llm.chat_structured",
            new=AsyncMock(side_effect=UnsupportedLocaleError("locale rejected")),
        ), patch(
            "fichero.llm.resolve_model_alias",
            side_effect=ValueError("no $large"),
        ):
            with pytest.raises(UnsupportedLocaleError, match="locale rejected"):
                await chat_structured_with_fallback(
                    prompt="x", schema=_Result, config=apple_cfg
                )


class TestAppleUnavailableHierarchy:
    """The AppleUnavailableError base class lets callers catch any
    'Apple can't proceed → use cloud' reason uniformly. Subclasses
    distinguish reasons for telemetry / per-cause UX (#868)."""

    def test_guardrail_is_apple_unavailable(self):
        assert issubclass(GuardrailViolationError, AppleUnavailableError)

    def test_unsupported_locale_is_apple_unavailable(self):
        assert issubclass(UnsupportedLocaleError, AppleUnavailableError)

    def test_apple_unavailable_is_runtime_error(self):
        # Preserves backwards-compat: callers that catch RuntimeError
        # generically (e.g. cleanup's chunked-retry) keep working.
        assert issubclass(AppleUnavailableError, RuntimeError)

    def test_bridge_stderr_unsupported_language_raises_typed(self):
        """The bridge emits {'kind': 'unsupported_language', ...} on Apple
        locale rejection. _raise_from_bridge_stderr must map that to
        UnsupportedLocaleError so the fallback path catches it."""
        import json
        payload = json.dumps({
            "kind": "unsupported_language",
            "error": "An unsupported language or locale was used",
        }).encode("utf-8")
        with pytest.raises(UnsupportedLocaleError) as excinfo:
            _raise_from_bridge_stderr(payload, returncode=1)
        # Subclass relationship lets callers catch the base.
        assert isinstance(excinfo.value, AppleUnavailableError)
        assert "unsupported_language" in str(excinfo.value)

    def test_bridge_stderr_guardrail_raises_typed(self):
        """Guardrail still maps to GuardrailViolationError after the
        AppleUnavailableError refactor (regression guard)."""
        import json
        payload = json.dumps({
            "kind": "guardrail",
            "error": "Safety filter rejected prompt",
        }).encode("utf-8")
        with pytest.raises(GuardrailViolationError) as excinfo:
            _raise_from_bridge_stderr(payload, returncode=1)
        assert isinstance(excinfo.value, AppleUnavailableError)

    def test_bridge_stderr_decoding_stays_runtime_error(self):
        """Non-Apple-unavailable kinds (decoding, context_overflow,
        rate_limited, etc.) remain bare RuntimeError so chat_with_fallback
        does NOT route them through $large — they're transient and the
        caller should retry/chunk in place."""
        import json
        payload = json.dumps({
            "kind": "decoding",
            "error": "Failed to decode generated content",
        }).encode("utf-8")
        with pytest.raises(RuntimeError) as excinfo:
            _raise_from_bridge_stderr(payload, returncode=1)
        # Specifically NOT AppleUnavailableError → fallback skips it.
        assert not isinstance(excinfo.value, AppleUnavailableError)


# =============================================================================
# Locale precheck (#849)
# =============================================================================


class TestSupportsLocale:
    """apple_intelligence_supports_locale subprocesses fm-bridge with
    --supports-locale <code>. We mock subprocess.run since the unit
    test environment may not have fm-bridge available."""

    def setup_method(self):
        # Cache is process-level; clear between tests so each test
        # exercises the subprocess path freshly.
        apple_intelligence_supports_locale.cache_clear()

    def test_supported_locale_returns_true(self):
        """Bridge stdout `{supported: true}` → helper returns True."""
        import subprocess
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout=b'{"locale":"en","supported":true}',
                stderr=b"",
            ),
        ):
            assert apple_intelligence_supports_locale("en") is True

    def test_unsupported_locale_returns_false(self):
        """Bridge stdout `{supported: false}` → helper returns False."""
        import subprocess
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=0,
                stdout=b'{"locale":"yi","supported":false}',
                stderr=b"",
            ),
        ):
            assert apple_intelligence_supports_locale("yi") is False

    def test_bridge_failure_returns_false(self):
        """Any failure (binary missing, timeout, JSON parse error)
        returns False so callers don't accidentally route to a
        non-functional Apple Intelligence path."""
        import subprocess
        with patch(
            "subprocess.run",
            return_value=subprocess.CompletedProcess(
                args=[], returncode=1,
                stdout=b"",
                stderr=b"fm-bridge crash",
            ),
        ):
            assert apple_intelligence_supports_locale("en") is False

    def test_result_is_cached(self):
        """Cache hits avoid the subprocess overhead. Two calls to the
        same locale should subprocess only once."""
        import subprocess
        mock = MagicMock(return_value=subprocess.CompletedProcess(
            args=[], returncode=0,
            stdout=b'{"locale":"en","supported":true}',
            stderr=b"",
        ))
        with patch("subprocess.run", new=mock):
            apple_intelligence_supports_locale("en")
            apple_intelligence_supports_locale("en")
            apple_intelligence_supports_locale("en")
        assert mock.call_count == 1
