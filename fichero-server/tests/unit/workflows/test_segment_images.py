"""Tests for the segment_images workflow tool (#1391)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import Document, FileType, ImageEditChain
from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.tools.segment_images import segment_image_file, segment_images


def _write_two_regions(path):
    image = Image.new("RGB", (100, 60), "white")
    for x in range(10, 30):
        for y in range(10, 30):
            image.putpixel((x, y), (0, 0, 0))
    for x in range(65, 90):
        for y in range(20, 45):
            image.putpixel((x, y), (0, 0, 0))
    image.save(path)


def test_segment_image_file_writes_cropped_segment_derivatives(tmp_path):
    source = tmp_path / "scan.png"
    output_dir = tmp_path / "segments"
    _write_two_regions(source)
    before_bytes = source.read_bytes()

    result = segment_image_file(
        source,
        output_dir,
        threshold=5,
        min_area=100,
        max_segments=10,
        output_format="png",
    )

    assert source.read_bytes() == before_bytes
    assert result["error"] is None
    assert len(result["outputs"]) == 2
    assert [segment["bbox"] for segment in result["segments"]] == [
        [10, 10, 20, 20],
        [65, 20, 25, 25],
    ]

    with Image.open(result["outputs"][0]) as first:
        assert first.size == (20, 20)
    with Image.open(result["outputs"][1]) as second:
        assert second.size == (25, 25)


def test_segment_images_tool_is_registered():
    tool = get_tool("segment_images")
    tool_def = get_tool_def("segment_images")

    assert tool is not None
    assert tool_def is not None
    assert tool_def.name == "segment_images"
    assert tool_def.uses_llm is False


@pytest.mark.asyncio
async def test_segment_workflow_appends_preview_editor_operation(tmp_path):
    library_path = tmp_path / "Library.fichero"
    (library_path / "lance").mkdir(parents=True)
    (library_path / "storage").mkdir()
    db = db_manager.get_database(library_path)

    source = tmp_path / "scan.png"
    _write_two_regions(source)
    doc = Document(name="scan.png", path=str(source), file_type=FileType.image)
    db.save(doc)

    result = await segment_images(
        {
            "files": [str(source)],
            "documents": [doc.model_dump(mode="json")],
            "output_dir": str(tmp_path / "segments"),
            "threshold": 5,
            "min_area": 100,
            "max_segments": 10,
            "output_format": "png",
        },
        {"library_path": str(library_path)},
        LLMConfig(provider="test", model="test"),
    )

    chains = list(db.query(ImageEditChain, document_id=doc.id))
    assert len(chains) == 1
    assert chains[0].operations[0]["op"] == "segment"
    assert len(chains[0].operations[0]["segments"]) == 2
    assert result["image_edit_operations"][0]["document_id"] == doc.id
