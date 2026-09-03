"""The ink-residue escalation's rect finder (Daniel, 2026-09-02: sparse-area
bounding-box review pass). `_uncovered_ink_rects` names WHERE the page still
holds text ink no word box covers, in the image's own normalized frame, so
the caller can crop and re-OCR at region scale. Pinned on synthetic pixels:
it must see uncovered ink, ignore covered ink, ignore page furniture (ruled
lines, dark backdrop), and stay bounded (rect cap, merge-span cap).

Verified against real Marshall diary pages in
agent-work/design/local-vision-bbox-lab.md (text-ink coverage 0.26 -> 0.70 on
dense small print; missed faint-pencil lines recovered).
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from fichero_server.workflows.tools.vision_base import (
    VisionOCRBox,
    _long_run_mask,
    _uncovered_ink_rects,
)


W, H = 800, 600


def _page(tmp_path, marks, *, lines_y=(), backdrop_frac=0.0, name="page.png"):
    """White page with thin dark stroke marks at normalized rects.

    Marks are stroke-thin (5px) on purpose: the detector measures ink
    against a 15px local median background, exactly like real pen strokes.
    """
    img = Image.new("L", (W, H), 245)
    draw = ImageDraw.Draw(img)
    if backdrop_frac:
        draw.rectangle([0, 0, int(W * backdrop_frac), H], fill=15)
    for x, y in marks:
        draw.rectangle([x * W, y * H, x * W + 30, y * H + 5], fill=10)
    for y in lines_y:
        draw.rectangle([0, y * H, W, y * H + 3], fill=10)
    p = tmp_path / name
    img.save(p)
    return str(p)


def _word_box(rect):
    return VisionOCRBox(text="word", bbox=list(rect), confidence=0.9)


def test_uncovered_ink_is_named_where_it_sits(tmp_path):
    page = _page(tmp_path, [(0.50, 0.50)])

    rects = _uncovered_ink_rects(page, [])

    assert rects, "an uncovered stroke must produce a crop rect"
    x, y, w, h = rects[0]
    # The rect contains the mark, in the page's own normalized frame.
    assert x <= 0.50 <= x + w
    assert y <= 0.50 <= y + h


def test_ink_inside_a_word_box_is_covered(tmp_path):
    page = _page(tmp_path, [(0.50, 0.50)])
    box = _word_box([0.48, 0.48, 0.10, 0.06])

    assert _uncovered_ink_rects(page, [box]) == []


def test_ruled_lines_are_furniture_not_ink(tmp_path):
    page = _page(tmp_path, [], lines_y=[0.2, 0.4, 0.6, 0.8])

    assert _uncovered_ink_rects(page, []) == []


def test_dark_backdrop_is_not_ink(tmp_path):
    page = _page(tmp_path, [], backdrop_frac=0.25)

    assert _uncovered_ink_rects(page, []) == []


def test_blank_page_yields_nothing(tmp_path):
    page = _page(tmp_path, [])

    assert _uncovered_ink_rects(page, []) == []


def test_rect_count_is_capped(tmp_path):
    # Ink in every grid cell: without the cap this would be a rect per cell.
    marks = [(c / 10 + 0.03, r / 10 + 0.03) for r in range(1, 9) for c in range(1, 9)]
    page = _page(tmp_path, marks)

    rects = _uncovered_ink_rects(page, [], max_rects=8)

    assert 0 < len(rects) <= 8


def test_merged_rects_stay_region_scale(tmp_path):
    # The re-read only helps because the crop zooms the glyphs, so a merge
    # must never swallow the page (3x3 cells of an 8-cell grid, plus pad).
    marks = [(c / 10 + 0.03, r / 10 + 0.03) for r in range(1, 9) for c in range(1, 9)]
    page = _page(tmp_path, marks)

    for _x, _y, w, h in _uncovered_ink_rects(page, []):
        assert w <= 3 / 8 + 0.04
        assert h <= 3 / 8 + 0.04


def test_missing_file_returns_no_rects(tmp_path):
    assert _uncovered_ink_rects(str(tmp_path / "nope.png"), []) == []


def test_long_run_mask_finds_the_rule_and_spares_the_word():
    mask = np.zeros((20, 200), dtype=bool)
    mask[5, 10:190] = True   # a ruled line
    mask[10, 50:80] = True   # a word-length stroke

    runs = _long_run_mask(mask, 100, axis=1)

    assert runs[5, 10:190].all()
    assert not runs[10].any()
