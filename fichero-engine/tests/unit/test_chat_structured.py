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
    GuardrailViolationError,
    LLMConfig,
    _pydantic_to_apple_schema,
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
    async def test_non_apple_provider_uses_langchain_function_calling(self):
        """Non-apple providers go through LangChain's
        with_structured_output(method="function_calling"). Verify the
        method kwarg is the one we ship by default (#844 docs note
        function_calling is the lowest-common-denominator across
        OpenAI / OpenRouter / Anthropic / Mistral)."""
        cfg = LLMConfig(provider="openai", model="gpt-5")

        # Build the chain of mocks: get_langchain_model -> .with_structured_output -> .ainvoke
        invoke_result = _Result(answer="from-openai")
        ainvoke_mock = AsyncMock(return_value=invoke_result)
        structured_model = MagicMock()
        structured_model.ainvoke = ainvoke_mock
        base_model = MagicMock()
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("fichero.llm.get_langchain_model", return_value=base_model):
            result = await chat_structured(
                prompt="hi",
                schema=_Result,
                config=cfg,
                system="ye",
            )

        assert result is invoke_result
        # Method kwarg = "function_calling" by default
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

        async def fake_chat_structured(prompt, schema, config, system=None, include_schema_in_prompt=None):
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
        the fallback — only GuardrailViolationError is. RuntimeError
        from the bridge (e.g. context_overflow, decoding) bubbles up
        for the caller to log and recover."""
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")
        with patch(
            "fichero.llm.chat_structured",
            new=AsyncMock(side_effect=RuntimeError("decoding failure")),
        ):
            with pytest.raises(RuntimeError, match="decoding failure"):
                await chat_structured_with_fallback(
                    prompt="x", schema=_Result, config=apple_cfg
                )
