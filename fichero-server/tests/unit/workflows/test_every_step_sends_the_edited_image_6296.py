"""Every step that sends a page to a model sends the page's CURRENT image (#6296): the edit chain applied, else the newest
rendition, else the original. Driven through the real tools with a real library; only the models are faked, and each fake
records the picture it was handed.

The photograph is 400 x 300 with a red marker. The edit is a crop (200 x 150) and a quarter turn, so the edited image is
150 x 200: a step that sent the photograph would be seen at once, by its size.
"""
from __future__ import annotations

import base64
import io

import pytest
from PIL import Image, ImageDraw

from fichero_server.db.manager import db_manager
from fichero_server.models import DocType, Document, FileType, ImageEditChain

W, H = 400, 300
CROP = {"left": 100, "top": 50, "width": 200, "height": 150}
EDITS = [{"op": "crop", "page": 1, "params": CROP}, {"op": "rotate", "page": 1, "params": {"angle": 90}}]
EDITED_SIZE = (150, 200)
#: Where the ink is on the photograph: a line 20 high across the cropped region's middle.
LINE = [[120, 140], [280, 140], [280, 160], [120, 160]]


def _poly(box):
    x0, y0, x1, y1 = box
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


@pytest.fixture
def page(test_package, tmp_path):
    library = str(test_package)
    db = db_manager.get_database(library)
    path = tmp_path / "page.png"
    image = Image.new("RGB", (W, H), "white")
    ImageDraw.Draw(image).rectangle([120, 142, 280, 158], fill=(0, 0, 0))  # the line's ink
    image.save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return {"library": library, "db": db, "doc": doc, "path": str(path)}


def _set_edits(page, operations):
    db, doc = page["db"], page["doc"]
    for row in db.query(ImageEditChain, document_id=doc.id):
        db.delete(row)
    if operations:
        db.save(ImageEditChain(document_id=doc.id, operations=operations))


def _size_of_uri(uri):
    return Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).size


async def _tool(page, tool, **inputs):
    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.sources import files_tool

    library, doc = page["library"], page["doc"]
    src = await files_tool(inputs={}, state={"selected_doc_ids": [doc.id], "library_path": library},
                           llm_config=LLMConfig(provider="", model=""))
    result = await tool(inputs={"files": src["files"], "documents": src["documents"], "regions_first": False, **inputs},
                        state={"library_path": library, "task_id": None},
                        llm_config=LLMConfig(provider="openrouter", model="google/gemini-3-flash-preview"))
    assert not result.get("error"), result.get("error")
    return result


async def _whole_page(page, monkeypatch):
    import fichero_server.llm as llm
    from fichero_server.workflows.tools.transcribe import transcribe

    sent = []

    async def model(images, prompt, config, **_):
        sent.extend(_size_of_uri(i) for i in images)
        return "una linea de texto"

    monkeypatch.setattr(llm, "vision", model)
    await _tool(page, transcribe, vision_mode="llm", save_to_db=False)
    return sent


def _find_lines_stub(monkeypatch):
    """Kraken's segmenter, giving its one line at the SAME place on whatever picture it is handed (as a page-wide line)."""
    import fichero_server.llm.kraken_runtime as kraken_runtime

    seen = []

    def segment(image_path, **_):
        with Image.open(image_path) as image:
            width, height = image.size
        seen.append((image_path, (width, height)))
        return {"width": width, "height": height, "regions": [],
                "lines": [{"baseline": [[10, height / 2], [width - 10, height / 2]],
                           "polygon": _poly((10, height / 2 - 10, width - 10, height / 2 + 10)), "region": None}]}

    monkeypatch.setattr(kraken_runtime, "segment_lines", segment)
    return seen


async def _find_lines(page, monkeypatch):
    from fichero_server.workflows.tools.transcribe import transcribe

    seen = _find_lines_stub(monkeypatch)
    await _tool(page, transcribe, vision_mode="kraken")
    return [size for _path, size in seen]


