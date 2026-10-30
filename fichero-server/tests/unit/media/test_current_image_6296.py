"""The page's current image: the edit chain applied, else the newest rendition, else the original (#6296).

`media/current_image.py` is the ONE answer every step that sends a page to a model reads. Tests drive it with a real
library and real pixels: a marker dot on the photograph must land on the same ink on the edited copy once a line's
fractions are carried through `media/frame_map.py`.
"""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from fichero_server.media.current_image import EDITED, ORIGINAL, RENDITION, current_page_image
from fichero_server.models import DocType, Document, FileType, ImageEditChain, NodeRegion, Rendition

W, H = 200, 100
DOT = (40, 30)  # on the photograph, in pixels
CROP = {"left": 20, "top": 10, "width": 120, "height": 80}
EDITS = [{"op": "crop", "page": 1, "params": CROP}, {"op": "rotate", "page": 1, "params": {"angle": 90}}]


def _page(db, tmp_path, name="page.png"):
    path = tmp_path / name
    image = Image.new("RGB", (W, H), "white")
    ImageDraw.Draw(image).rectangle([DOT[0] - 2, DOT[1] - 2, DOT[0] + 2, DOT[1] + 2], fill=(255, 0, 0))
    image.save(path)
    doc = Document(name=name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc


def _red_at(image_path, fraction):
    with Image.open(image_path) as image:
        x, y = round(fraction[0] * image.width), round(fraction[1] * image.height)
        return image.convert("RGB").getpixel((min(x, image.width - 1), min(y, image.height - 1))) == (255, 0, 0)


def _edit(db, doc, operations):
    for row in db.query(ImageEditChain, document_id=doc.id):
        db.delete(row)
    if operations:
        db.save(ImageEditChain(document_id=doc.id, operations=operations))


def test_a_page_with_no_edits_is_the_original(db, tmp_path):
    doc = _page(db, tmp_path)
    found = current_page_image(db, doc)
    assert found.kind == ORIGINAL and found.is_original
    assert found.path == str(tmp_path / "page.png") and found.to_image is None


def test_a_cropped_and_rotated_page_is_the_edited_image_and_a_line_follows_the_ink(db, tmp_path):
    doc = _page(db, tmp_path)
    _edit(db, doc, EDITS)

    found = current_page_image(db, doc)

    assert found.kind == EDITED and found.path != str(tmp_path / "page.png")
    with Image.open(found.path) as edited:
        assert edited.size == (80, 120)  # cropped to 120 x 80, then turned a quarter
    carried = found.to_image.carry([[DOT[0] / W, DOT[1] / H]])[0]
    assert _red_at(found.path, carried), carried  # the dot's fractions, carried, are on the dot
    assert not _red_at(found.path, [DOT[0] / W, DOT[1] / H])  # the photograph's own fractions are not
    back = found.photograph_map().carry([carried])[0]
    assert back == pytest.approx([DOT[0] / W, DOT[1] / H], abs=1e-6)


def test_undo_in_preview_changes_what_the_next_step_sends(db, tmp_path):
    doc = _page(db, tmp_path)
    _edit(db, doc, EDITS)
    edited = current_page_image(db, doc)
    _edit(db, doc, EDITS[:1])  # Undo the rotate: one edit is left
    cropped = current_page_image(db, doc)
    _edit(db, doc, [])  # Undo the crop: none is left
    original = current_page_image(db, doc)

    with Image.open(edited.path) as a, Image.open(cropped.path) as b:
        assert a.size == (80, 120) and b.size == (120, 80)
    assert len({edited.path, cropped.path}) == 2
    assert original.is_original and original.path == str(tmp_path / "page.png")


def test_a_same_frame_edit_leaves_the_lines_where_they_are(db, tmp_path):
    doc = _page(db, tmp_path)
    _edit(db, doc, [{"op": "enhance", "page": 1, "params": {"auto_levels": True}}])
    found = current_page_image(db, doc)
    assert found.kind == EDITED
    assert found.to_image.carry([[0.25, 0.5]])[0] == pytest.approx([0.25, 0.5])


def test_the_newest_rendition_is_read_when_there_is_no_edit(db, tmp_path):
    doc = _page(db, tmp_path)
    cut = tmp_path / "crop.png"
    Image.open(tmp_path / "page.png").crop((20, 10, 140, 90)).save(cut)
    db.save(Rendition(document_id=doc.id, role="crop", path=str(cut), pixel_width=120, pixel_height=80,
                      transform=NodeRegion(rect=[0.1, 0.1, 0.6, 0.8])))

    found = current_page_image(db, doc)

    assert found.kind == RENDITION and found.path == str(cut)
    assert _red_at(cut, found.to_image.carry([[DOT[0] / W, DOT[1] / H]])[0])


def test_a_person_edit_comes_before_a_rendition(db, tmp_path):
    doc = _page(db, tmp_path)
    cut = tmp_path / "crop.png"
    Image.open(tmp_path / "page.png").crop((20, 10, 140, 90)).save(cut)
    db.save(Rendition(document_id=doc.id, role="crop", path=str(cut), transform=NodeRegion(rect=[0.1, 0.1, 0.6, 0.8])))
    _edit(db, doc, EDITS[:1])

    assert current_page_image(db, doc).kind == EDITED


def test_a_rendition_whose_frame_is_not_known_is_passed_over_not_guessed(db, tmp_path):
    doc = _page(db, tmp_path)
    flat = tmp_path / "flat.png"
    Image.new("RGB", (W, H), "white").save(flat)
    db.save(Rendition(document_id=doc.id, role="flattened", path=str(flat),
                      transform=NodeRegion(rect=[0, 0, 1, 1], method="flatten")))
    turned = tmp_path / "turned.png"
    Image.new("RGB", (H, W), "white").save(turned)  # turned a quarter, and no transform says so
    db.save(Rendition(document_id=doc.id, role="rotated", path=str(turned)))

    assert current_page_image(db, doc).is_original


def test_prepared_rendition_in_the_pages_own_frame_is_read(db, tmp_path):
    doc = _page(db, tmp_path)
    prepared = tmp_path / "prepared.png"
    Image.open(tmp_path / "page.png").save(prepared)
    db.save(Rendition(document_id=doc.id, role="prepared", path=str(prepared)))

    found = current_page_image(db, doc)

    assert found.kind == RENDITION and found.path == str(prepared)
    assert found.to_image is None  # same pixels' frame: lines need no carrying


def test_a_turn_rendition_follows_its_recorded_angle(db, tmp_path):
    doc = _page(db, tmp_path)
    turned = tmp_path / "turned.png"
    Image.open(tmp_path / "page.png").transpose(Image.Transpose.ROTATE_90).save(turned)
    db.save(Rendition(document_id=doc.id, role="rotated", path=str(turned), pixel_width=H, pixel_height=W,
                      transform=NodeRegion(rect=[0, 0, 1, 1], method="turn", angle=90)))

    found = current_page_image(db, doc)

    assert found.kind == RENDITION
    assert _red_at(turned, found.to_image.carry([[DOT[0] / W, DOT[1] / H]])[0])


def test_a_pages_geometry_carried_to_the_edit_and_back_is_the_same_box(db, tmp_path):
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    doc = _page(db, tmp_path)
    _edit(db, doc, EDITS)
    found = current_page_image(db, doc)
    # what a finder measured on the EDITED image: one line, in that image's pixels
    polygon = [[10, 20], [60, 20], [60, 40], [10, 40]]
    box = OCRGeometryBox(text="", bbox=[10 / 80, 20 / 120, 50 / 80, 20 / 120], level=OCRGeometryLevel.LINE,
                         metadata={"polygon_px": polygon, "pixel_frame": {"width": 80, "height": 120}})
    result = OCRGeometryResult(text="", provider="kraken", boxes=[box], metadata={"pixel_frame": {"width": 80, "height": 120}})

    on_photograph = found.geometry_to_photograph(result)

    assert on_photograph.metadata["frame"] == "upright"
    assert on_photograph.metadata["pixel_frame"] == {"width": W, "height": H}
    xs = [p[0] for p in on_photograph.boxes[0].metadata["polygon_px"]]
    ys = [p[1] for p in on_photograph.boxes[0].metadata["polygon_px"]]
    # a 50 x 20 outline on the turned page is 20 wide and 50 tall on the cropped one, inside the cropped region of the photograph
    assert (max(xs) - min(xs), max(ys) - min(ys)) == pytest.approx((20, 50))
    assert min(xs) >= CROP["left"] and max(xs) <= CROP["left"] + CROP["width"]
    assert min(ys) >= CROP["top"] and max(ys) <= CROP["top"] + CROP["height"]
