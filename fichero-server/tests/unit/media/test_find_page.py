"""The classical page finder on synthetic Doc11-like scans (`image.enhance.page-crop`, #6188/#6198).

Fixtures are drawn here (paper on a dark mount, a striped wooden ruler, a grey colour card): the owner's scans are not
copied into the repo. WHY: the finder must return the paper, never the ruler or the card, so Kraken runs only on it.
"""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image, ImageDraw

from fichero_server.media.find_page import find_page

W, H = 1600, 1200
PAPER = (222, 208, 176)
PAGE = (330, 260, 1450, 1100)  # left, top, right, bottom


def scan(*, ruler=True, card=True, dark=True, touching=False) -> Image.Image:
    img = Image.new("RGB", (W, H), (18, 16, 14) if dark else (128, 122, 116))
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(1)
    paper = np.clip(np.array(PAPER) + rng.normal(0, 6, (PAGE[3] - PAGE[1], PAGE[2] - PAGE[0], 3)), 0, 255).astype("uint8")
    img.paste(Image.fromarray(paper), PAGE[:2])
    for y in range(500, 1000, 60):  # ink lines
        d.line([(400, y), (1380, y)], fill=(60, 50, 40), width=6)
    if ruler:  # wooden ruler down the left edge, cm ticks
        right = PAGE[0] - 5 if touching else 120
        d.rectangle([20, 0, right, H], fill=(170, 130, 80))
        for y in range(0, H, 14):
            d.line([(20, y), (60 if y % 70 else 100, y)], fill=(30, 20, 10), width=2)
    if card:  # grey colour card at the top
        d.rectangle([600, 20, 1100, 200], fill=(150, 150, 150))
        for i in range(6):
            d.rectangle([610 + i * 80, 40, 670 + i * 80, 180], fill=(40 * i, 200 - 30 * i, 90))
    return img


@pytest.mark.parametrize("kw", [{}, {"touching": True}, {"dark": False}, {"ruler": False, "card": False}],
                         ids=["dark+ruler+card", "ruler touching the page", "light table", "bare page"])
def test_the_page_is_found_and_the_ruler_and_card_are_left_out(kw):
    found = find_page(scan(**kw))
    assert found is not None
    left, top, right, bottom = found.pixels(W, H)
    # within 2 % of the image of the hand-drawn box (spec: outline within 2 %)
    tol = 0.02 * max(W, H)
    assert abs(left - PAGE[0]) < tol and abs(right - PAGE[2]) < tol, found
    assert abs(top - PAGE[1]) < tol and abs(bottom - PAGE[3]) < tol, found


def test_a_page_that_fills_the_frame_is_not_cropped():
    assert find_page(Image.new("RGB", (W, H), PAPER)) is None


def test_the_ruler_and_the_colour_card_are_named_as_furniture():
    """WHY: Leave Out gives a line on the ruler the reason `ruler`, not just `off the page` (#6198)."""
    kinds = {f["kind"] for f in find_page(scan()).furniture}
    assert kinds == {"ruler", "colour card"}, kinds