async def _read_lines_with_kraken(page, monkeypatch):
    """A page with its lines already found, read by a Kraken reader: what it is handed is the image and the lines."""
    import fichero_server.llm.kraken_runtime as kraken_runtime
    from fichero_server.workflows.tools.transcribe import transcribe

    await _seed_lines(page, monkeypatch)
    monkeypatch.setattr(kraken_runtime, "resolve_recognition_model", lambda ref: ("/models/m.mlmodel", ref))
    seen = {}

    def read(image_path, model_path, lines, **kw):
        with Image.open(image_path) as image:
            seen["size"] = image.size
        seen["lines"] = list(lines)
        return ["texto"] * len(lines)

    monkeypatch.setattr(kraken_runtime, "read_given_lines", read)
    await _tool(page, transcribe, vision_mode="kraken", kraken_model="kraken-m")
    return seen


async def _seed_lines(page, monkeypatch):
    """Find the page's lines on the PHOTOGRAPH (a page with no edit), then restore the page's edits: the lines every step
    reads are stored as fractions of the photograph."""
    import fichero_server.llm.kraken_runtime as kraken_runtime
    from fichero_server.workflows.tools.transcribe import transcribe

    chain = [dict(op) for row in page["db"].query(ImageEditChain, document_id=page["doc"].id) for op in row.operations]
    _set_edits(page, [])
    monkeypatch.setattr(kraken_runtime, "segment_lines", lambda image_path, **_: {
        "width": W, "height": H, "regions": [], "lines": [{"baseline": [[120, 155], [280, 155]], "polygon": _poly((120, 140, 280, 160)),
                                                           "region": None}]})
    await _tool(page, transcribe, vision_mode="kraken")
    _set_edits(page, chain)


async def _read_lines_with_a_model(page, monkeypatch):
    import fichero_server.llm as llm
    from fichero_server.workflows.tools.transcribe import transcribe

    await _seed_lines(page, monkeypatch)
    crops = []

    async def model(images, prompt, config, **_):
        crops.extend(_size_of_uri(i) for i in images)
        return '["una linea"]'

    monkeypatch.setattr(llm, "vision", model)
    await _tool(page, transcribe, vision_mode="kraken", lines_read_by="model")
    return crops


def _find_regions(page, monkeypatch, provider):
    import fichero_server.llm.kraken_runtime as kraken_runtime
    import fichero_server.llm.yolo_runtime as yolo_runtime
    from fichero_server.llm.yolo_runtime import Region
    from fichero_server.recipes.regions import find_regions

    sizes = []

    def seg(image_path, **_):
        with Image.open(image_path) as image:
            sizes.append(image.size)
            return {"width": image.width, "height": image.height, "regions": [], "lines": []}

    def yolo(image_path, model="m", **_):
        with Image.open(image_path) as image:
            sizes.append(image.size)
        return [Region(kind_raw="Text", rect=[0.1, 0.1, 0.5, 0.5], confidence=0.9)]

    monkeypatch.setattr(kraken_runtime, "segment_lines", seg)
    monkeypatch.setattr(yolo_runtime, "detect_regions", yolo)
    find_regions(page["db"], [page["doc"].id], "run-1", "blla" if provider == "kraken" else "yolo", provider=provider)
    return sizes


STEPS = ["whole-page read", "find lines", "find regions (kraken)", "find regions (yolo)"]


def _sizes(step, page, monkeypatch):
    """The size of every picture the step sent (a sync wrapper: Find Regions runs its own event loop)."""
    import asyncio

    if step == "whole-page read":
        return asyncio.run(_whole_page(page, monkeypatch))
    if step == "find lines":
        return asyncio.run(_find_lines(page, monkeypatch))
    return _find_regions(page, monkeypatch, "kraken" if "kraken" in step else "yolo")


@pytest.mark.parametrize("step", STEPS)
def test_an_edited_page_is_what_each_step_sends(page, monkeypatch, step):
    _set_edits(page, EDITS)
    assert _sizes(step, page, monkeypatch) == [EDITED_SIZE]


