"""Turn by the text, straighten with the angle on the row, blank pages (`prep.turn-by-the-text`,
`prep.straighten-and-flatten`, `prep.blank-pages-marked`, #5382, #6190).

WHY: a page lying on its side reads as noise; the model needs it upright. The turn is decided by where the reader's
lines sit in reading order (Vision reads sideways text as well as upright, so a word count cannot tell).
"""
from __future__ import annotations

import pytest
from PIL import Image, ImageDraw

from fichero_server.media.turn_by_text import turn_by_text


def _lines_of(turn_applied, n=6):
    """The lines Vision returns for a page of `n` lines that was laid by `turn_applied` (counter-clockwise): its
    reading order, positions as fractions, as measured on drawn pages (first line first)."""
    upright = [(0.04, 0.07 + 0.13 * i, 0.45, 0.07) for i in range(n)]  # text runs along, lines go down
    if turn_applied == 0:
        return upright
    if turn_applied == 180:
        return [(1 - x - w, 1 - y - h, w, h) for x, y, w, h in upright]
    if turn_applied == 90:  # ROTATE_90: top goes left; lines go left to right and are tall
        return [(y, 1 - x - w, h, w) for x, y, w, h in upright]
    return [(1 - y - h, x, h, w) for x, y, w, h in upright]  # 270: top goes right; lines go right to left


@pytest.mark.parametrize("turn_applied,expected", [(0, 0), (90, 270), (180, 180), (270, 90)])
def test_a_page_on_its_side_or_upside_down_is_turned_upright(turn_applied, expected):
    page = Image.new("RGB", (400, 300) if turn_applied in (0, 180) else (300, 400))
    decision = turn_by_text(page, reader=lambda _image: _lines_of(turn_applied))
    assert decision["angle"] == expected, decision
    assert decision["reason"]


def test_too_few_or_disagreeing_lines_are_not_turned():
    page = Image.new("RGB", (400, 300))
    assert turn_by_text(page, reader=lambda _i: _lines_of(180, n=2))["angle"] == 0  # two lines: too few to tell
    zigzag = [(0.04, y, 0.45, 0.07) for y in (0.1, 0.5, 0.2, 0.6, 0.3, 0.7)]
    assert turn_by_text(page, reader=lambda _i: zigzag)["angle"] == 0
    assert turn_by_text(page, reader=lambda _i: [])["angle"] == 0


def test_vision_reads_the_real_turn_of_a_drawn_page():
    """The real reader (Apple Vision) on a drawn page of different lines: upright left alone, the others turned back."""
    pytest.importorskip("Vision")
    from PIL import ImageFont

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 44)
    except OSError:
        pytest.skip("no system font")
    img = Image.new("RGB", (900, 600), "white")
    d = ImageDraw.Draw(img)
    for i, words in enumerate(["alpha beta gamma", "delta epsilon zeta", "eta theta iota", "kappa lambda mu",
                               "nu xi omicron", "pi rho sigma"]):
        d.text((40, 40 + i * 80), words, fill="black", font=font)
    assert turn_by_text(img)["angle"] == 0
    assert turn_by_text(img.transpose(Image.Transpose.ROTATE_180))["angle"] == 180
    assert turn_by_text(img.transpose(Image.Transpose.ROTATE_90))["angle"] == 270
    assert turn_by_text(img.transpose(Image.Transpose.ROTATE_270))["angle"] == 90


def _ruled(angle):
    """A ruled page, its lines turned `angle` degrees."""
    img = Image.new("RGB", (900, 700), (235, 230, 215))
    d = ImageDraw.Draw(img)
    for y in range(80, 640, 40):
        d.line([(40, y), (860, y)], fill=(40, 40, 70), width=3)
    return img.rotate(angle, resample=Image.Resampling.BICUBIC, fillcolor=(235, 230, 215))


def test_the_straighten_angle_is_found_and_a_level_page_gets_none():
    from fichero_server.media.image_ops import auto_straighten_angle

    assert abs(abs(auto_straighten_angle(_ruled(3.0))) - 3.0) < 0.5
    assert auto_straighten_angle(_ruled(0.0)) == 0.0
    assert auto_straighten_angle(_ruled(0.1)) == 0.0  # under 0.3 degrees: skipped


