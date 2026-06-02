"""Tests for the crop_images workflow tool (#1595)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero.llm import LLMConfig
from fichero.workflows.registry import get_tool, get_tool_def
from fichero.workflows.tools.crop_images import crop_image_file, crop_images


def test_crop_image_file_trims_black_photocopy_border(tmp_path):
    pytest.importorskip("cv2")
    source = tmp_path / "photocopy.png"
    output_dir = tmp_path / "cropped"
    image = Image.new("RGB", (160, 120), color="white")
    for x in range(4, 70):
        for y in range(8, 112):
            image.putpixel((x, y), (0, 0, 0))
    for x in range(70, 154):
        for y in range(8, 100):
            image.putpixel((x, y), (238, 232, 214))
    image.save(source)
    before_bytes = source.read_bytes()

    result = crop_image_file(
        source,
        output_dir,
        method="photocopy",
        padding=0,
        output_format="png",
    )

    assert source.read_bytes() == before_bytes
    assert result["error"] is None
    assert result["details"]["method"] == "photocopy"
    with Image.open(result["outputs"][0]) as cropped:
        assert cropped.width < 120
        assert cropped.height <= 120


def test_crop_images_tool_is_registered():
    tool = get_tool("crop_images")
    tool_def = get_tool_def("crop_images")

    assert tool is not None
    assert tool_def is not None
    assert tool_def.name == "crop_images"
    assert tool_def.uses_llm is False


@pytest.mark.asyncio
async def test_crop_images_workflow_returns_output_files(tmp_path):
    pytest.importorskip("cv2")
    source = tmp_path / "photocopy.png"
    Image.new("RGB", (80, 60), color="white").save(source)

    result = await crop_images(
        {
            "files": [str(source)],
            "output_dir": str(tmp_path / "cropped"),
            "method": "photocopy",
            "output_format": "png",
        },
        {},
        LLMConfig(provider="test", model="test"),
    )

    assert result["error"] is None
    assert result["count"] == 1
    assert result["output_files"]
