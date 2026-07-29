"""Tests for the split_images workflow tool (#1394)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.tools.split_images import split_image_file, split_images


def test_split_image_file_writes_grid_tiles_without_touching_source(tmp_path):
    source = tmp_path / "scan.png"
    output_dir = tmp_path / "split"
    Image.new("RGB", (40, 20), color="white").save(source)
    before_bytes = source.read_bytes()

    result = split_image_file(
        source,
        output_dir,
        rows=1,
        columns=2,
        output_format="png",
    )

    assert source.read_bytes() == before_bytes
    assert result["error"] is None
    assert len(result["outputs"]) == 2
    assert [part["bbox"] for part in result["parts"]] == [
        [0, 0, 20, 20],
        [20, 0, 20, 20],
    ]
    with Image.open(result["outputs"][0]) as first:
        assert first.size == (20, 20)


def test_split_images_tool_is_registered():
    tool = get_tool("split_images")
    tool_def = get_tool_def("split_images")

    assert tool is not None
    assert tool_def is not None
    assert tool_def.name == "split_images"
    assert tool_def.uses_llm is False


@pytest.mark.asyncio
async def test_split_images_workflow_returns_output_files(tmp_path):
    source = tmp_path / "scan.png"
    Image.new("RGB", (40, 20), color="white").save(source)

    result = await split_images(
        {
            "files": [str(source)],
            "output_dir": str(tmp_path / "split"),
            "rows": 2,
            "columns": 2,
            "output_format": "png",
        },
        {},
        LLMConfig(provider="test", model="test"),
    )

    assert result["error"] is None
    assert result["count"] == 4
    assert len(result["parts"]) == 4
