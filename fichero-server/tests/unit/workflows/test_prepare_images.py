"""Tests for the prepare_images workflow tool (#1390)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.tools.prepare_images import prepare_image_file


def _save_oriented_jpeg(path, orientation: int) -> None:
    image = Image.new("RGB", (10, 20), color="white")
    exif = Image.Exif()
    exif[274] = orientation
    image.save(path, format="JPEG", exif=exif)


def test_prepare_image_file_applies_exif_orientation_without_touching_source(tmp_path):
    source = tmp_path / "scan.jpg"
    output_dir = tmp_path / "prepared"
    _save_oriented_jpeg(source, orientation=6)

    before_bytes = source.read_bytes()

    result = prepare_image_file(
        source,
        output_dir,
        output_format="png",
        compression_quality=90,
        grayscale=False,
        autocontrast=False,
    )

    assert source.read_bytes() == before_bytes
    assert result["error"] is None
    assert result["outputs"] == [str(output_dir / "scan.png")]
    assert result["details"]["total_pages"] == 1
    assert result["details"]["pages"][0]["original_size"] == [10, 20]
    assert result["details"]["pages"][0]["prepared_size"] == [20, 10]
    assert result["details"]["pages"][0]["rotation_applied"]["applied"] is True

    with Image.open(result["outputs"][0]) as prepared:
        assert prepared.size == (20, 10)


def test_prepare_images_tool_is_registered():
    tool = get_tool("prepare_images")
    tool_def = get_tool_def("prepare_images")

    assert tool is not None
    assert tool_def is not None
    assert tool_def.name == "prepare_images"
    assert tool_def.uses_llm is False
