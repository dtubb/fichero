"""A photograph of a page on a dark table: the content box and the skew come from the page (#5382).

WHY: the review on the Sergio notebooks found `detect_content_bbox` returning the whole frame (the
grey table passes its > 20 threshold) and `detect_deskew_angle` returning 0.0 (it accepted the ruler
and table edges, which are exactly horizontal, not the writing).
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

pytest.importorskip("cv2")

from fichero_server.media.image_ops import auto_straighten_angle, detect_content_bbox, detect_deskew_angle


def _photo(tilt: float, with_text: bool = True) -> Image.Image:
    rng = np.random.default_rng(5)
    table = np.clip(40 + rng.normal(0, 3, (1000, 1500, 3)), 0, 255).astype("uint8")
    photo = Image.fromarray(table)
    ImageDraw.Draw(photo).rectangle([60, 30, 1440, 44], fill=(215, 215, 200))  # the ruler: long, level, bright
    page = Image.new("RGB", (1000, 760), (225, 222, 210))
    d = ImageDraw.Draw(page)
    if with_text:
        for row, y in enumerate(range(70, 700, 34)):
            x = 60
            while x < 900:
                w = int(rng.integers(30, 90))
                d.rectangle([x, y, x + w, y + 9], fill=(30, 30, 40))
                x += w + 14
    mask = Image.new("L", page.size, 255)
    page = page.rotate(tilt, expand=True, resample=Image.Resampling.BICUBIC)
    mask = mask.rotate(tilt, expand=True)
    photo.paste(page, (250, 120), mask)
    return photo


def test_the_content_box_leaves_the_grey_table_out():
    left, top, width, height = detect_content_bbox(_photo(0.0))
    # the ruler is bright too, so the box reaches it at the top; the left and right edges are the ruler's
    # (60..1440) - what must hold is that the frame (0, 0, 1500, 1000) is no longer the answer
    assert (left, top, width, height) != (0, 0, 1500, 1000)
    assert left >= 50 and left + width <= 1450
    assert top >= 25 and top + height <= 900


def test_the_content_box_of_the_page_alone_is_the_page():
    photo = _photo(0.0)
    ImageDraw.Draw(photo).rectangle([60, 30, 1440, 44], fill=(40, 40, 40))  # no ruler
    assert detect_content_bbox(photo) == (250, 120, 1000, 760)


@pytest.mark.parametrize("tilt", [1.0, -1.5])
def test_the_skew_is_read_from_the_writing_not_the_ruler(tilt):
    found = detect_deskew_angle(_photo(tilt))
    assert abs(abs(found) - abs(tilt)) < 0.3
    assert found * tilt < 0  # PIL turns counter-clockwise; the estimate is the slope in y-down pixels


def test_a_level_page_and_a_blank_one_read_zero():
    assert auto_straighten_angle(_photo(0.0)) == 0.0
    assert detect_deskew_angle(_photo(1.0, with_text=False)) == 0.0
