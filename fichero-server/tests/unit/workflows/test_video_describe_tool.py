"""Contract coverage for the video description workflow tool."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools import video_describe as tool


@pytest.mark.parametrize(
    ("detail", "expected"),
    [("brief", "brief summary"), ("detailed", "scenes, actions"), ("comprehensive", "scene transitions")],
)
def test_video_describe_prompt_selects_detail_and_focus(detail, expected):
    prompt = tool.build_video_describe_prompt({"detail_level": detail, "focus": "captions"})
    assert expected in prompt
    assert "Focus particularly on: captions" in prompt


@pytest.mark.asyncio
async def test_video_describe_forwards_video_and_persistence_options(monkeypatch):
    process = AsyncMock(return_value={"text": "description", "artifacts": ["a1"]})
    monkeypatch.setattr(tool, "process_video", process)

    result = await tool.video_describe(
        {
            "files": ["movie.mov"], "documents": [{"id": "doc-1"}], "extract_audio": False,
            "frame_sample_rate": 3, "max_frames": 4, "max_image_dimension": 512,
            "whisper_model_size": "small", "detail_level": "brief", "focus": "speaker",
            "temperature": 0.1, "max_tokens": 80, "output_format": "json",
            "choices": ["x"], "max_words": 10, "max_items": 2, "save_to_db": False,
            "save_to_file": True, "metadata_field": "video_notes",
        },
        {"library_path": "/tmp/library.fichero", "task_id": "task-1"},
        LLMConfig(provider="test", model="test"),
    )

    assert result["artifacts"] == ["a1"]
    kwargs = process.await_args.kwargs
    assert kwargs["extract_audio"] is False and kwargs["frame_sample_rate"] == 3
    assert kwargs["max_frames"] == 4 and kwargs["whisper_model_size"] == "small"
    assert "brief summary" in kwargs["prompt"] and "speaker" in kwargs["prompt"]
    assert kwargs["save_to_db"] is False and kwargs["save_to_file_flag"] is True
    assert kwargs["metadata_field"] == "video_notes"


@pytest.mark.asyncio
async def test_video_describe_uses_state_files_explicit_prompt_and_defaults(monkeypatch):
    process = AsyncMock(return_value={"error": "provider unavailable", "artifacts": []})
    monkeypatch.setattr(tool, "process_video", process)
    result = await tool.video_describe(
        {"prompt": "Use exactly this prompt"}, {"input_files": ["fallback.mov"]}, LLMConfig(provider="test", model="test")
    )
    assert result["error"] == "provider unavailable"
    kwargs = process.await_args.kwargs
    assert kwargs["files"] == ["fallback.mov"] and kwargs["prompt"] == "Use exactly this prompt"
    assert kwargs["extract_audio"] is True and kwargs["max_frames"] == 10
    assert kwargs["metadata_field"] == "description"
