"""Tests for the text-format passthrough in process_vision (#884).

Locks the behaviour: when Transcribe (or any vision tool) receives a
.md/.txt/etc. file, it reads the file directly instead of sending the
bytes to the vision LLM. Without this, Catalogue (Mixed) on a folder
containing .md crashes the vision API with 'cannot identify image file'.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from fichero.llm import LLMConfig
from fichero.workflows.tools.vision_base import VisionToolConfig, process_vision


def _make_llm_config() -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")


def _tool_config() -> VisionToolConfig:
    return VisionToolConfig(
        artifact_type="transcription",
        update_page_content=True,
        trigger_embedding=False,
        supports_apple_vision=True,
    )


@pytest.mark.asyncio
async def test_markdown_file_returns_its_text_without_vision_call(tmp_path: Path) -> None:
    """A .md file should round-trip its content via the fast path.

    If the fast path didn't fire the function would try to lazy-import
    `vision` and POST the file bytes to a vision LLM — which is exactly
    the #884 crash we're locking out.
    """
    md_file = tmp_path / "notes.md"
    md_file.write_text("# Heading\n\nBody content.\n", encoding="utf-8")

    with patch(
        "fichero.workflows.tools.vision_base.save_artifact",
        new=AsyncMock(return_value=None),
    ):
        result = await process_vision(
            files=[str(md_file)],
            documents=[],
            prompt="Transcribe.",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    assert "Heading" in result["text"]
    assert "Body content" in result["text"]
    assert result["texts"] == [result["text"]]


@pytest.mark.asyncio
async def test_all_text_format_suffixes_passthrough(tmp_path: Path) -> None:
    """Every suffix in TEXT_FORMATS hits the fast path with non-empty output."""
    suffixes = [".txt", ".md", ".markdown", ".rst", ".html", ".htm", ".xml", ".csv"]
    with patch(
        "fichero.workflows.tools.vision_base.save_artifact",
        new=AsyncMock(return_value=None),
    ):
        for suffix in suffixes:
            file = tmp_path / f"sample{suffix}"
            file.write_text(f"content-{suffix}", encoding="utf-8")
            result = await process_vision(
                files=[str(file)],
                documents=[],
                prompt="x",
                llm_config=_make_llm_config(),
                library_path="",
                task_id=None,
                tool_config=_tool_config(),
                vision_mode="llm",
            )
            assert f"content-{suffix}" in result["text"], suffix


@pytest.mark.asyncio
async def test_save_to_db_false_skips_artifact_persistence(tmp_path: Path) -> None:
    """When save_to_db=False, the artifact write is not attempted."""
    md_file = tmp_path / "n.md"
    md_file.write_text("hello", encoding="utf-8")

    with patch(
        "fichero.workflows.tools.vision_base.save_artifact",
        new=AsyncMock(return_value="artifact-id"),
    ) as mock_save:
        result = await process_vision(
            files=[str(md_file)],
            documents=[],
            prompt="x",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
            save_to_db=False,
        )

    assert mock_save.await_count == 0
    assert result["text"] == "hello"