def test_the_deskew_node_writes_the_angle_on_the_row_and_no_row_for_a_level_page(db, tmp_path, test_package):
    import asyncio

    from fichero_server.llm import LLMConfig
    from fichero_server.models import DocType, Document, FileType, ImageEditChain
    from fichero_server.workflows.tools.deskew_images import deskew_images

    docs = {}
    for name, angle in (("tilted", 3.0), ("level", 0.0)):
        path = tmp_path / f"{name}.png"
        _ruled(angle).save(path)
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
        db.save(doc)
        docs[name] = doc
    state = {"library_path": str(test_package)}
    asyncio.run(deskew_images({"documents": [{"id": d.id} for d in docs.values()]}, state, LLMConfig(provider="none", model="none")))

    (chain,) = db.query(ImageEditChain, document_id=docs["tilted"].id)
    (op,) = chain.operations
    assert op["op"] == "auto_deskew" and abs(abs(op["params"]["angle"]) - 3.0) < 0.5 and op["method"] == "hough"
    assert db.query(ImageEditChain, document_id=docs["level"].id) == [], "a level page writes no row"


def test_page_crop_prepare_turns_and_straightens_in_renditions(db, tmp_path, monkeypatch):
    from fichero_server.media import find_page as module
    from fichero_server.media import turn_by_text as turn_module
    from fichero_server.models import DocType, Document, FileType, Rendition
    from fichero_server.recipes.page_crop import crop_pages

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)
    monkeypatch.setattr(turn_module, "read_lines", lambda image, db_path=None: _lines_of(180))  # the reader finds it upside down
    table = Image.new("RGB", (1400, 1100), (14, 12, 10))
    table.paste(_ruled(2.0).resize((900, 700)), (250, 200))
    path = tmp_path / "photo.png"
    table.save(path)
    doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc)

    crop_pages(db, [doc.id], "run-1", prepare=True)

    rows = {r.role: r for r in db.query(Rendition, document_id=doc.id)}
    assert rows["rotated"].transform.angle == 180 and "180" in rows["rotated"].note
    assert "deskewed" in rows or "squared" in rows  # the page is a little off: it is straightened or squared first
    # a plain crop (what Find Regions asks for) makes neither
    doc2 = Document(name="b.png", doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
    db.save(doc2)
    crop_pages(db, [doc2.id], "run-2")
    assert {r.role for r in db.query(Rendition, document_id=doc2.id)} == {"crop"}


def _graph_paper(ink=False):
    img = Image.new("RGB", (900, 1200), (238, 236, 224))
    d = ImageDraw.Draw(img)
    for x in range(0, 900, 30):
        d.line([(x, 0), (x, 1200)], fill=(150, 180, 205), width=2)
    for y in range(0, 1200, 30):
        d.line([(0, y), (900, y)], fill=(150, 180, 205), width=2)
    if ink:
        for i in range(6):
            d.text((60, 100 + i * 60), "Entered the camp at noon and wrote", fill=(25, 25, 40))
            d.rectangle([60, 130 + i * 60, 420, 136 + i * 60], fill=(25, 25, 40))
    return img


def test_a_blank_graph_paper_page_is_blank_and_a_written_one_is_not():
    """`prep.blank-pages-marked`: ink under 0.2 % after the ruling mask."""
    from fichero_server.media.blank_page import ink_share, is_blank

    assert is_blank(_graph_paper(ink=False)), ink_share(_graph_paper(ink=False))
    assert not is_blank(_graph_paper(ink=True)), ink_share(_graph_paper(ink=True))
    assert is_blank(Image.new("RGB", (900, 1200), (238, 236, 224)))


def _ledger_with_strokes(strokes: int):
    """A ruled page, full-width bars every 40 px, with `strokes` short handwritten-like dashes."""
    img = Image.new("RGB", (900, 1200), (238, 236, 224))
    d = ImageDraw.Draw(img)
    for y in range(80, 1200, 40):
        d.line([(0, y), (900, y)], fill=(40, 40, 60), width=2)
    for i in range(strokes):
        d.line([(120 + i * 200, 300 + i * 90), (170 + i * 200, 320 + i * 90)], fill=(25, 25, 40), width=4)
    return img


def test_a_ruled_page_with_a_little_writing_is_unsure_not_hidden():
    """`prep.blank-pages-marked`: hidden only when sure; a ruled ledger page with three strokes is a proposal."""
    from fichero_server.media.blank_page import blank_verdict

    assert blank_verdict(_ledger_with_strokes(0)) == "blank"  # bars alone are ruling
    assert blank_verdict(_ledger_with_strokes(3)) != "blank"
    assert blank_verdict(Image.new("RGB", (900, 1200), (238, 236, 224))) == "blank"  # truly empty
    assert blank_verdict(Image.new("RGB", (900, 1200), (238, 236, 224)), has_lines=True) == "unsure"


def test_a_vision_warning_from_the_turn_read_never_opens_the_app_database(monkeypatch):
    """Review finding: `get_activity_tracker(None)` opens the REAL app database; the turn read has no library to log to."""
    from fichero_server.media.turn_by_text import read_lines
    from fichero_server.workflows import activity
    from fichero_server.workflows.tools import vision_base

    opened: list = []
    monkeypatch.setattr(activity, "get_activity_tracker", lambda path=None: opened.append(path))

    def fails(path, language="en", reference_text=None):
        vision_base._log_vision_warning("Apple Vision OCR failed: probe", path)
        raise ValueError("probe")

    monkeypatch.setattr(vision_base, "apple_vision_ocr_with_geometry", fails)
    assert read_lines(Image.new("RGB", (40, 40), "white")) == []
    assert opened == []


def _pencil_scan(width, height, entries, grey=175, stroke=3):
    """A big scan of plain paper with `entries` short pencil lines of handwriting-like strokes (thin, lightish)."""
    img = Image.new("RGB", (width, height), (238, 236, 224))
    d = ImageDraw.Draw(img)
    for i in range(entries):
        y = 400 + i * 260
        x = 300
        for _ in range(14):  # a word: a run of short slanted strokes
            d.line([(x, y), (x + 40, y - 70)], fill=(grey,) * 3, width=stroke)
            d.line([(x + 40, y - 70), (x + 80, y)], fill=(grey,) * 3, width=stroke)
            x += 110
    return img


def test_written_pages_are_never_called_blank_at_scan_size():
    """Review finding: shrinking to 900 px averaged thin pencil below the contrast cut and hid pages with writing."""
    from fichero_server.media.blank_page import blank_verdict

    assert blank_verdict(_pencil_scan(3000, 4200, 0)) == "blank"
    for entries in (2, 3, 4, 6):
        assert blank_verdict(_pencil_scan(3000, 4200, entries)) != "blank", entries
    assert blank_verdict(_pencil_scan(3000, 4200, 4, grey=195, stroke=2)) != "blank"  # faint, thin pencil


def test_the_ink_share_is_of_the_paper_not_the_mount():
    """A page on a big dark-less table: the same writing is a larger share of the page box than of the whole picture."""
    from fichero_server.media.blank_page import ink_share

    img = Image.new("RGB", (3000, 3000), (238, 236, 224))
    d = ImageDraw.Draw(img)
    for i in range(3):
        d.line([(400 + 200 * i, 500), (440 + 200 * i, 560)], fill=(60, 60, 60), width=5)
    assert ink_share(img, [0.1, 0.1, 0.3, 0.3]) > 3 * ink_share(img)


def test_the_text_read_is_asked_only_when_the_ink_alone_would_hide_the_page():
    from fichero_server.media.blank_page import blank_verdict

    asked = []

    def reads():
        asked.append(1)
        return True

    assert blank_verdict(_graph_paper(ink=True), reads) == "ink" and asked == []
    assert blank_verdict(_graph_paper(ink=False), reads) == "unsure" and asked == [1]
