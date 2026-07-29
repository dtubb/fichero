"""Tests for the rotate_images workflow tool (#1387)."""

from __future__ import annotations

import pytest

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import Document, FileType, ImageEditChain

pytest.importorskip("PIL")

from PIL import Image

from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.tools.rotate_images import rotate_image_file, rotate_images


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


@pytest.mark.asyncio
async def test_rotate_images_workflow_appends_preview_editor_operation(tmp_path):
    library_path = tmp_path / "Library.fichero"
    (library_path / "lance").mkdir(parents=True)
    (library_path / "storage").mkdir()
    db = db_manager.get_database(library_path)

    source = tmp_path / "scan.png"
    Image.new("RGB", (10, 20), color="white").save(source)
    doc = Document(name="scan.png", path=str(source), file_type=FileType.image)
    db.save(doc)

    result = await rotate_images(
        {
            "files": [str(source)],
            "documents": [doc.model_dump(mode="json")],
            "output_dir": str(tmp_path / "rotated"),
            "rotation_degrees": 90,
            "output_format": "png",
        },
        {"library_path": str(library_path)},
        LLMConfig(provider="test", model="test"),
    )

    chains = list(db.query(ImageEditChain, document_id=doc.id))
    assert len(chains) == 1
    assert chains[0].operations[0]["op"] == "rotate"
    assert chains[0].operations[0]["params"] == {"angle": -90, "expand": True}
    assert result["image_edit_operations"][0]["document_id"] == doc.id
