"""Page crop writes `page_box`; Leave Out reads it and names the ruler and the colour card
(`image.enhance.page-crop-writes-page-box`, `image.enhance.leave-out-reads-the-page-box`, #6198).

WHY: nothing wrote `page_box`, so Leave Out's `off the page` never fired on a real scan and Kraken's false lines on the
ruler reached Read. The scan is drawn (paper on a dark mount, a ruler down the left, a colour card at the top).
"""
from __future__ import annotations

import hashlib

from PIL import Image

from fichero_server.models import DocType, Document, FileType, Rendition
from tests.unit.media.test_find_page import H, PAGE, W, scan


def _doc(db, tmp_path):
    path = tmp_path / "doc11.png"
    scan().save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path))
    db.save(doc)
    return doc, path


def test_page_crop_writes_the_page_box_and_a_rendition_and_leaves_the_original_alone(db, tmp_path):
    from fichero_server.recipes.page_crop import crop_pages

    doc, path = _doc(db, tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    account = crop_pages(db, [doc.id], "run-1")

    assert account["cropped"] == 1
    meta = db.get(Document, doc.id).metadata
    x, y, w, h = meta["page_box"]
    assert abs(x * W - PAGE[0]) < 32 and abs((x + w) * W - PAGE[2]) < 32 and abs(y * H - PAGE[1]) < 32
    assert {f["kind"] for f in meta["page_furniture"]} == {"ruler", "colour card"}
    (crop,) = [r for r in db.query(Rendition, document_id=doc.id) if r.role == "crop"]
    assert crop.transform is not None and crop.pixel_width < W and not crop.is_primary
    with Image.open(crop.path) as opened:
        assert opened.size == (crop.pixel_width, crop.pixel_height)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before, "the original is never changed"
    crop_pages(db, [doc.id], "run-2")  # a re-run replaces its own crop, it does not stack another
    assert len([r for r in db.query(Rendition, document_id=doc.id) if r.role == "crop"]) == 1


def test_a_persons_box_is_not_replaced(db, tmp_path):
    from fichero_server.recipes.page_crop import crop_pages

    doc, _ = _doc(db, tmp_path)
    doc.metadata = {"page_box": [0.1, 0.1, 0.5, 0.5], "page_box_by": "person"}
    db.save(doc)

    assert crop_pages(db, [doc.id], "run-1")["kept"] == 1
    assert db.get(Document, doc.id).metadata["page_box"] == [0.1, 0.1, 0.5, 0.5]


def test_leave_out_names_the_ruler_and_the_card_and_keeps_the_text():
    from fichero_server.media.find_page import find_page
    from fichero_server.recipes.leave_out import COLOUR_CARD, RULER, decide

    found = find_page(scan())
    line = lambda i, x, y, w, h: {"id": i, "x": x, "y": y, "w": w, "h": h, "confidence": 0.9}  # noqa: E731
    lines = [line("text", 0.3, 0.5, 0.5, 0.03), line("ruler", 0.04, 0.3, 0.02, 0.05), line("card", 0.45, 0.06, 0.1, 0.03),
             line("mount", 0.96, 0.5, 0.03, 0.03)]
    verdicts = decide(lines, page_box=list(found.box), furniture=list(found.furniture))
    assert verdicts == {"ruler": RULER, "card": COLOUR_CARD, "mount": "off the page"}
