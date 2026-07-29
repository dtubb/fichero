"""Tests for the fuzzy_clean_images workflow tool (#1389)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import Document, FileType, ImageEditChain
from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.tools.fuzzy_clean_images import fuzzy_clean_image_file, fuzzy_clean_images


def test_fuzzy_clean_image_file_despeckles_without_touching_source(tmp_path):
    source = tmp_path / "scan.png"
    output_dir = tmp_path / "cleaned"
    image = Image.new("RGB", (9, 9), color=(128, 128, 128))
    image.putpixel((4, 4), (0, 0, 0))
    image.save(source)
    before_bytes = source.read_bytes()

    result = fuzzy_clean_image_file(
        source,
        output_dir,
        despeckle_radius=3,
        output_format="png",
    )

    assert source.read_bytes() == before_bytes
    assert result["error"] is None
    assert result["outputs"] == [str(output_dir / "scan.png")]
    assert result["details"]["despeckle_radius"] == 3

    with Image.open(result["outputs"][0]) as cleaned:
        assert cleaned.getpixel((4, 4))[0] > 0


def test_fuzzy_clean_images_tool_is_registered():
    tool = get_tool("fuzzy_clean_images")
    tool_def = get_tool_def("fuzzy_clean_images")

    assert tool is not None
    assert tool_def is not None
    assert tool_def.name == "fuzzy_clean_images"
    assert tool_def.uses_llm is False


@pytest.mark.asyncio
async def test_fuzzy_clean_workflow_appends_preview_editor_operation(tmp_path):
    library_path = tmp_path / "Library.fichero"
    (library_path / "lance").mkdir(parents=True)
    (library_path / "storage").mkdir()
    db = db_manager.get_database(library_path)

    source = tmp_path / "scan.png"
    Image.new("RGB", (9, 9), color=(128, 128, 128)).save(source)
    doc = Document(name="scan.png", path=str(source), file_type=FileType.image)
    db.save(doc)

    result = await fuzzy_clean_images(
        {
            "files": [str(source)],
            "documents": [doc.model_dump(mode="json")],
            "output_dir": str(tmp_path / "cleaned"),
            "despeckle_radius": 3,
            "output_format": "png",
        },
        {"library_path": str(library_path)},
        LLMConfig(provider="test", model="test"),
    )

    chains = list(db.query(ImageEditChain, document_id=doc.id))
    assert len(chains) == 1
    assert chains[0].operations[0]["op"] == "fuzzy_clean"
    assert chains[0].operations[0]["params"] == {"despeckle_radius": 3, "background_clean": True}
    assert result["image_edit_operations"][0]["document_id"] == doc.id
