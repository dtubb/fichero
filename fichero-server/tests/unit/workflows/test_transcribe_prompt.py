"""Prompt regressions for transcribe tool instructions."""

from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.transcribe import _build_prompt, transcribe


def test_transcribe_prompt_explicitly_preserves_diacritics():
    """#1397: accents/diacritics must be preserved exactly."""
    prompt = _build_prompt("es-CO", False)
    lowered = prompt.lower()
    assert "diacrit" in lowered
    assert "do not strip accents" in lowered


def test_transcribe_prompt_uses_uncertainty_markers():
    """#1398: prompt must ask for honest uncertainty markers."""
    prompt = _build_prompt("es-CO", False)
    assert "[ilegible]" in prompt
    assert "[uncertain]" in prompt


@pytest.mark.asyncio
async def test_transcribe_forwards_thinking_mode():
    with patch(
        "fichero_server.workflows.tools.transcribe.process_vision",
        new=AsyncMock(return_value={"text": "draft"}),
    ) as process_vision:
        await transcribe(
            {"files": ["page.png"], "thinking_mode": "medium"},
            {"library_path": "/library.fichero"},
            LLMConfig(provider="test", model="test"),
        )

    assert process_vision.await_args.kwargs["thinking_mode"] == "medium"


@pytest.mark.asyncio
async def test_transcribe_only_forces_images_for_specialist_passes():
    for inputs, expected in (
        ({"files": ["page.png"]}, False),
        ({"files": ["page.png"], "prompt": "Specialist pass"}, True),
        ({"files": ["page.png"], "update_page_content": False}, True),
    ):
        with patch(
            "fichero_server.workflows.tools.transcribe.process_vision",
            new=AsyncMock(return_value={"text": "result"}),
        ) as process_vision:
            await transcribe(
                inputs,
                {"library_path": "/library.fichero"},
                LLMConfig(provider="test", model="test"),
            )

        assert process_vision.await_args.kwargs["force_ocr"] is expected
