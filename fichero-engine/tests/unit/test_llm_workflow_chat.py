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
async def test_chat_workflow_propagates_errors():
    config = LLMConfig(provider="openai", model="gpt-4o-mini")

    with patch(
        "fichero.llm.chat",
        new=AsyncMock(side_effect=ValueError("bad provider config")),
    ):
        with pytest.raises(ValueError, match="bad provider config"):
            await chat_workflow("hello", config)
