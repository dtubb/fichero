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
    monkeypatch.setattr(turn_module, "read_lines", lambda image: _lines_of(180))  # the reader finds it upside down
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
