"""Coverage for the key-people workflow tool."""

from __future__ import annotations

import asyncio

from fichero_server.workflows.tools import key_people as tool


def test_prompt_builder_toggles_context_section():
    with_context = tool.build_key_people_prompt({"max_people": 3, "include_context": True})
    without_context = tool.build_key_people_prompt({"max_people": 3, "include_context": False})

    assert "most important people" in with_context
    assert "Their role or title" in with_context
    assert "Their role or title" not in without_context


def test_key_people_forwards_metadata_and_defaults(monkeypatch):
    captured = {}

    async def fake_process_text(**kwargs):
        captured.update(kwargs)
        return {"key_people": []}

    monkeypatch.setattr(tool, "process_text", fake_process_text)

    result = asyncio.run(tool.key_people({"text": "Alice"}, {}, object()))

    assert result == {"key_people": []}
    assert captured["output_format"] == "json"
    assert captured["max_tokens"] == 2048
    assert captured["match_mode"] == "prefer"
    assert captured["metadata_field"] == "key_people"
