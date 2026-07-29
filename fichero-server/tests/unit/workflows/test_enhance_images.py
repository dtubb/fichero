"""Tests for the enhance_images workflow tool (#1388)."""

from __future__ import annotations

import pytest

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import Document, FileType, ImageEditChain

pytest.importorskip("PIL")

from PIL import Image

from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.tools.enhance_images import enhance_image_file, enhance_images


def test_enhance_image_file_writes_derivative_without_touching_source(tmp_path):
    source = tmp_path / "scan.png"
    output_dir = tmp_path / "enhanced"
    Image.new("RGB", (10, 20), color=(120, 120, 120)).save(source)
    before_bytes = source.read_bytes()

    result = enhance_image_file(
        source,
        output_dir,
        contrast=1.5,
        sharpness=1.25,
        denoise=True,
        output_format="png",
    )

    assert source.read_bytes() == before_bytes
    assert result["error"] is None
    assert result["outputs"] == [str(output_dir / "scan.png")]
    assert result["details"]["contrast"] == 1.5
    assert result["details"]["sharpness"] == 1.25
    assert result["details"]["denoise"] is True
    assert result["details"]["original_size"] == [10, 20]
    assert result["details"]["prepared_size"] == [10, 20]

    with Image.open(result["outputs"][0]) as enhanced:
        assert enhanced.size == (10, 20)


def test_enhance_images_tool_is_registered():
    tool = get_tool("enhance_images")
    tool_def = get_tool_def("enhance_images")

    assert tool is not None
    assert tool_def is not None
    assert tool_def.name == "enhance_images"
    assert tool_def.uses_llm is False


@pytest.mark.asyncio
async def test_enhance_images_workflow_appends_preview_editor_operation(tmp_path):
    library_path = tmp_path / "Library.fichero"
    (library_path / "lance").mkdir(parents=True)
    (library_path / "storage").mkdir()
    db = db_manager.get_database(library_path)

    source = tmp_path / "scan.png"
    Image.new("RGB", (10, 20), color=(120, 120, 120)).save(source)
    doc = Document(name="scan.png", path=str(source), file_type=FileType.image)
    db.save(doc)

    result = await enhance_images(
        {
            "files": [str(source)],
            "documents": [doc.model_dump(mode="json")],
            "output_dir": str(tmp_path / "enhanced"),
            "contrast": 1.5,
            "sharpness": 1.25,
            "denoise": True,
            "output_format": "png",
        },
        {"library_path": str(library_path)},
        LLMConfig(provider="test", model="test"),
    )

    chains = list(db.query(ImageEditChain, document_id=doc.id))
    assert len(chains) == 1
    assert chains[0].operations[0]["op"] == "enhance"
    assert chains[0].operations[0]["params"] == {
        "brightness": 1.0,
        "contrast": 1.5,
        "sharpen": 1.25,
        "auto_levels": False,
        "denoise": True,
    }
    assert result["image_edit_operations"][0]["document_id"] == doc.id
