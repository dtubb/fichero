"""Tests for the remove_background_images workflow tool (#1393)."""

from __future__ import annotations

import pytest

pytest.importorskip("PIL")

from PIL import Image

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.models import Document, FileType, ImageEditChain
from fichero_server.workflows.registry import get_tool, get_tool_def
from fichero_server.workflows.tools.remove_background_images import (
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


def test_remove_background_opencv_preserves_page_and_text_on_dark_ground():
    """The contour method keeps the WHOLE page — ink included — and drops the ground.

    Guards against the old per-pixel Otsu-inverted mask, whose "foreground" was
    only the dark pixels: it deleted the paper and morphologically ate the thin
    strokes themselves (Daniel, 2026-09-02).
    """
    pytest.importorskip("cv2")

    from fichero_server.workflows.tools.remove_background_images import remove_background

    image = Image.new("RGB", (60, 60), (10, 10, 10))
    for x in range(15, 45):
        for y in range(15, 45):
            image.putpixel((x, y), (235, 230, 220))
    for x in range(20, 40):  # a thin ink stroke on the paper
        image.putpixel((x, 30), (30, 25, 20))

    cleaned = remove_background(image, method="opencv", threshold=28)

    assert cleaned.mode == "RGBA"
    assert cleaned.size[0] < 60  # cropped to the page
    centre = cleaned.getpixel((cleaned.width // 2, cleaned.height // 2))
    assert centre[3] > 200  # the stroke at page centre is still opaque


def test_remove_background_opencv_falls_back_without_cv2(monkeypatch):
    import builtins

    from fichero_server.workflows.tools.remove_background_images import remove_background

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
