"""Unit tests for chat_structured / chat_structured_with_fallback and the
Pydantic→Apple schema converter (#847).

Covers:
- _pydantic_to_apple_schema: nested objects, arrays, optional fields,
  $ref / $defs resolution, anyOf-with-null Optional handling.
- chat_structured provider dispatch: Apple → fm-bridge subprocess (mocked),
  LangChain → with_structured_output (mocked).
- chat_structured_with_fallback: GuardrailViolationError on Apple
  triggers retry against the $medium provider returned by
  resolve_default_provider.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel, Field

from fichero.llm import (
    AppleUnavailableError,
    GuardrailViolationError,
    LLMConfig,
    ProviderQuotaError,
    StructuredDecodeError,
    UnsupportedLocaleError,
    _PROVIDER_QUOTA_HITS,
    _compute_timeout,
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


class TestComputeTimeout:
    """Single source of truth for wall-clock timeouts on every LLM
    call path (#855, #862, #867). Three formulas, scaled by config
    timeout, max_tokens, and schema size (Apple structured only)."""

    def test_langchain_default_floors_at_60s(self):
        cfg = LLMConfig(provider="openai", model="gpt-4", timeout=10, max_tokens=512)
        # 10 * 5 * (512/1024) = 25 → clamped to floor 60
        assert _compute_timeout(cfg, "langchain") == 60

    def test_langchain_scales_with_max_tokens(self):
        small = LLMConfig(provider="x", model="y", timeout=60, max_tokens=128)
        big = LLMConfig(provider="x", model="y", timeout=60, max_tokens=4096)
        # Bigger max_tokens → bigger budget, both clamped though.
        assert _compute_timeout(big, "langchain") > _compute_timeout(small, "langchain")

    def test_langchain_caps_at_600s(self):
        cfg = LLMConfig(provider="x", model="y", timeout=600, max_tokens=4096)
        # 600 * 5 * 4 = 12000 → clamped to 600
        assert _compute_timeout(cfg, "langchain") == 600

    def test_apple_chat_tighter_than_langchain(self):
        cfg = LLMConfig(provider="apple", model="apple-intelligence", timeout=60)
        chat = _compute_timeout(cfg, "apple_chat")
        lc = _compute_timeout(cfg, "langchain")
        # Free-form Apple should be tighter — guided decoding overhead
        # is on structured, not chat.
        assert chat < lc

    def test_apple_chat_floors_at_30s(self):
        cfg = LLMConfig(provider="apple", model="x", timeout=10, max_tokens=128)
        # 10 * (128/1024) = 1.25 → clamped to floor 30
        assert _compute_timeout(cfg, "apple_chat") == 30

    def test_apple_chat_caps_at_180s(self):
        cfg = LLMConfig(provider="apple", model="x", timeout=600, max_tokens=4096)
        assert _compute_timeout(cfg, "apple_chat") == 180

    def test_apple_structured_scales_with_schema_size(self):
        cfg = LLMConfig(provider="apple", model="x", timeout=60)
        small_schema = _compute_timeout(cfg, "apple_structured", schema_chars=500)
        big_schema = _compute_timeout(cfg, "apple_structured", schema_chars=10000)
        # Bigger schema → more guided-decoding overhead → bigger budget.
        assert big_schema > small_schema

    def test_apple_structured_baseline(self):
        cfg = LLMConfig(provider="apple", model="x", timeout=60, max_tokens=1024)
        # 60 * 2 * 1.0 (1024 baseline) * 1.0 (2K schema baseline) = 120
        assert _compute_timeout(cfg, "apple_structured", schema_chars=2000) == 120

    def test_apple_structured_caps_at_600s(self):
        cfg = LLMConfig(provider="apple", model="x", timeout=600, max_tokens=4096)
        assert _compute_timeout(
            cfg, "apple_structured", schema_chars=10000,
        ) == 600

    def test_unknown_kind_raises(self):
        cfg = LLMConfig(provider="x", model="y", timeout=60)
        with pytest.raises(ValueError, match="Unknown timeout kind"):
            _compute_timeout(cfg, "garbage")  # type: ignore[arg-type]

    def test_zero_timeout_uses_default_base(self):
        """config.timeout=0 means 'no client-side timeout' — the helper
        defaults to a sensible base (60s) and clamps from there."""
        cfg = LLMConfig(provider="x", model="y", timeout=0, max_tokens=1024)
        # 60 * 5 * 1 = 300 (in [60, 600])
        assert _compute_timeout(cfg, "langchain") == 300


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


class TestPydanticToAppleSchemaFailLoud:
    """The converter must fail loud with a field-pointing error on
    unsupported shapes (#856) — silently emitting a partial tree lets
    the bridge raise an opaque 'GenerationSchema init failed' downstream
    that's painful to diagnose."""

    def test_discriminated_union_raises(self):
        """anyOf with >1 non-null branches isn't expressible in
        DynamicGenerationSchema; converter must point at the offending
        field."""
        from typing import Union

        class _Cat(BaseModel):
            kind: str = "cat"
            meow: str

        class _Dog(BaseModel):
            kind: str = "dog"
            bark: str

        class _Pet(BaseModel):
            animal: Union[_Cat, _Dog]

        with pytest.raises(ValueError, match="2 non-null branches"):
            _pydantic_to_apple_schema(_Pet)

    def test_enum_field_raises(self):
        """Enum / Literal fields aren't modeled today."""
        from typing import Literal

        class _Status(BaseModel):
            state: Literal["pending", "done", "failed"]

        with pytest.raises(ValueError, match="enum types not yet supported"):
            _pydantic_to_apple_schema(_Status)

    def test_format_keyword_raises(self):
        """`format=date`/`format=uri`/etc. imply runtime validation
        DynamicGenerationSchema doesn't enforce; silently dropping the
        constraint would mislead the caller."""
        from datetime import date

        class _DatedItem(BaseModel):
            when: date

        with pytest.raises(ValueError, match="format="):
            _pydantic_to_apple_schema(_DatedItem)

    def test_recursive_type_raises(self):
        """Self-referential models would loop indefinitely. Detect via
        seen-set on $defs name and fail loud."""

        class _Node(BaseModel):
            value: str
            children: list["_Node"] = []

        _Node.model_rebuild()
        with pytest.raises(ValueError, match="recursive type"):
            _pydantic_to_apple_schema(_Node)

    def test_error_message_includes_field_path(self):
        """Errors must point at the offending nested field, not just
        the top-level model — otherwise caller can't tell what to fix."""
        from typing import Literal

        class _Inner(BaseModel):
            mode: Literal["a", "b", "c"]  # enum → fails

        class _Outer(BaseModel):
            inner: _Inner

        with pytest.raises(ValueError) as exc:
            _pydantic_to_apple_schema(_Outer)
        # Path should mention the nested field 'mode', not just '$' /
        # 'inner' alone — caller needs to know exactly what field tripped.
        assert "mode" in str(exc.value) or "inner.mode" in str(exc.value)


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
                permissive_guardrails=True,
            )
        assert result == _Result(answer="hi")
        mock_apple.assert_awaited_once()
        # Apple-only structured options thread through as kwargs.
        kwargs = mock_apple.await_args.kwargs
        assert kwargs.get("include_schema_in_prompt") is False
        assert kwargs.get("permissive_guardrails") is True

    @pytest.mark.asyncio
    async def test_non_apple_picks_json_schema_when_profile_advertises_it(self):
        """Profile-driven method selection (#844 item 7): when
        model.profile.structured_output is True, prefer json_schema —
        faster + cheaper than tool-calling. Native Anthropic/Gemini/
        Mistral advertise this; OpenRouter-passthrough models often
        don't. (openai/openrouter have explicit overrides — #1802/#1803 —
        so this test uses a native provider that hits the profile branch.)"""
        cfg = LLMConfig(provider="anthropic", model="claude-sonnet-4.6")

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
        # json_schema is paired with strict=False so LangChain coerces into the
        # pydantic model without OpenAI's rigid schema gate (#1803).
        base_model.with_structured_output.assert_called_once_with(
            _Result, method="json_schema", include_raw=True, strict=False
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
            _Result, method="function_calling", include_raw=True
        )

    @pytest.mark.asyncio
    async def test_omlx_uses_provider_default_structured_method(self):
        """Local OpenAI-compatible providers (omlx/lmstudio/ollama) don't
        reliably support json_schema/function_calling. We should not
        force a method; LangChain's default path must be used."""
        cfg = LLMConfig(provider="omlx", model="Qwen3-VL-4B-Instruct-MLX-8bit")

        invoke_result = _Result(answer="ok")
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(return_value=invoke_result)
        base_model = MagicMock()
        base_model.profile = {"structured_output": True}
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("fichero.llm.get_langchain_model", return_value=base_model), patch(
            "fichero.llm._ensure_managed_local_provider_ready",
            new=AsyncMock(),
        ):
            await chat_structured(prompt="hi", schema=_Result, config=cfg)

        base_model.with_structured_output.assert_called_once_with(
            _Result, include_raw=True
        )

    @pytest.mark.asyncio
    async def test_openrouter_uses_function_calling(self):
        """OpenRouter routes structured output through function_calling
        (#1802). json_mode 400s the OpenAI route ('messages' must contain
        'json') and strict json_schema returns an empty body on Bedrock-
        Claude; tool-calling works on both once the Bedrock-hostile
        parallel_tool_calls param is stripped at the request layer."""
        cfg = LLMConfig(provider="openrouter", model="anthropic/claude-3.5-haiku")

        invoke_result = _Result(answer="ok")
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(return_value=invoke_result)
        base_model = MagicMock()
        base_model.profile = {"structured_output": True}
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("fichero.llm.get_langchain_model", return_value=base_model):
            await chat_structured(prompt="hi", schema=_Result, config=cfg)

        base_model.with_structured_output.assert_called_once_with(
            _Result, method="function_calling", include_raw=True
        )

    @pytest.mark.asyncio
    async def test_include_raw_dict_unwraps_to_parsed(self, caplog):
        """include_raw=True returns {raw, parsed, parsing_error}.
        chat_structured must unwrap the parsed instance and log
        usage_metadata from the raw AIMessage. (#844 item 8)"""
        import logging
        cfg = LLMConfig(provider="openai", model="gpt-5")

        raw_message = MagicMock()
        raw_message.usage_metadata = {
            "input_tokens": 120,
            "output_tokens": 45,
            "total_tokens": 165,
        }
        invoke_result = {
            "raw": raw_message,
            "parsed": _Result(answer="from-dict"),
            "parsing_error": None,
        }
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(return_value=invoke_result)
        base_model = MagicMock()
        base_model.profile = {"structured_output": True}
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("fichero.llm.get_langchain_model", return_value=base_model), \
             caplog.at_level(logging.INFO, logger="fichero.llm"):
            result = await chat_structured(prompt="x", schema=_Result, config=cfg)

        assert result == _Result(answer="from-dict")
        assert any("LLM usage" in r.message and "input=120" in r.message
                   for r in caplog.records)

    @pytest.mark.asyncio
    async def test_include_raw_parsing_error_raises(self):
        """When the model returns parsing_error and no parsed value,
        chat_structured must raise — not silently return None."""
        cfg = LLMConfig(provider="openai", model="gpt-5")
        invoke_result = {
            "raw": MagicMock(usage_metadata=None),
            "parsed": None,
            "parsing_error": ValueError("schema mismatch on field 'x'"),
        }
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(return_value=invoke_result)
        base_model = MagicMock()
        base_model.profile = {"structured_output": True}
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("fichero.llm.get_langchain_model", return_value=base_model):
            with pytest.raises(RuntimeError, match="structured parse failed"):
                await chat_structured(prompt="x", schema=_Result, config=cfg)

    @pytest.mark.asyncio
    async def test_collect_usage_captures_apple_estimate(self):
        """`with collect_usage() as bucket: ...` should accumulate every
        LLM call's usage entry while the block is active. Outside the
        block, recording is a no-op log-only path. (#852)"""
        from fichero.llm import collect_usage, _log_apple_usage_estimate

        cfg = LLMConfig(provider="apple", model="apple-intelligence")

        # No collector active → no exception, no bucket to leak.
        _log_apple_usage_estimate(cfg, prompt="alpha", response_text="beta", kind="chat")

        # Active collector → entries accumulate.
        with collect_usage() as bucket:
            _log_apple_usage_estimate(cfg, prompt="alpha bravo", response_text="charlie", kind="chat")
            _log_apple_usage_estimate(cfg, prompt="delta", response_text="echo foxtrot", kind="structured")

        assert len(bucket) == 2
        assert bucket[0]["provider"] == "apple"
        assert bucket[0]["kind"] == "chat"
        assert bucket[0]["estimated"] is True
        assert bucket[0]["input_tokens"] is not None
        assert bucket[0]["output_tokens"] is not None
        assert bucket[1]["kind"] == "structured"

        # Outside again → bucket is no longer the active target.
        _log_apple_usage_estimate(cfg, prompt="ignored", response_text="ignored", kind="chat")
        assert len(bucket) == 2

    @pytest.mark.asyncio
    async def test_collect_usage_captures_langchain_chat(self):
        """LangChain plain chat() also flows into the active collector
        when AIMessage.usage_metadata is present."""
        from fichero.llm import collect_usage, chat

        cfg = LLMConfig(provider="openai", model="gpt-5")
        response_msg = MagicMock()
        response_msg.content = "ok"
        response_msg.usage_metadata = {
            "input_tokens": 50, "output_tokens": 20, "total_tokens": 70,
        }
        model = MagicMock()
        model.ainvoke = AsyncMock(return_value=response_msg)

        with patch("fichero.llm.get_langchain_model", return_value=model):
            with collect_usage() as bucket:
                await chat("hi", config=cfg)

        assert len(bucket) == 1
        assert bucket[0]["provider"] == "openai"
        assert bucket[0]["kind"] == "chat"
        assert bucket[0]["estimated"] is False
        assert bucket[0]["input_tokens"] == 50
        assert bucket[0]["output_tokens"] == 20
        assert bucket[0]["total_tokens"] == 70

    @pytest.mark.asyncio
    async def test_apple_logs_estimated_usage(self, caplog):
        """Apple Intelligence path logs an estimated input/output/total
        token count via _log_apple_usage_estimate (#843 item 3).
        Foundation Models doesn't expose token counts through fm-bridge's
        stdout payload yet, so we estimate from char counts and mark the
        log line (estimated)."""
        import logging
        from fichero.llm import _log_apple_usage_estimate

        cfg = LLMConfig(provider="apple", model="apple-intelligence")
        with caplog.at_level(logging.INFO, logger="fichero.llm"):
            _log_apple_usage_estimate(
                cfg,
                prompt="hola, esto es un prompt corto",
                response_text="ok",
                kind="chat",
            )
        msgs = [r.message for r in caplog.records]
        assert any("apple/apple-intelligence chat" in m for m in msgs)
        assert any("(estimated)" in m for m in msgs)
        assert any("input=~" in m and "output=~" in m for m in msgs)

    @pytest.mark.asyncio
    async def test_apple_usage_prefers_bridge_usage_payload(self):
        """When fm-bridge includes usage counts, we should log exact
        values (not estimated)."""
        from fichero.llm import _log_apple_usage_from_bridge, collect_usage

        cfg = LLMConfig(provider="apple", model="apple-intelligence")
        bridge_payload = {
            "usage": {
                "input_tokens": 111,
                "output_tokens": 22,
                "total_tokens": 133,
            }
        }

        with collect_usage() as bucket:
            used = _log_apple_usage_from_bridge(
                cfg, bridge_payload, kind="structured"
            )
        assert used is True
        assert len(bucket) == 1
        assert bucket[0]["estimated"] is False
        assert bucket[0]["input_tokens"] == 111
        assert bucket[0]["output_tokens"] == 22
        assert bucket[0]["total_tokens"] == 133

    @pytest.mark.asyncio
    async def test_apple_usage_handles_messages_list(self, caplog):
        """When prompt is a messages list (OpenAI shape), the estimator
        concats content fields rather than crashing on str()."""
        import logging
        from fichero.llm import _log_apple_usage_estimate

        cfg = LLMConfig(provider="apple", model="apple-intelligence")
        prompt = [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "what is 2+2"},
        ]
        with caplog.at_level(logging.INFO, logger="fichero.llm"):
            _log_apple_usage_estimate(cfg, prompt=prompt, response_text="4", kind="chat")
        # Estimator ran and logged — no exception on list input.
        assert any("estimated" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_include_raw_legacy_pydantic_return_still_works(self):
        """Backward-compat: tests / providers that return a bare Pydantic
        instance from ainvoke (rather than the dict shape) keep working —
        the unwrap branch checks for the dict shape first."""
        cfg = LLMConfig(provider="openai", model="gpt-5")

        invoke_result = _Result(answer="legacy")
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(return_value=invoke_result)
        base_model = MagicMock()
        base_model.profile = {"structured_output": True}
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        with patch("fichero.llm.get_langchain_model", return_value=base_model):
            result = await chat_structured(prompt="x", schema=_Result, config=cfg)

        assert result == _Result(answer="legacy")

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


class TestProviderQuotaHandling:
    class _QuotaError(Exception):
        def __init__(self, message: str = "Key limit exceeded (weekly limit)"):
            super().__init__(message)
            self.status_code = 403
            self.response = SimpleNamespace(status_code=403)

    @pytest.mark.asyncio
    async def test_chat_structured_raises_typed_quota_error_once(self):
        _PROVIDER_QUOTA_HITS.clear()
        cfg = LLMConfig(provider="openrouter", model="gpt-5")

        quota_error = self._QuotaError()
        structured_model = MagicMock()
        structured_model.ainvoke = AsyncMock(side_effect=quota_error)
        base_model = MagicMock()
        base_model.profile = {"structured_output": True}
        base_model.with_structured_output = MagicMock(return_value=structured_model)

        tracker = MagicMock()
        with patch("fichero.llm.get_langchain_model", return_value=base_model), \
             patch("fichero.workflows.activity.get_activity_tracker", return_value=tracker), \
             patch("fichero.llm.logger.warning") as warn:
            with pytest.raises(ProviderQuotaError, match="Provider openrouter quota/limit hit"):
                await chat_structured(prompt="x", schema=_Result, config=cfg)
            with pytest.raises(ProviderQuotaError):
                await chat_structured(prompt="y", schema=_Result, config=cfg)

        assert warn.call_count == 1
        assert tracker.log.call_count == 1

    @pytest.mark.asyncio
    async def test_structured_fallback_uses_medium_env_override(self, monkeypatch):
        monkeypatch.setenv("FICHERO_MEDIUM_PROVIDER", "openai")
        monkeypatch.setenv("FICHERO_MEDIUM_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("FICHERO_MEDIUM_BASE_URL", "http://127.0.0.1:8765/v1")
        cfg = LLMConfig(provider="apple", model="apple-intelligence")

        calls: list[LLMConfig] = []

        async def fake_chat_structured(
            prompt,
            schema,
            config,
            system=None,
            include_schema_in_prompt=None,
            use_case=None,
            permissive_guardrails=False,
        ):
            calls.append(config)
            if len(calls) == 1:
                raise AppleUnavailableError("guardrail")
            return _Result(answer="from-env")

        with patch("fichero.llm.chat_structured", new=fake_chat_structured), \
             patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=True):
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=cfg
            )

        assert result == _Result(answer="from-env")
        assert len(calls) == 2
        fallback_config = calls[1]
        assert fallback_config.provider == "openai"
        assert fallback_config.model == "gpt-4o-mini"
        assert fallback_config.api_base == "http://127.0.0.1:8765/v1"


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
    async def test_falls_back_to_medium_on_guardrail(self):
        """Apple raises GuardrailViolationError → resolve $medium alias →
        rebuild LLMConfig from (provider, model) → call chat_structured
        again with the new config. Same pattern as chat_with_fallback (#838)."""
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")

        call_count = {"n": 0}

        async def fake_chat_structured(prompt, schema, config, system=None, include_schema_in_prompt=None, use_case=None, permissive_guardrails=False):
            call_count["n"] += 1
            if config.provider == "apple":
                raise GuardrailViolationError("safety filter")
            assert config.provider == "openrouter"
            assert config.model == "openai/gpt-4o-mini"
            return _Result(answer="from-medium")

        with patch("fichero.llm.chat_structured", new=fake_chat_structured), \
             patch(
                 "fichero.llm.resolve_model_alias",
                 return_value=("openrouter", "openai/gpt-4o-mini"),
             ), \
             patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=True):
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=apple_cfg
            )

        assert result == _Result(answer="from-medium")
        assert call_count["n"] == 2  # apple call + medium fallback

    @pytest.mark.asyncio
    async def test_tries_large_when_medium_unusable(self):
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")
        calls: list[LLMConfig] = []

        async def fake_chat_structured(
            prompt,
            schema,
            config,
            system=None,
            include_schema_in_prompt=None,
            use_case=None,
            permissive_guardrails=False,
        ):
            calls.append(config)
            if config.provider == "apple":
                raise GuardrailViolationError("safety filter")
            if config.provider == "openrouter":
                raise AppleUnavailableError("medium unavailable")
            assert config.provider == "openai"
            assert config.model == "mlx-local"
            return _Result(answer="from-large")

        def resolve_alias(provider, model):
            if provider == "$medium":
                return ("openrouter", "openai/gpt-4o-mini")
            if provider == "$large":
                return ("openai", "mlx-local")
            raise AssertionError(provider)

        with patch("fichero.llm.chat_structured", new=fake_chat_structured), \
             patch("fichero.llm.resolve_model_alias", side_effect=resolve_alias), \
             patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=True):
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=apple_cfg
            )

        assert result == _Result(answer="from-large")
        assert [(c.provider, c.model) for c in calls] == [
            ("apple", "apple-intelligence"),
            ("openrouter", "openai/gpt-4o-mini"),
            ("openai", "mlx-local"),
        ]

    @pytest.mark.asyncio
    async def test_schema_failure_retries_without_schema_prompt_injection(self):
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")
        good = _Result(answer="from-compact-retry")
        mock_structured = AsyncMock(
            side_effect=[
                StructuredDecodeError("(schema): too large", kind="schema"),
                good,
            ]
        )

        with patch("fichero.llm.chat_structured", new=mock_structured), \
             patch("fichero.llm.resolve_model_alias") as mock_resolve:
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=apple_cfg
            )

        assert result == good
        assert mock_structured.await_count == 2
        assert mock_structured.await_args_list[1].kwargs["include_schema_in_prompt"] is False
        mock_resolve.assert_not_called()

    @pytest.mark.asyncio
    async def test_remote_paid_fallbacks_are_skipped_by_default(self):
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")
        mock_structured = AsyncMock(side_effect=GuardrailViolationError("blocked"))

        def resolve_alias(provider, model):
            if provider == "$medium":
                return ("openrouter", "openai/gpt-4o-mini")
            if provider == "$large":
                return ("openai", "gpt-5")
            raise AssertionError(provider)

        with patch("fichero.llm.chat_structured", new=mock_structured), \
             patch("fichero.llm.resolve_model_alias", side_effect=resolve_alias), \
             patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=False):
            with pytest.raises(GuardrailViolationError, match="blocked"):
                await chat_structured_with_fallback(
                    prompt="x", schema=_Result, config=apple_cfg
                )

        assert mock_structured.await_count == 1

    @pytest.mark.asyncio
    async def test_fallback_preserves_use_case_and_permissive_guardrails(self):
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")
        calls: list[tuple[str, str | None, bool]] = []

        async def fake_chat_structured(
            prompt,
            schema,
            config,
            system=None,
            include_schema_in_prompt=None,
            use_case=None,
            permissive_guardrails=False,
        ):
            calls.append((config.provider, use_case, permissive_guardrails))
            if config.provider == "apple":
                raise GuardrailViolationError("blocked")
            return _Result(answer="from-medium")

        with patch("fichero.llm.chat_structured", new=fake_chat_structured), \
             patch(
                 "fichero.llm.resolve_model_alias",
                 return_value=("openrouter", "openai/gpt-4o-mini"),
             ), \
             patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=True):
            result = await chat_structured_with_fallback(
                prompt="x",
                schema=_Result,
                config=apple_cfg,
                use_case="extract_entities",
                permissive_guardrails=True,
            )

        assert result == _Result(answer="from-medium")
        assert calls == [
            ("apple", "extract_entities", True),
            ("openrouter", "extract_entities", True),
        ]

    @pytest.mark.asyncio
    async def test_local_large_fallback_still_runs_when_paid_remote_disabled(self):
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")
        calls: list[LLMConfig] = []

        async def fake_chat_structured(
            prompt,
            schema,
            config,
            system=None,
            include_schema_in_prompt=None,
            use_case=None,
            permissive_guardrails=False,
        ):
            calls.append(config)
            if config.provider == "apple":
                raise GuardrailViolationError("blocked")
            assert config.provider == "ollama"
            assert config.model == "llama3.2"
            return _Result(answer="from-local")

        def resolve_alias(provider, model):
            if provider == "$medium":
                return ("openrouter", "openai/gpt-4o-mini")
            if provider == "$large":
                return ("ollama", "llama3.2")
            raise AssertionError(provider)

        with patch("fichero.llm.chat_structured", new=fake_chat_structured), \
             patch("fichero.llm.resolve_model_alias", side_effect=resolve_alias), \
             patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=False):
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=apple_cfg
            )

        assert result == _Result(answer="from-local")
        assert [(c.provider, c.model) for c in calls] == [
            ("apple", "apple-intelligence"),
            ("ollama", "llama3.2"),
        ]

    @pytest.mark.asyncio
    async def test_reraises_when_no_fallback_configured(self):
        """If resolve_model_alias raises ValueError for both fallbacks,
        the original GuardrailViolationError propagates unchanged."""
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")

        with patch(
            "fichero.llm.chat_structured",
            new=AsyncMock(side_effect=GuardrailViolationError("blocked")),
        ), patch(
            "fichero.llm.resolve_model_alias",
            side_effect=ValueError("no fallback"),
        ):
            with pytest.raises(GuardrailViolationError, match="blocked"):
                await chat_structured_with_fallback(
                    prompt="x", schema=_Result, config=apple_cfg
                )

    @pytest.mark.asyncio
    async def test_reraises_when_fallbacks_equal_current(self):
        """If fallbacks resolve to the same provider+model we just tried,
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
    async def test_falls_back_to_medium_on_unsupported_locale(self):
        """Apple raises UnsupportedLocaleError → resolve $medium → retry.
        Same fallback path as guardrail — both inherit AppleUnavailableError
        so chat_structured_with_fallback's single `except` catches both (#868)."""
        apple_cfg = LLMConfig(provider="apple", model="apple-intelligence")

        async def fake_chat_structured(prompt, schema, config, system=None, include_schema_in_prompt=None, use_case=None, permissive_guardrails=False):
            if config.provider == "apple":
                raise UnsupportedLocaleError(
                    "Apple Intelligence (unsupported_language): es-CO not supported"
                )
            assert config.provider == "openrouter"
            assert config.model == "openai/gpt-4o-mini"
            return _Result(answer="from-medium")

        with patch("fichero.llm.chat_structured", new=fake_chat_structured), \
             patch(
                 "fichero.llm.resolve_model_alias",
                 return_value=("openrouter", "openai/gpt-4o-mini"),
             ), \
             patch("fichero.llm._paid_remote_fallbacks_enabled", return_value=True):
            result = await chat_structured_with_fallback(
                prompt="x", schema=_Result, config=apple_cfg
            )

        assert result == _Result(answer="from-medium")

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

    def test_bridge_stderr_decoding_raises_structured_decode_error(self):
        """Grammar-decode failures map to StructuredDecodeError, which IS
        an AppleUnavailableError subclass since #949/#962 — so
        chat_structured_with_fallback escapes the chunk to $large instead
        of letting extract_all silently drop it. (Pre-#962 these were bare
        RuntimeError and the fallback skipped them.)"""
        import json
        payload = json.dumps({
            "kind": "decoding",
            "error": "Failed to decode generated content",
        }).encode("utf-8")
        with pytest.raises(StructuredDecodeError) as excinfo:
            _raise_from_bridge_stderr(payload, returncode=1)
        # StructuredDecodeError is fallback-eligible by design.
        assert isinstance(excinfo.value, AppleUnavailableError)


