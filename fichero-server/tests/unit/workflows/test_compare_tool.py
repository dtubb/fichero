"""Coverage for compare tool prompt and input validation."""

from __future__ import annotations

import asyncio

from fichero_server.workflows.tools import compare as tool


def test_build_compare_prompt_handles_focus_and_aspects():
    prompt = tool.build_compare_prompt({"focus": "differences", "aspects": ["layout", "text"]})
    assert "DIFFERENT" in prompt
    assert "layout, text" in prompt
    assert "similarities" not in prompt.lower().split("consider", 1)[0]


def test_compare_requires_two_files_even_when_single_path_string():
    result = asyncio.run(tool.compare({"files": "one.png"}, {}, None))
    assert result["error"] == "Compare requires at least 2 images"
    assert result["results"] == []
