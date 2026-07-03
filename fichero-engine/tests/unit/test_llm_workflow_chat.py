"""Unit tests for the central workflow LLM dispatcher."""

import pytest
from unittest.mock import AsyncMock, patch

from pydantic import BaseModel

from fichero.llm import LLMConfig, chat_workflow


class _StructuredReply(BaseModel):
    answer: str


@pytest.mark.asyncio
async def test_chat_workflow_uses_unstructured_chat():
    config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch("fichero.llm.chat", new=AsyncMock(return_value="plain reply")) as mock_chat:
        result = await chat_workflow(
            [{"role": "user", "content": "hello"}],
            config,
        )

    assert result == "plain reply"
    assert mock_chat.await_count == 1


@pytest.mark.asyncio
async def test_chat_workflow_uses_structured_chat():
    config = LLMConfig(provider="openai", model="gpt-4o-mini")
    structured = _StructuredReply(answer="done")

    with patch(
        "fichero.llm.chat_structured",
        new=AsyncMock(return_value=structured),
    ) as mock_chat_structured:
        result = await chat_workflow(
            "extract this",
            config,
            system="system",
            schema=_StructuredReply,
        )

    assert result == structured
    assert mock_chat_structured.await_count == 1


@pytest.mark.asyncio
async def test_chat_workflow_uses_tool_chat_and_preserves_shape():
    config = LLMConfig(provider="openai", model="gpt-4o-mini")
    tool_result = {
        "content": "",
        "tool_calls": [{"id": "call-1", "name": "search", "args": {"q": "room"}}],
    }

    with patch(
        "fichero.llm.chat_with_tools",
        new=AsyncMock(return_value=tool_result),
    ) as mock_chat_with_tools:
        result = await chat_workflow(
            [{"role": "user", "content": "search for room"}],
            config,
            tools=[{"type": "function", "function": {"name": "search"}}],
        )

    assert result == tool_result
    assert isinstance(result, dict)
    assert result["tool_calls"][0]["name"] == "search"
    assert mock_chat_with_tools.await_count == 1


@pytest.mark.asyncio
async def test_chat_workflow_propagates_errors():
    config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch(
        "fichero.llm.chat",
        new=AsyncMock(side_effect=ValueError("bad provider config")),
    ):
        with pytest.raises(ValueError, match="bad provider config"):
            await chat_workflow("hello", config)


@pytest.mark.asyncio
async def test_chat_workflow_propagates_structured_errors():
    config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch(
        "fichero.llm.chat_structured",
        new=AsyncMock(side_effect=RuntimeError("structured provider failure")),
    ):
        with pytest.raises(RuntimeError, match="structured provider failure"):
            await chat_workflow("hello", config, schema=_StructuredReply)


@pytest.mark.asyncio
async def test_chat_workflow_propagates_tool_errors():
    config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch(
        "fichero.llm.chat_with_tools",
        new=AsyncMock(side_effect=RuntimeError("tool provider failure")),
    ):
        with pytest.raises(RuntimeError, match="tool provider failure"):
            await chat_workflow(
                [{"role": "user", "content": "search"}],
                config,
                tools=[{"type": "function", "function": {"name": "search"}}],
            )
