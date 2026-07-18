"""Coverage for the custom vision analysis tool."""

from __future__ import annotations

import asyncio

from fichero.workflows.tools import analyze as tool


def test_analyze_returns_structured_error_for_empty_prompt():
    result = asyncio.run(tool.analyze({"prompt": ""}, {}, None))
    assert result["error"] == "No prompt provided"
    assert result["results"] == []


def test_analyze_forwards_shared_vision_options(monkeypatch):
    captured = {}

    async def fake_process_vision(**kwargs):
        captured.update(kwargs)
        return {"text": "done"}

    monkeypatch.setattr(tool, "process_vision", fake_process_vision)
    result = asyncio.run(
        tool.analyze(
            {
                "files": ["scan.png"],
                "prompt": "Describe the seal",
                "output_format": "json",
                "choices": ["yes", "no"],
                "save_to_db": False,
            },
            {"library_path": "/tmp/library", "task_id": "task-2"},
            None,
        )
    )

    assert result == {"text": "done"}
    assert captured["files"] == ["scan.png"]
    assert captured["prompt"] == "Describe the seal"
    assert captured["output_format"] == "json"
    assert captured["output_options"]["choices"] == ["yes", "no"]
    assert captured["max_image_dimension"] == 2048
    assert captured["metadata_field"] is None
