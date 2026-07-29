"""Tests for the recombine_segments workflow tool (#1392)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.tools.recombine_segments import recombine_segment_files, recombine_segments


def _write_segment(path, size, color):
    Image.new("RGB", size, color=color).save(path)


def test_recombine_segment_files_creates_contact_sheet(tmp_path):
    seg1 = tmp_path / "seg1.png"
    seg2 = tmp_path / "seg2.png"
    output_dir = tmp_path / "combined"
    _write_segment(seg1, (20, 10), "red")
    _write_segment(seg2, (10, 20), "blue")

    result = recombine_segment_files(
        [str(seg1), str(seg2)],
        output_dir,
        layout="horizontal",
        padding=5,
        output_format="png",
    )

    assert result["error"] is None
    assert result["output_files"] == [str(output_dir / "recombined.png")]
    assert result["details"]["segment_count"] == 2
    assert result["details"]["layout"] == "horizontal"

    with Image.open(result["output_files"][0]) as combined:
        assert combined.size == (35, 20)


def test_recombine_segments_tool_is_registered():
    tool = get_tool("recombine_segments")
    tool_def = get_tool_def("recombine_segments")

    assert tool is not None
    assert tool_def is not None
    assert tool_def.name == "recombine_segments"
    assert tool_def.uses_llm is False


@pytest.mark.asyncio
async def test_recombine_segments_workflow_returns_output_files(tmp_path):
    seg1 = tmp_path / "seg1.png"
    seg2 = tmp_path / "seg2.png"
    _write_segment(seg1, (20, 10), "red")
    _write_segment(seg2, (10, 20), "blue")

    result = await recombine_segments(
        {
            "files": [str(seg1), str(seg2)],
            "output_dir": str(tmp_path / "combined"),
            "layout": "vertical",
            "padding": 2,
            "output_format": "png",
        },
        {},
        LLMConfig(provider="test", model="test"),
    )

    assert result["error"] is None
    assert result["count"] == 1
    with Image.open(result["output_files"][0]) as combined:
        assert combined.size == (20, 32)
