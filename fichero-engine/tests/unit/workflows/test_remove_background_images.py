"""Tests for the remove_background_images workflow tool (#1393)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero.db import db_manager
from fichero.llm import LLMConfig
from fichero.models import Document, FileType, ImageEditChain
from fichero.workflows.registry import get_tool, get_tool_def
from fichero.workflows.tools.remove_background_images import (
    remove_background_image_file,
    remove_background_images,
)


def _write_foreground(path):
    image = Image.new("RGB", (20, 20), color="white")
    for x in range(6, 14):
        for y in range(6, 14):
            image.putpixel((x, y), (0, 0, 0))
    image.save(path)


def test_remove_background_image_file_writes_alpha_derivative(tmp_path):
    source = tmp_path / "scan.png"
    output_dir = tmp_path / "background_removed"
    _write_foreground(source)
    before_bytes = source.read_bytes()

    result = remove_background_image_file(
        source,
        output_dir,
        method="threshold",
        threshold=5,
        output_format="png",
    )

    assert source.read_bytes() == before_bytes
    assert result["error"] is None
    assert result["outputs"] == [str(output_dir / "scan.png")]
    assert result["details"]["method"] == "threshold"

    with Image.open(result["outputs"][0]) as cleaned:
        assert cleaned.mode == "RGBA"
        assert cleaned.getpixel((0, 0))[3] == 0
        assert cleaned.getpixel((10, 10))[3] == 255


def test_remove_background_opencv_crops_black_photocopy_margins(tmp_path):
    pytest.importorskip("cv2")
    source = tmp_path / "saladin_like.png"
    output_dir = tmp_path / "background_removed"
    image = Image.new("RGB", (120, 100), color="black")
    for x in range(24, 96):
        for y in range(18, 82):
            image.putpixel((x, y), (232, 226, 208))
    image.save(source)

    result = remove_background_image_file(
        source,
        output_dir,
        method="opencv",
        output_format="png",
    )

    assert result["error"] is None
    assert result["details"]["method"] == "opencv"
    with Image.open(result["outputs"][0]) as cleaned:
        assert cleaned.mode == "RGBA"
        assert cleaned.width < 100
        assert cleaned.height < 90
        assert cleaned.getbbox() is not None


def test_remove_background_images_tool_is_registered():
    tool = get_tool("remove_background_images")
    tool_def = get_tool_def("remove_background_images")

    assert tool is not None
    assert tool_def is not None
    assert tool_def.name == "remove_background_images"
    assert tool_def.uses_llm is False


@pytest.mark.asyncio
async def test_remove_background_workflow_appends_preview_editor_operation(tmp_path):
    library_path = tmp_path / "Library.fichero"
    (library_path / "lance").mkdir(parents=True)
    (library_path / "storage").mkdir()
    db = db_manager.get_database(library_path)

    source = tmp_path / "scan.png"
    _write_foreground(source)
    doc = Document(name="scan.png", path=str(source), file_type=FileType.image)
    db.save(doc)

    result = await remove_background_images(
        {
            "files": [str(source)],
            "documents": [doc.model_dump(mode="json")],
            "output_dir": str(tmp_path / "background_removed"),
            "method": "threshold",
            "threshold": 5,
            "output_format": "png",
        },
        {"library_path": str(library_path)},
        LLMConfig(provider="test", model="test"),
    )

    chains = list(db.query(ImageEditChain, document_id=doc.id))
    assert len(chains) == 1
    assert chains[0].operations[0]["op"] == "remove_background"
    assert chains[0].operations[0]["params"] == {"method": "threshold", "threshold": 5}
    assert result["image_edit_operations"][0]["document_id"] == doc.id


def test_remove_background_opencv_uses_archive_black_margin_remover():
    pytest.importorskip("cv2")
    from fichero.workflows.tools.remove_background_images import remove_background

    image = Image.new("RGB", (100, 80), "black")
    for x in range(20, 80):
        for y in range(10, 70):
            image.putpixel((x, y), (245, 245, 235))
    cleaned = remove_background(image, method="opencv", threshold=5)

    assert cleaned.mode == "RGBA"
    assert cleaned.size[0] < image.size[0]
    assert cleaned.size[1] < image.size[1]


def test_remove_background_opencv_falls_back_without_cv2(monkeypatch):
    import builtins

    from fichero.workflows.tools.remove_background_images import remove_background

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "cv2":
            raise ImportError("cv2 missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    image = Image.new("RGB", (5, 5), "white")
    image.putpixel((2, 2), (0, 0, 0))

    cleaned = remove_background(image, method="opencv", threshold=5)

    assert cleaned.mode == "RGBA"
    assert cleaned.getpixel((0, 0))[3] == 0
    assert cleaned.getpixel((2, 2))[3] == 255
