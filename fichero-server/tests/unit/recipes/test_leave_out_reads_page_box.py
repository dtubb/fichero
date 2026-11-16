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


def test_the_stage_marks_the_ruler_the_card_and_the_mount_lines_of_a_cropped_scan_and_keeps_the_text(db, tmp_path):
    """Page crop writes `page_box` and `page_furniture` on the document; Leave Out, run on the same document through the real
    store, reads them: the ruler's, the card's and the mount's lines are marked with their reasons and the text lines stay."""
    from fichero_server.models import Segment
    from fichero_server.recipes import leave_out
    from fichero_server.recipes.page_crop import crop_pages
    from tests.unit.recipes.test_leave_out import _segment

    doc, _ = _doc(db, tmp_path)
    assert crop_pages(db, [doc.id], "run-1")["cropped"] == 1
    text = [{"id": f"text{i}", "x": 0.3, "y": 0.4 + 0.06 * i, "w": 0.55, "h": 0.03, "confidence": 0.9} for i in range(8)]
    others = [{"id": "ruler", "x": 0.04, "y": 0.3, "w": 0.02, "h": 0.05, "confidence": 0.9},
              {"id": "card", "x": 0.45, "y": 0.06, "w": 0.1, "h": 0.03, "confidence": 0.9},
              {"id": "mount", "x": 0.96, "y": 0.5, "w": 0.03, "h": 0.03, "confidence": 0.9}]
    made = {}
    for line in [*text, *others]:
        row = _segment(doc.id, line)
        db.save(row)
        made[line["id"]] = row.id

    account = leave_out.leave_out_pages(db, [doc.id], "run-2")

    reasons = {name: db.get(Segment, sid).metadata.get("left_out", {}).get("why") for name, sid in made.items()}
    assert reasons["ruler"] == leave_out.RULER and reasons["card"] == leave_out.COLOUR_CARD and reasons["mount"] == leave_out.OFF_THE_PAGE
    assert not any(reasons[f"text{i}"] for i in range(8)), reasons
    assert account["left_out"] == 3 and account["why"] == {leave_out.RULER: 1, leave_out.COLOUR_CARD: 1, leave_out.OFF_THE_PAGE: 1}


def test_the_reasons_vocabulary_has_the_page_level_and_show_through_names():
    from fichero_server.recipes import leave_out

    assert {leave_out.RULER, leave_out.COLOUR_CARD, leave_out.OFF_THE_PAGE, leave_out.SHOW_THROUGH,
            leave_out.SHOW_THROUGH_ONLY_VERSO} == {"ruler", "colour card", "off the page", "show-through",
                                                   "show-through-only verso"}


def _faint_line_page(db, tmp_path, *, enhanced_dark: bool):
    """A page whose original is plain paper under a low-confidence line; an `enhanced` rendition (same frame) is written
    with inked pixels under that line when `enhanced_dark`."""
    from fichero_server.recipes.leave_out import LOW_CONFIDENCE
    from tests.unit.recipes.test_leave_out import _segment

    original = tmp_path / "plain.png"
    Image.new("L", (400, 400), 235).save(original)
    doc = Document(name="plain.png", doc_type=DocType.file, file_type=FileType.image, path=str(original))
    db.save(doc)
    ink = Image.new("L", (400, 400), 235)
    if enhanced_dark:
        for x in range(60, 340):
            for y in range(200, 216):
                ink.putpixel((x, y), 20 if (x // 3) % 2 else 235)
    enhanced = tmp_path / "enhanced.png"
    ink.save(enhanced)
    db.save(Rendition(document_id=doc.id, role="enhanced", path=str(enhanced), pixel_width=400, pixel_height=400))
    for i in range(8):
        row = _segment(doc.id, {"id": f"t{i}", "x": 0.1, "y": 0.05 + 0.05 * i, "w": 0.7, "h": 0.03, "confidence": 0.9})
        db.save(row)
    faint = _segment(doc.id, {"id": "faint", "x": 0.15, "y": 0.5, "w": 0.7, "h": 0.04, "confidence": LOW_CONFIDENCE / 3})
    db.save(faint)
    return doc, faint.id


def test_ink_contrast_reads_the_enhanced_rendition_when_there_is_one(db, tmp_path):
    """The original has no contrast under the faint line (bleed-through would fire); the enhanced rendition has ink there,
    so the line stays. With the rendition's pixels also plain, the same line is left out."""
    from fichero_server.models import Segment
    from fichero_server.recipes import leave_out

    doc, faint = _faint_line_page(db, tmp_path, enhanced_dark=True)
    leave_out.leave_out_pages(db, [doc.id], "run-1")
    assert not db.get(Segment, faint).is_furniture, "the enhanced rendition shows ink under the line"

    doc2, faint2 = _faint_line_page(db, tmp_path, enhanced_dark=False)
    leave_out.leave_out_pages(db, [doc2.id], "run-2")
    assert db.get(Segment, faint2).metadata["left_out"]["why"] == leave_out.BLEED


def test_a_show_through_only_verso_has_every_line_left_out_with_the_page_level_reason_and_no_pixels_change(db, tmp_path):
    from fichero_server.models import Segment
    from fichero_server.recipes import leave_out

    doc, _ = _faint_line_page(db, tmp_path, enhanced_dark=True)
    doc.metadata = {"show_through_only": True}
    db.save(doc)
    before = {r.id: hashlib.sha256(open(r.path, "rb").read()).hexdigest() for r in db.query(Rendition, document_id=doc.id)}

    account = leave_out.leave_out_pages(db, [doc.id], "run-1")

    rows = [r for r in db.query(Segment, document_id=doc.id) if r.kind == "line"]
    assert len(rows) == 9 and all(r.is_furniture for r in rows)
    assert {r.metadata["left_out"]["why"] for r in rows} == {leave_out.SHOW_THROUGH_ONLY_VERSO}
    assert account["why"] == {leave_out.SHOW_THROUGH_ONLY_VERSO: 9}
    assert before == {r.id: hashlib.sha256(open(r.path, "rb").read()).hexdigest() for r in db.query(Rendition, document_id=doc.id)}
