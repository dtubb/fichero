"""## 1114 (Test 14): every place that pairs a page image with geometry opens the image in the geometry's frame.

New geometry (Kraken's) is measured on the upright page and says `frame: "upright"`; geometry with NO marker was
measured on the file's raw pixels and is cut from them still, so an old pass on a rotated page keeps matching its own
image (nothing is rewritten). The page here is a landscape 200x100 whose only ink is a black bar across its upright top
left; it is stored as the raw 100x200 sideways file a phone makes, tagged EXIF Orientation 6."""
from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from PIL import Image

from fichero_server.llm import kraken_runtime
from fichero_server.llm.line_reader import read_lines
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult
from fichero_server.media.upright import FRAME_UPRIGHT, copy_in_frame, open_in_frame

#: The bar's place on the page as a person sees it (x0, y0, x1, y1), 200 wide and 100 tall.
BAR = (20, 10, 120, 30)


def _phone_photo(path: Path) -> Path:
    """The upright page, turned a quarter and tagged so a viewer turns it back (Orientation 6)."""
    upright = Image.new("RGB", (200, 100), (255, 255, 255))
    upright.paste((0, 0, 0), BAR)
    raw = upright.rotate(90, expand=True)  # counter-clockwise; Orientation 6 means "rotate 90 clockwise to view"
    exif = Image.Exif()
    exif[0x0112] = 6
    raw.save(path, format="PNG", exif=exif)
    return path


def _kraken_payload() -> dict:
    x0, y0, x1, y1 = BAR
    return {"width": 200, "height": 100, "regions": {}, "lines": [
        {"polygon": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "baseline": [[x0, y1 - 4], [x1, y1 - 4]]}]}


def _crops_seen(monkeypatch) -> list[Image.Image]:
    seen: list[Image.Image] = []

    async def fake_vision(images, prompt, config, **kwargs):
        for uri in images:
            seen.append(Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1]))).convert("L"))
        return '["bar"]'

    monkeypatch.setattr("fichero_server.llm.vision", fake_vision)
    return seen


def _darkness(image: Image.Image) -> float:
    return 1 - sum(image.getdata()) / (255 * image.width * image.height)


async def _read(path: Path, geometry: OCRGeometryResult):
    from fichero_server.llm import LLMConfig

    return await read_lines(str(path), geometry, LLMConfig(provider="fake", model="fake"))


def test_kraken_geometry_says_it_is_upright_and_the_crop_is_the_text(tmp_path, monkeypatch):
    import asyncio

    photo = _phone_photo(tmp_path / "phone.png")
    geometry = kraken_runtime.geometry_from_segmentation(_kraken_payload())
    assert geometry.metadata["frame"] == FRAME_UPRIGHT
    assert all(box.metadata["frame"] == FRAME_UPRIGHT for box in geometry.boxes)
    seen = _crops_seen(monkeypatch)
    asyncio.run(_read(photo, geometry))
    assert seen and _darkness(seen[0]) > 0.5  # the line's crop is the black bar, not a patch of blank page


def test_an_old_pass_with_no_marker_is_cut_from_the_raw_pixels(tmp_path, monkeypatch):
    """A pass made before the marker existed was measured on the sideways file: it keeps matching its own image."""
    import asyncio

    photo = _phone_photo(tmp_path / "phone.png")
    with Image.open(photo) as raw:
        assert raw.size == (100, 200)
    # The raw frame's own coordinates of the bar: the quarter turn maps (x, y) of the page to (y, 200 - x).
    x0, y0, x1, y1 = BAR
    rx0, ry0, rx1, ry1 = y0, 200 - x1, y1, 200 - x0
    box = OCRGeometryBox(text="", bbox=[rx0 / 100, ry0 / 200, (rx1 - rx0) / 100, (ry1 - ry0) / 200],
                         level=OCRGeometryLevel.LINE, provider="kraken", model="blla", source="kraken-blla",
                         metadata={"polygon_px": [[rx0, ry0], [rx1, ry0], [rx1, ry1], [rx0, ry1]],
                                   "baseline_px": [[rx0, ry1 - 4], [rx1, ry1 - 4]],
                                   "pixel_frame": {"width": 100, "height": 200}})
    old = OCRGeometryResult(provider="kraken", model="blla", boxes=[box], source="kraken-blla")
    assert "frame" not in old.metadata
    seen = _crops_seen(monkeypatch)
    asyncio.run(_read(photo, old))
    assert seen and _darkness(seen[0]) > 0.15  # the sideways bar, in the raw frame (a wrong frame gives blank page)


def test_open_in_frame_is_raw_unless_marked_upright(tmp_path):
    photo = _phone_photo(tmp_path / "phone.png")
    assert open_in_frame(photo, None).size == (100, 200)
    assert open_in_frame(photo, FRAME_UPRIGHT).size == (200, 100)


def test_an_exported_training_page_agrees_with_its_lines(tmp_path):
    photo = _phone_photo(tmp_path / "phone.png")
    out = tmp_path / "set.png"
    copy_in_frame(photo, out, FRAME_UPRIGHT)
    with Image.open(out) as copied:
        assert copied.size == (200, 100) and (copied.getexif().get(0x0112, 1) or 1) == 1
    raw_out = tmp_path / "raw.png"
    copy_in_frame(photo, raw_out, None)
    assert raw_out.read_bytes() == photo.read_bytes()


def test_a_working_pass_page_size_follows_its_frame(tmp_path):
    from types import SimpleNamespace

    from fichero_server.llm.working_lines import WorkingLines

    photo = _phone_photo(tmp_path / "phone.png")
    new = WorkingLines(SimpleNamespace(metadata={}), [SimpleNamespace(metadata={"frame": FRAME_UPRIGHT})])
    old = WorkingLines(SimpleNamespace(metadata={}), [SimpleNamespace(metadata={})])
    with Image.open(photo) as image:
        assert new.page_size(image) == (200.0, 100.0)
        assert old.page_size(image) == (100.0, 200.0)


@pytest.mark.parametrize("marked, expect_ink", [(True, True), (False, False)])
def test_a_segment_picture_follows_the_segments_frame(db, marked, expect_ink):
    from fichero_server.media.segment_pictures import SegmentPictureOptions, segment_picture
    from fichero_server.models import DocType, Document, FileType, Status
    from fichero_server.models.anchors import SourceAnchor
    from fichero_server.models.knowledge import ProvenanceKind
    from fichero_server.models.segments import Segment, bbox_and_tile_from_anchor

    photo = _phone_photo(Path(db.path.parent) / "phone.png")
    doc = Document(name="phone", doc_type=DocType.file, file_type=FileType.image, path=str(photo), status=Status.completed)
    db.save(doc)
    x0, y0, x1, y1 = BAR  # the upright frame's fractions; a marked segment is cut from the upright page
    anchor = SourceAnchor(document_id=doc.id, rect=[x0 / 200, y0 / 100, (x1 - x0) / 200, (y1 - y0) / 100])
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    row = Segment(document_id=doc.id, pass_id="pass", kind="line", anchor=anchor, bbox_x=x, bbox_y=y, bbox_w=w,
                  bbox_h=h, tile=tile, doc_kind="page", provenance_kind=ProvenanceKind.workflow, version=1,
                  metadata={"frame": FRAME_UPRIGHT} if marked else {})
    db.save(row)
    rendition = segment_picture(db, row.id, options=SegmentPictureOptions(mask=False, margin=0.0))
    with Image.open(rendition.path) as picture:
        dark = _darkness(picture.convert("L"))
    assert (dark > 0.5) is expect_ink
