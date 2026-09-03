"""extract: a run where EVERY file fails must say so at the top level.

Found by the 2026-09-03 tool sweep: Apple Vision refused every page and
`extract` still returned ok — empty text, empty value, no error key. The
per-file errors lived only inside `results`, which nothing downstream reads
as a failure signal.
"""

from __future__ import annotations

import pytest

import fichero_server.workflows.tools  # noqa: F401  (registers all tools)
from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools import extract as extract_module


@pytest.mark.asyncio
async def test_all_files_failed_surfaces_top_level_error(monkeypatch, tmp_path):
    img = tmp_path / "page.jpg"
    img.write_bytes(b"fake")

    async def failing_vision(images, prompt, config, **kwargs):
        raise ValueError("provider refused")

    monkeypatch.setattr(extract_module, "vision", failing_vision)

    out = await extract_module.extract(
        {"files": [str(img)], "save_to_db": False},
        {"library_path": "", "input_files": []},
        LLMConfig(provider="apple", model="apple-vision"),
    )

    assert out["error"], "all-files-failed run must carry a top-level error"
    assert "provider refused" in out["error"]
    assert out["results"][0]["error"]


@pytest.mark.asyncio
async def test_partial_failure_stays_ok(monkeypatch, tmp_path):
    """One good file among failures keeps the run ok — partial data is data."""
    good = tmp_path / "good.jpg"
    bad = tmp_path / "bad.jpg"
    good.write_bytes(b"fake")
    bad.write_bytes(b"fake")

    calls = {"n": 0}

    async def flaky_vision(images, prompt, config, **kwargs):
        # One vision call per file; the image paths handed over are resized
        # temp copies, so fail by call ORDER (second file), not by name.
        calls["n"] += 1
        if calls["n"] > 1:
            raise ValueError("provider refused")
        return '{"description": "a page", "tags": ["diary"]}'

    monkeypatch.setattr(extract_module, "vision", flaky_vision)

    out = await extract_module.extract(
        {"files": [str(good), str(bad)], "save_to_db": False},
        {"library_path": "", "input_files": []},
        LLMConfig(provider="apple", model="apple-vision"),
    )

    assert not out.get("error")
    assert any(r.get("error") for r in out["results"])
    assert any(not r.get("error") for r in out["results"])
