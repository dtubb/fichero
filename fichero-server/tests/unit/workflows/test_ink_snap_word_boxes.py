"""The ink-snap word-box refinement (C2, 2026-08-24): tighten-only, bounded,
and never moves a box that shows no ink. Verified visually on Marshall
IMG_005 (two-line-tall cursive boxes collapse onto their words); these pin
the mechanics on synthetic pixels.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from fichero_server.workflows.tools.vision_base import (
    VisionOCRBox,
    _snap_word_boxes_to_ink,
)


def _page(tmp_path, marks):
    """White 1000x500 page with black rectangles at normalized rects."""
    img = Image.new("L", (1000, 500), 245)
    draw = ImageDraw.Draw(img)
    for x, y, w, h in marks:
        draw.rectangle([x * 1000, y * 500, (x + w) * 1000, (y + h) * 500], fill=10)
    p = tmp_path / "page.png"
    img.save(p)
    return str(p)


def _box(rect):
    return VisionOCRBox(text="word", bbox=list(rect), confidence=0.9)


def test_sloppy_box_snaps_to_the_ink(tmp_path):
    # Ink at [0.40, 0.40, 0.10, 0.05]; box is generous on every side.
    page = _page(tmp_path, [(0.40, 0.40, 0.10, 0.05)])
    box = _box([0.35, 0.34, 0.20, 0.17])

    moved = _snap_word_boxes_to_ink(page, [box])

    assert moved == 1
    x, y, w, h = box.bbox
    # Tighter on every edge, still CONTAINING the ink.
    assert 0.35 < x <= 0.40 and x + w >= 0.50
    assert 0.34 < y <= 0.40 and y + h >= 0.45
    assert w < 0.20 and h < 0.17


def test_blank_box_is_never_moved(tmp_path):
    page = _page(tmp_path, [(0.40, 0.40, 0.10, 0.05)])
    blank = _box([0.70, 0.70, 0.10, 0.10])  # clean paper

    moved = _snap_word_boxes_to_ink(page, [blank])

    assert moved == 0
    assert blank.bbox == [0.70, 0.70, 0.10, 0.10]


def test_trim_is_capped_never_a_teleport(tmp_path):
    # A sliver of ink at the box's far right: an uncapped snap would collapse
    # the box onto the sliver; the cap keeps each edge within 35% of the box.
    page = _page(tmp_path, [(0.53, 0.40, 0.02, 0.05)])
    box = _box([0.20, 0.38, 0.36, 0.09])

    _snap_word_boxes_to_ink(page, [box])

    x, _, w, _ = box.bbox
    assert x <= 0.20 + 0.36 * 0.35 + 0.001  # left edge moved at most the cap
    assert x + w >= 0.55  # still reaches the ink


def test_unreadable_image_is_a_quiet_no_op(tmp_path):
    box = _box([0.1, 0.1, 0.2, 0.1])
    assert _snap_word_boxes_to_ink(str(tmp_path / "missing.png"), [box]) == 0
    assert box.bbox == [0.1, 0.1, 0.2, 0.1]
