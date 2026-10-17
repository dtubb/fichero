"""`source.recipe.apple-finds-lines-on-print` (#5451): `keep_text` off holds on every Apple branch of the tool.

Spec: docs/contributor_manual/specs/source/models-chains-and-projects.md. WHY: the review of 810ceb4dd found the
option honoured on the image branch only; a print PDF's Find lines still landed Apple's OCR as a reading. Driven through
`process_vision` (Apple stubbed) for an image, a requested PDF page and a whole PDF: the lines land with their boxes
and no text, no word boxes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.media.ocr_geometry import OCRGeometryLevel
from fichero_server.workflows.tools.vision_base import (
    VisionOCRBox, VisionOCRResult, VisionToolConfig, process_vision,
)

JUNK = "WtrtNI-"
VB = "fichero_server.workflows.tools.vision_base."


def _apple_page() -> VisionOCRResult:
    line = VisionOCRBox(text=JUNK, bbox=[0.1, 0.1, 0.5, 0.05], char_start=0, char_end=len(JUNK))
    word = VisionOCRBox(text=JUNK, bbox=[0.1, 0.1, 0.2, 0.05], char_start=0, char_end=len(JUNK))
    return VisionOCRResult(text=JUNK, line_boxes=[line], word_boxes=[word])


def _config() -> VisionToolConfig:
    return VisionToolConfig(artifact_type="regions", supports_apple_vision=True, update_page_content=False,
                            trigger_embedding=False, skip_if_artifact_exists=False)


async def _run(path, document, library):
    db = MagicMock()
    db.get.return_value = MagicMock(metadata={}, region_in_parent=None)
    with patch(VB + "_try_pdf_text_layer", return_value=None), \
            patch(VB + "apple_vision_ocr_with_geometry_async", new=AsyncMock(return_value=_apple_page())), \
            patch(VB + "apple_vision_ocr_pdf_page_geometry_async", new=AsyncMock(return_value=_apple_page())), \
            patch(VB + "apple_vision_ocr_pages_geometry_async", new=AsyncMock(return_value=[_apple_page(), _apple_page()])), \
            patch(VB + "save_artifact", new=AsyncMock(return_value="artifact_1")) as saved, \
            patch(VB + "_propagate_to_page_children", new=AsyncMock(return_value=2)) as propagated, \
            patch("fichero_server.db.db_manager") as manager:
        manager.get_database.return_value = db
        await process_vision(files=[str(path)], documents=[document], prompt="", library_path=str(library),
                             llm_config=LLMConfig(provider="apple", model="apple-vision"), task_id="t",
                             tool_config=_config(), vision_mode="apple", keep_text=False, save_to_db=True)
    return saved, propagated


def _only_lines_no_text(geometries) -> None:
    boxes = [b for g in geometries if g is not None for b in g.boxes]
    assert boxes, "the lines land with their boxes"
    assert all(b.level == OCRGeometryLevel.LINE and b.text == "" for b in boxes), boxes


@pytest.mark.asyncio
async def test_an_image_keeps_the_lines_and_no_reading(tmp_path):
    """source.recipe.apple-finds-lines-on-print: "Apple finds the lines and keeps no text" on an image."""
    image = tmp_path / "files" / "ab" / "page.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"\x89PNG")
    saved, _ = await _run(image, {"id": "d1", "path": "files/ab/page.png"}, tmp_path)

    saved.assert_awaited_once()
    assert JUNK not in repr(saved.await_args_list), "Apple's text reached the saved artifact"
    _only_lines_no_text([saved.await_args.kwargs["ocr_geometry"]])


@pytest.mark.asyncio
async def test_a_whole_print_pdf_keeps_the_lines_and_no_reading(tmp_path):
    """source.recipe.apple-finds-lines-on-print: the same for every page of a PDF (the review's finding)."""
    pdf = tmp_path / "files" / "ab" / "doc.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4\n")
    saved, propagated = await _run(pdf, {"id": "d1", "path": "files/ab/doc.pdf"}, tmp_path)

    propagated.assert_awaited_once()
    assert propagated.await_args.args[1] == ["", ""], propagated.await_args.args[1]
    _only_lines_no_text(propagated.await_args.kwargs["page_geometries"])
    assert JUNK not in repr(saved.await_args_list)


@pytest.mark.asyncio
async def test_a_requested_pdf_page_keeps_the_lines_and_no_reading(tmp_path):
    """source.recipe.apple-finds-lines-on-print: the same for one requested page of a PDF."""
    pdf = tmp_path / "files" / "ab" / "doc.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4\n")
    saved, propagated = await _run(pdf, {"id": "p1", "path": "files/ab/doc.pdf", "parent_id": "d1", "sequence": 1}, tmp_path)

    saved.assert_awaited_once()
    assert JUNK not in repr(saved.await_args_list) + repr(propagated.await_args_list), "Apple's text was kept"
    _only_lines_no_text([saved.await_args.kwargs["ocr_geometry"]])
