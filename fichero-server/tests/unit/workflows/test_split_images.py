"""Tests for the split_images workflow tool (#1394)."""

from __future__ import annotations

from pathlib import Path

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


def test_a_jpeg_splits_into_jpegs_by_default(tmp_path):
    """#5386: Split wrote PNG halves of a 3.4 MB JPEG photo (8.1 MB, 2.4x), so a 374-photo
    notebook corpus grew by gigabytes. A derived part keeps its source's format unless asked."""
    from PIL import Image
    from fichero_server.workflows.tools.split_images import split_image_file

    src = tmp_path / "spread.jpg"
    Image.new("RGB", (600, 400), "white").save(src, quality=85)
    out = split_image_file(src, tmp_path / "out")
    assert out["error"] is None
    assert [Path(p).suffix for p in out["outputs"]] == [".jpg", ".jpg"]
    asked = split_image_file(src, tmp_path / "png", output_format="png")
    assert [Path(p).suffix for p in asked["outputs"]] == [".png", ".png"]
