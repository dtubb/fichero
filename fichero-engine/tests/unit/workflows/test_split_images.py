"""Tests for the split_images workflow tool (#1394)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero.llm import LLMConfig
from fichero.workflows.registry import get_tool, get_tool_def
from fichero.workflows.tools.split_images import split_image_file, split_images


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


def test_split_image_file_auto_detects_two_page_spread(tmp_path):
    pytest.importorskip("cv2")
    source = tmp_path / "marshall_spread.png"
    output_dir = tmp_path / "split"
    image = Image.new("RGB", (1200, 600), color="white")
    for x in range(590, 610):
        for y in range(20, 580):
            image.putpixel((x, y), (0, 0, 0))
    for x in range(120, 500):
        for y in range(160, 440):
            if (x + y) % 17 == 0:
                image.putpixel((x, y), (40, 40, 40))
    for x in range(720, 1100):
        for y in range(160, 440):
            if (x + y) % 19 == 0:
                image.putpixel((x, y), (40, 40, 40))
    image.save(source)

    result = split_image_file(
        source,
        output_dir,
        strategy="auto",
        output_format="png",
    )

    assert result["error"] is None
    assert result["details"]["split_mode"] == "auto"
    assert len(result["outputs"]) == 2
    assert result["parts"][0]["debug"]["should_split"] is True
    with Image.open(result["outputs"][0]) as left, Image.open(result["outputs"][1]) as right:
        assert 560 <= left.width <= 640
        assert 560 <= right.width <= 640
        assert left.height == right.height == 600


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
            "strategy": "grid",
            "output_format": "png",
        },
        {},
        LLMConfig(provider="test", model="test"),
    )

    assert result["error"] is None
    assert result["count"] == 4
    assert len(result["parts"]) == 4
