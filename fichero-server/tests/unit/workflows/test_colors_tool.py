"""Coverage for the dominant-colors workflow tool."""

from __future__ import annotations

import asyncio

from fichero_server.workflows.tools import colors as tool


def test_build_colors_prompt_supports_formats_and_defaults():
    prompt = tool.build_colors_prompt({"color_count": 3, "format": "rgb"})
    assert "3 most dominant colors" in prompt
    assert 'rgb(255, 87, 51)' in prompt
    assert '"mood"' in prompt
    assert "#FF5733" in tool.build_colors_prompt({"format": "unknown"})


def test_colors_forwards_inputs_to_vision_processor(monkeypatch):
    captured = {}

    async def fake_process_vision(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr(tool, "process_vision", fake_process_vision)
    result = asyncio.run(
        tool.colors(
            {"files": ["image.jpg"], "color_count": 7, "format": "name", "save_to_db": False},
            {"library_path": "/tmp/library", "task_id": "task-1"},
            None,
        )
    )

    assert result == {"ok": True}
    assert captured["files"] == ["image.jpg"]
    assert captured["library_path"] == "/tmp/library"
    assert captured["task_id"] == "task-1"
    assert captured["output_format"] == "json"
    assert captured["metadata_field"] == "colors"
    assert "7 most dominant colors" in captured["prompt"]