@pytest.mark.parametrize("step", STEPS)
def test_undo_in_preview_changes_what_the_next_step_sends(page, monkeypatch, step):
    _set_edits(page, EDITS)
    assert _sizes(step, page, monkeypatch) == [EDITED_SIZE]
    _set_edits(page, EDITS[:1])  # Undo the turn
    assert _sizes(step, page, monkeypatch) == [(200, 150)]
    _set_edits(page, [])  # Undo the crop
    assert _sizes(step, page, monkeypatch) == [(W, H)]


@pytest.mark.parametrize("step", STEPS)
def test_a_page_with_no_edits_sends_the_original(page, monkeypatch, step):
    assert _sizes(step, page, monkeypatch) == [(W, H)]


@pytest.mark.asyncio
async def test_lines_found_on_an_edited_page_are_stored_on_the_photograph(page, monkeypatch):
    """Find Lines read the edited image; the line it found is saved where it is on the PHOTOGRAPH, so every other surface
    (Source view, export, a later reader) that measures against the photograph agrees."""
    from fichero_server.llm.working_lines import working_lines

    _set_edits(page, EDITS)
    await _find_lines(page, monkeypatch)
    found = working_lines(page["db"], page["doc"].id)
    (line,) = found.lines
    # the segmenter put a page-wide line across the middle of the 150 x 200 edit: after the turn back it is a vertical
    # stripe inside the cropped region of the photograph
    x, y, w, h = line.bbox_x * W, line.bbox_y * H, line.bbox_w * W, line.bbox_h * H
    assert (w, h) == pytest.approx((20, 130), abs=2)
    assert CROP["left"] <= x and x + w <= CROP["left"] + CROP["width"]
    assert CROP["top"] <= y and y + h <= CROP["top"] + CROP["height"]


@pytest.mark.asyncio
async def test_a_kraken_reader_is_given_the_edited_image_and_the_lines_carried_onto_it(page, monkeypatch):
    _set_edits(page, EDITS)
    seen = await _read_lines_with_kraken(page, monkeypatch)

    assert seen["size"] == EDITED_SIZE
    (line,) = seen["lines"]
    # the line was on the photograph at x 120..280, y 140..160; on the edit (cropped by 100, 50 then turned a quarter) it is
    # a stripe 20 wide and 160 tall, still over the ink
    xs = [p[0] for p in line["polygon"]]
    ys = [p[1] for p in line["polygon"]]
    assert (max(xs) - min(xs), max(ys) - min(ys)) == pytest.approx((20, 160), abs=1)
    assert 0 <= min(xs) and max(xs) <= EDITED_SIZE[0] and 0 <= min(ys) and max(ys) <= EDITED_SIZE[1]


@pytest.mark.asyncio
async def test_a_kraken_reader_on_an_unedited_page_is_given_the_photograph_and_its_lines_as_they_are(page, monkeypatch):
    seen = await _read_lines_with_kraken(page, monkeypatch)
    assert seen["size"] == (W, H)
    assert [pt for p in seen["lines"][0]["polygon"] for pt in p] == pytest.approx([120, 140, 280, 140, 280, 160, 120, 160])


@pytest.mark.asyncio
async def test_a_model_reading_lines_is_sent_each_line_cut_from_the_edited_image(page, monkeypatch):
    _set_edits(page, EDITS)
    crops = await _read_lines_with_a_model(page, monkeypatch)
    (crop,) = crops
    # the line's stripe is 20 wide and 160 tall on the edit; padded by a third of the stripe's smaller side's height rule
    # (`line_cut.crop_line`: a third of the outline's height), it is cut from the edit and not from the photograph, where it
    # would be 160 wide and 20 tall
    assert crop[1] > crop[0], crop


@pytest.mark.asyncio
async def test_a_model_reading_lines_on_an_unedited_page_is_sent_the_line_as_it_is(page, monkeypatch):
    (crop,) = await _read_lines_with_a_model(page, monkeypatch)
    assert crop[0] > crop[1], crop


