"""Coverage for style classification workflow tool."""

from __future__ import annotations

import asyncio

from fichero_server.workflows.tools import style as tool


def test_style_prompt_changes_with_detail_flag():
    detailed = tool.build_style_prompt({"styles": ["map", "photo"], "include_details": True})
    concise = tool.build_style_prompt({"styles": ["map", "photo"], "include_details": False})
    assert "Choose ONE primary style from: map, photo" in detailed
    assert '"features"' in detailed
    assert "Return ONLY the style type" in concise


def test_style_selects_choice_output_without_details(monkeypatch):
    captured = {}

    async def fake_process_vision(**kwargs):
        captured.update(kwargs)
        return {"value": "map"}

    monkeypatch.setattr(tool, "process_vision", fake_process_vision)
    result = asyncio.run(tool.style({"styles": ["map"], "include_details": False}, {}, None))

    assert result == {"value": "map"}
    assert captured["output_format"] == "choice"
    assert captured["reference_values"] == {"style": ["map"]}
    assert captured["metadata_field"] == "style"
