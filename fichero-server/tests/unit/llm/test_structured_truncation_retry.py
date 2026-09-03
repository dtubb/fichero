"""chat_structured truncation recovery + classified empty failures.

Production shape (beta catalogue run, 2026-09-03, ~250 files): the OpenRouter
gemini-3.1-flash-lite structured call came back with NO parsed result, an
empty AIMessage, output_tokens=0 and finish_reason='length' — the model's
default-on hidden reasoning burned the entire max_tokens budget before a
single answer token. The transcription path already recovers from exactly
this shape (vision_base empty-retry: raise the ceiling, disable reasoning);
chat_structured now applies the same policy, and a final failure names its
shape via StructuredCallEmptyError.error_kind (the 10872b864 classification
pattern).

The same run's raw message carried finish_reason='lengthlength' and a doubled
model name with input_tokens exactly 2× the prompt — the LangChain streaming
chunk-merge folding repeated OpenRouter/Gemini metadata (strings concatenate,
cumulative usage sums). Truncation detection therefore matches by SUBSTRING,
and chat_structured pins real models to the non-streaming path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from fichero_server.llm import (
    LLMConfig,
    STRUCTURED_ERROR_EMPTY,
    STRUCTURED_ERROR_TRUNCATED,
    StructuredCallEmptyError,
    chat_structured,
)


class _Result(BaseModel):
    answer: str = ""


def _raw_message(finish_reason: str, **usage: int) -> MagicMock:
    raw = MagicMock()
    raw.response_metadata = {
        "finish_reason": finish_reason,
        "model_name": "google/gemini-3.1-flash-lite",
    }
    raw.usage_metadata = {
        "input_tokens": usage.get("input_tokens", 640),
        "output_tokens": usage.get("output_tokens", 0),
        "total_tokens": usage.get("total_tokens", 640),
    }
    return raw


def _unparsed(finish_reason: str) -> dict:
    return {"raw": _raw_message(finish_reason), "parsed": None, "parsing_error": None}


def _model_returning(results: list) -> MagicMock:
    """A fake LangChain model whose structured ainvoke pops from `results`."""
    structured_model = MagicMock()
    structured_model.ainvoke = AsyncMock(side_effect=results)
    base_model = MagicMock(spec=["with_structured_output"])
    base_model.with_structured_output = MagicMock(return_value=structured_model)
    return base_model


@pytest.mark.asyncio
async def test_length_truncation_retries_with_raised_budget_and_reasoning_off():
    cfg = LLMConfig(
        provider="openrouter", model="google/gemini-3.1-flash-lite", max_tokens=8192
    )
    good = {"raw": _raw_message("stop"), "parsed": _Result(answer="ok"),
            "parsing_error": None}
    seen_configs: list[LLMConfig] = []
    # Capturing per-call configs is the point: the retry must arrive with a
    # materially larger budget and reasoning disabled, mirroring the vision
    # empty-retry policy (de336cc92).
    shared = _model_returning([_unparsed("length"), good])
    with patch(
        "fichero_server.llm.get_langchain_model",
        side_effect=lambda config: (seen_configs.append(config), shared)[1],
    ):
        result = await chat_structured(prompt="hi", schema=_Result, config=cfg)

    assert result == _Result(answer="ok")
    assert len(seen_configs) == 2
    retry_cfg = seen_configs[1]
    assert retry_cfg.max_tokens >= 2 * cfg.max_tokens
    assert retry_cfg.reasoning_effort == "disabled"


@pytest.mark.asyncio
async def test_doubled_finish_reason_lengthlength_still_detected_as_truncation():
    """The doubled-metadata fold produces 'lengthlength' — substring match."""
    cfg = LLMConfig(provider="openrouter", model="google/gemini-3.1-flash-lite")
    good = {"raw": _raw_message("stop"), "parsed": _Result(answer="ok"),
            "parsing_error": None}
    model = _model_returning([_unparsed("lengthlength"), good])

    with patch("fichero_server.llm.get_langchain_model", return_value=model):
        result = await chat_structured(prompt="hi", schema=_Result, config=cfg)

    assert result == _Result(answer="ok")
    assert model.with_structured_output.return_value.ainvoke.await_count == 2


@pytest.mark.asyncio
async def test_persistent_truncation_fails_once_with_error_kind():
    """A second identical truncation is a real failure — surfaced, classified,
    and NOT retried a third time."""
    cfg = LLMConfig(provider="openrouter", model="google/gemini-3.1-flash-lite")
    model = _model_returning([_unparsed("length"), _unparsed("length")])

    with patch("fichero_server.llm.get_langchain_model", return_value=model):
        with pytest.raises(StructuredCallEmptyError) as excinfo:
            await chat_structured(prompt="hi", schema=_Result, config=cfg)

    assert excinfo.value.error_kind == STRUCTURED_ERROR_TRUNCATED
    assert "error_kind=truncated" in str(excinfo.value)
    # Exactly two calls: the original and ONE raised-ceiling retry.
    assert model.with_structured_output.return_value.ainvoke.await_count == 2


@pytest.mark.asyncio
async def test_non_length_empty_result_does_not_retry():
    """finish_reason=stop with no parsed result is 'empty', not 'truncated' —
    re-asking costs tokens for the same nothing."""
    cfg = LLMConfig(provider="openrouter", model="google/gemini-3.1-flash-lite")
    model = _model_returning([_unparsed("stop")])

    with patch("fichero_server.llm.get_langchain_model", return_value=model):
        with pytest.raises(StructuredCallEmptyError) as excinfo:
            await chat_structured(prompt="hi", schema=_Result, config=cfg)

    assert excinfo.value.error_kind == STRUCTURED_ERROR_EMPTY
    assert model.with_structured_output.return_value.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_real_pydantic_model_is_pinned_to_non_streaming():
    """A real (pydantic) LangChain model must be copied with
    disable_streaming=True before with_structured_output — ambient streaming
    callbacks otherwise flip ainvoke into chunk streaming, whose merge doubles
    OpenRouter/Gemini metadata ('lengthlength') and double-counts usage."""

    class _FakePydModel(BaseModel):
        disable_streaming: bool = False

        def with_structured_output(self, schema, **kwargs):
            structured = MagicMock()
            structured.ainvoke = AsyncMock(
                return_value={
                    "raw": _raw_message("stop"),
                    "parsed": _Result(answer=f"streaming_disabled={self.disable_streaming}"),
                    "parsing_error": None,
                }
            )
            return structured

    cfg = LLMConfig(provider="openrouter", model="google/gemini-3.1-flash-lite")
    with patch(
        "fichero_server.llm.get_langchain_model", return_value=_FakePydModel()
    ):
        result = await chat_structured(prompt="hi", schema=_Result, config=cfg)

    assert result.answer == "streaming_disabled=True"