def test_a_review_re_asks_on_the_edited_image_with_the_lines_carried(page):
    from fichero_server.workflows.tools.transcribe_review import _lines_on_current_image

    _set_edits(page, EDITS)
    asked = [{"id": "l1", "text": "x", "polygon": LINE}]
    path, moved, frame = _lines_on_current_image(page["db"], page["doc"], asked, "upright")

    assert path != page["path"] and Image.open(path).size == EDITED_SIZE
    assert frame is None  # the edited image is opened as it is
    xs = [p[0] for p in moved[0]["polygon"]]
    ys = [p[1] for p in moved[0]["polygon"]]
    assert (max(xs) - min(xs), max(ys) - min(ys)) == pytest.approx((20, 160), abs=1)

    _set_edits(page, [])
    path, same, frame = _lines_on_current_image(page["db"], page["doc"], asked, "upright")
    assert path == page["path"] and same == asked and frame == "upright"


def test_a_page_with_a_prepared_rendition_and_no_edit_sends_the_rendition(page, monkeypatch):
    """Prepare Images' renditions are read after a person's edits and before the original."""
    import asyncio

    from fichero_server.models import Rendition

    prepared = page["db"].path.parent / "files" / "prepared.png"
    prepared.parent.mkdir(exist_ok=True)
    Image.new("RGB", (W, H), "gray").save(prepared)
    page["db"].save(Rendition(document_id=page["doc"].id, role="prepared", path=str(prepared)))
    sent = asyncio.run(_whole_page(page, monkeypatch))
    assert sent == [(W, H)]  # the rendition is the page's own frame and size: told apart by its colour below

    seen = []
    import fichero_server.workflows.tools.vision_base as vision_base

    real = vision_base.file_to_data_uri_async

    async def spy(path, **kw):
        seen.append(path)
        return await real(path, **kw)

    monkeypatch.setattr(vision_base, "file_to_data_uri_async", spy)
    asyncio.run(_whole_page(page, monkeypatch))
    assert seen == [str(prepared)]

    _set_edits(page, EDITS)  # a person's edit comes before the rendition
    seen.clear()
    assert asyncio.run(_whole_page(page, monkeypatch)) == [EDITED_SIZE] and seen and seen[0] != str(prepared)


@pytest.mark.asyncio
async def test_apple_vision_reads_the_edited_image_and_its_boxes_land_on_the_photograph(page):
    from unittest.mock import AsyncMock, patch

    from fichero_server.llm import LLMConfig
    from fichero_server.workflows.tools.vision_base import VisionOCRBox, VisionOCRResult, VisionToolConfig, process_vision

    _set_edits(page, EDITS)
    asked = []

    async def vision(path, language, **_):
        asked.append(path)
        line = VisionOCRBox(text="x", bbox=[0.0, 0.25, 1.0, 0.1], char_start=0, char_end=1)  # a band across the edit
        return VisionOCRResult(text="x", line_boxes=[line], word_boxes=[])

    saved = AsyncMock(return_value="artifact-1")
    vb = "fichero_server.workflows.tools.vision_base."
    with patch(vb + "_try_pdf_text_layer", return_value=None), \
            patch(vb + "apple_vision_ocr_with_geometry_async", new=vision), \
            patch(vb + "save_artifact", new=saved):
        await process_vision(
            files=[page["path"]], documents=[{"id": page["doc"].id, "path": page["path"]}], prompt="",
            library_path=page["library"], llm_config=LLMConfig(provider="apple", model="apple-vision"), task_id="t",
            tool_config=VisionToolConfig(artifact_type="regions", supports_apple_vision=True, update_page_content=False,
                                         trigger_embedding=False, skip_if_artifact_exists=False),
            vision_mode="apple", keep_text=True, save_to_db=True)

    assert asked and asked[0] != page["path"] and Image.open(asked[0]).size == EDITED_SIZE
    (box,) = saved.await_args.kwargs["ocr_geometry"].boxes
    x, y, w, h = box.bbox
    # a full-width band on the 150 x 200 edit is a tall strip on the photograph, inside the cropped region
    assert (w * W, h * H) == pytest.approx((20, 150), abs=2)
    assert (x * W, y * H) == pytest.approx((230, 50), abs=2)  # turned back, then put 100 and 50 in from the photograph's corner
