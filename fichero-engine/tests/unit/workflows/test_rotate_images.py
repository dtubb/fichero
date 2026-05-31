"""Tests for the rotate_images workflow tool (#1387)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero.workflows.registry import get_tool, get_tool_def
from fichero.workflows.tools.rotate_images import rotate_image_file


def test_rotate_image_file_rotates_without_touching_source(tmp_path):
    source = tmp_path / "scan.png"
    output_dir = tmp_path / "rotated"
    Image.new("RGB", (10, 20), color="white").save(source)
    before_bytes = source.read_bytes()

    result = rotate_image_file(
        source,
        output_dir,
        rotation_degrees=90,
        auto_orient=False,
        output_format="png",
    )

    assert source.read_bytes() == before_bytes
    assert result["error"] is None
    assert result["outputs"] == [str(output_dir / "scan.png")]
    assert result["details"]["rotation_degrees"] == 90
    assert result["details"]["original_size"] == [10, 20]
    assert result["details"]["prepared_size"] == [20, 10]

    with Image.open(result["outputs"][0]) as rotated:
        assert rotated.size == (20, 10)


def test_rotate_images_tool_is_registered():
    tool = get_tool("rotate_images")
    tool_def = get_tool_def("rotate_images")

    assert tool is not None
    assert tool_def is not None
    assert tool_def.name == "rotate_images"
    assert tool_def.uses_llm is False