# =============================================================================
# Locale precheck (#849)
# =============================================================================


class TestSupportsLocale:
    """apple_intelligence_supports_locale spawns fm-bridge via
    asyncio.create_subprocess_exec — non-blocking probe on a typed
    coroutine boundary (#857). Tests mock the asyncio process to avoid
    needing fm-bridge in the test environment."""

    def setup_method(self):
        # Cache is module-level; clear between tests so each test
        # exercises the subprocess path freshly.
        from fichero.llm import _LOCALE_SUPPORT_CACHE
        _LOCALE_SUPPORT_CACHE.clear()

    def _fake_proc(self, returncode: int, stdout: bytes, stderr: bytes = b""):
        """Build a mock async subprocess that mimics the bits we use:
        .returncode + .communicate() returning (stdout, stderr)."""
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(return_value=(stdout, stderr))
        return proc

    @pytest.mark.asyncio
    async def test_supported_locale_returns_true(self):
        """Bridge stdout `{supported: true}` → helper returns True."""
        proc = self._fake_proc(0, b'{"locale":"en","supported":true}')
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ), patch("pathlib.Path.is_file", return_value=True), \
           patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_mode = 0o755
            assert await apple_intelligence_supports_locale("en") is True

    @pytest.mark.asyncio
    async def test_unsupported_locale_returns_false(self):
        """Bridge stdout `{supported: false}` → helper returns False."""
        proc = self._fake_proc(0, b'{"locale":"yi","supported":false}')
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ), patch("pathlib.Path.is_file", return_value=True), \
           patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_mode = 0o755
            assert await apple_intelligence_supports_locale("yi") is False

    @pytest.mark.asyncio
    async def test_bridge_failure_returns_false(self):
        """Any failure (binary missing, timeout, JSON parse error)
        returns False so callers don't accidentally route to a
        non-functional Apple Intelligence path."""
        proc = self._fake_proc(1, b"", b"fm-bridge crash")
        with patch(
            "asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ), patch("pathlib.Path.is_file", return_value=True), \
           patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_mode = 0o755
            assert await apple_intelligence_supports_locale("en") is False

    @pytest.mark.asyncio
    async def test_result_is_cached(self):
        """Cache hits avoid the subprocess overhead. Three calls to the
        same locale should subprocess only once — the lock + cache
        pattern is async-safe."""
        proc = self._fake_proc(0, b'{"locale":"en","supported":true}')
        spawn = AsyncMock(return_value=proc)
        with patch("asyncio.create_subprocess_exec", new=spawn), \
             patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.stat") as mock_stat:
            mock_stat.return_value.st_mode = 0o755
            await apple_intelligence_supports_locale("en")
            await apple_intelligence_supports_locale("en")
            await apple_intelligence_supports_locale("en")
        assert spawn.call_count == 1

    @pytest.mark.asyncio
    async def test_no_binary_returns_false(self):
        """When fm-bridge isn't installed, returns False without raising."""
        with patch("pathlib.Path.is_file", return_value=False):
            assert await apple_intelligence_supports_locale("en") is False


class _FakeRequest:
    """Minimal stand-in for httpx.Request for hook unit tests — exposes
    the attributes _openrouter_strip_parallel_tool_use reads/writes."""

    def __init__(self, body: bytes, content_type: str = "application/json"):
        import httpx

        self._content = body
        self.stream = httpx.ByteStream(body)
        self.headers = {
            "content-type": content_type,
            "content-length": str(len(body)),
        }

    @property
    def content(self) -> bytes:
        return self._content


class TestOpenRouterStripParallelToolUse:
    """The httpx request hook that keeps function_calling structured output
    working on the OpenRouter→Bedrock-Claude route (#1802)."""

    @pytest.mark.asyncio
    async def test_strips_parallel_tool_calls_field(self):
        import json

        from fichero.llm import _openrouter_strip_parallel_tool_use

        body = {
            "model": "anthropic/claude-3.5-haiku",
            "messages": [{"role": "user", "content": "hi"}],
            "parallel_tool_calls": False,
            "tool_choice": {"type": "function", "function": {"name": "X"}},
        }
        req = _FakeRequest(json.dumps(body).encode())
        await _openrouter_strip_parallel_tool_use(req)

        out = json.loads(req.content.decode())
        assert "parallel_tool_calls" not in out
        # Everything else is preserved verbatim.
        assert out["model"] == "anthropic/claude-3.5-haiku"
        assert out["tool_choice"] == body["tool_choice"]
        assert req.headers["content-length"] == str(len(req.content))

    @pytest.mark.asyncio
    async def test_strips_nested_disable_parallel_tool_use(self):
        import json

        from fichero.llm import _openrouter_strip_parallel_tool_use

        body = {
            "tool_choice": {"type": "auto", "disable_parallel_tool_use": True},
        }
        req = _FakeRequest(json.dumps(body).encode())
        await _openrouter_strip_parallel_tool_use(req)

        out = json.loads(req.content.decode())
        assert "disable_parallel_tool_use" not in out["tool_choice"]
        assert out["tool_choice"]["type"] == "auto"

    @pytest.mark.asyncio
    async def test_passes_through_clean_body_untouched(self):
        import json

        from fichero.llm import _openrouter_strip_parallel_tool_use

        original = json.dumps({"model": "m", "messages": []}).encode()
        req = _FakeRequest(original)
        await _openrouter_strip_parallel_tool_use(req)
        # No offending key → body is left byte-identical.
        assert req.content == original

    @pytest.mark.asyncio
    async def test_ignores_non_json_body(self):
        from fichero.llm import _openrouter_strip_parallel_tool_use

        original = b"--multipart-boundary--"
        req = _FakeRequest(original, content_type="multipart/form-data")
        await _openrouter_strip_parallel_tool_use(req)
        assert req.content == original
