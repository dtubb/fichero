"""Tests for detect_ai_text workflow tool (#753)."""

from __future__ import annotations

import pytest

import fichero_server.workflows.tools  # noqa: F401
from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import TOOL_DEFS
from fichero_server.workflows.tools.detect_ai_text import detect_ai_text


@pytest.mark.asyncio
async def test_detect_ai_text_returns_analysis_payload():
    result = await detect_ai_text(
        {"text": "As an AI assistant, in conclusion this text is highly structured."},
        {},
        LLMConfig(provider="openai", model="gpt-4o-mini"),
    )
    assert "analysis" in result
    assert result["analysis"]["model"] == "heuristic-v1"
    assert result["analysis"]["verdict"] in {"likely_ai", "likely_human"}


def test_detect_ai_text_registered_tool_schema():
    tool = TOOL_DEFS["detect_ai_text"]
    assert tool.display_name == "Detect AI Text"
    assert "threshold" in tool.config_schema
    assert tool.config_schema["threshold"]["default"] == 0.55
