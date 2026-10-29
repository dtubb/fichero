"""A page bent toward its gutter is flattened (`prep.flatten.curve-toward-the-gutter`, #5382).

The page is drawn here: lines of word-sized ink blocks whose baselines follow a known quadratic. WHY: a bound page
curving into the gutter bends its lines, and a segmenter cuts across the bend; after flattening each baseline must be
straight within 2 px, and a page that was straight must be left exactly alone.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from fichero_server.media.flatten_curve import _baselines, flatten_curve

W, H = 800, 1000


def page(bend=0.0) -> Image.Image:
    """Ink blocks along each line; `bend` px is how far the line's ends sag below its middle."""
    img = Image.new("L", (W, H), 235)
    d = ImageDraw.Draw(img)
    for base in range(120, H - 100, 60):
        for x in range(70, W - 70, 22):
            sag = bend * ((x - W / 2) / (W / 2)) ** 2
            d.rectangle([x, base + sag - 22, x + 8, base + sag], fill=30)
    return img.convert("RGB")


def _worst_deviation(image) -> float:
    """The largest distance of any line's baseline from the straight line through its middle, in working pixels."""
    gray = np.asarray(image.convert("L"))
    worst = 0.0
    for coefficients, left, right in _baselines(gray):
        xs = np.linspace(left, right, 50)
        ys = np.polyval(coefficients, xs)
        worst = max(worst, float(np.abs(ys - np.polyval(np.polyfit(xs, ys, 1), xs)).max()))
    return worst


def test_a_bent_page_comes_out_with_straight_baselines_within_2_px():
    bent = page(bend=24)
    assert _worst_deviation(bent) > 5  # the lines really are bent
    result = flatten_curve(bent)
    assert result is not None
    flat, points = result
    assert _worst_deviation(flat) < 2.0
    assert len(points) >= 9 and all(len(p) == 3 for p in points)  # control points for the row


def test_a_straight_blank_or_empty_page_writes_nothing():
    assert flatten_curve(page(bend=0)) is None
    assert flatten_curve(Image.new("RGB", (W, H), (235, 235, 235))) is None
    one_line = Image.new("RGB", (W, H), (235, 235, 235))
    ImageDraw.Draw(one_line).rectangle([100, 400, 700, 420], fill=(30, 30, 30))
    assert flatten_curve(one_line) is None  # too few lines to measure


def test_page_crop_writes_a_flattened_rendition_for_a_bent_page_and_none_for_a_straight_one(db, tmp_path, monkeypatch):
    from fichero_server.media import find_page as module
    from fichero_server.models import DocType, Document, FileType, Rendition
    from fichero_server.recipes.page_crop import crop_pages

    monkeypatch.setattr(module, "find_page_vision", lambda image: None)

    def on_a_table(bend):
        table = Image.new("RGB", (W + 400, H + 300), (14, 12, 10))
        table.paste(page(bend), (200, 150))
        path = tmp_path / f"bend{bend}.png"
        table.save(path)
        doc = Document(name=path.name, doc_type=DocType.file, file_type=FileType.image, path=str(path), metadata={})
        db.save(doc)
        crop_pages(db, [doc.id], "run-1", prepare=True)
        return [r for r in db.query(Rendition, document_id=doc.id) if r.role == "flattened"]

    (row,) = on_a_table(24)
    assert row.transform.method == "flatten" and row.transform.control_points
    assert _worst_deviation(Image.open(row.path)) < 2.0
    assert on_a_table(0) == []
