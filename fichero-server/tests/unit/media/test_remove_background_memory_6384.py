"""Removing the background of a very large scan stays inside a memory budget (`image.ops.long-operation-is-bounded`, #6384).

WHY: on an 8 GB Mac the default method took ~30 bytes a pixel on top of the engine, the engine was killed, the request closed and
every other call failed until it came back. The page outline now comes from a bounded copy and the page is cut before its
transparency is built.
"""
from __future__ import annotations

import tracemalloc

import numpy as np
import pytest
from PIL import Image

from fichero_server.media import image_ops

pytest.importorskip("cv2")
BYTES_PER_PIXEL = 14  # the source itself is 3; the cut page and its alpha are the rest. The old path was ~30.


def _scan(width: int, height: int) -> Image.Image:
    pixels = np.full((height, width, 3), 235, np.uint8)
    pixels[:150] = 10
    pixels[:, :150] = 10
    pixels[-150:] = 10
    pixels[:, -150:] = 10
    return Image.fromarray(pixels)


def test_a_large_scan_is_cut_inside_the_memory_budget():
    image = _scan(7000, 5000)  # 35 MP
    tracemalloc.start()
    try:
        page = image_ops.remove_black_background_opencv(image)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < BYTES_PER_PIXEL * image.width * image.height, f"peak {peak / 1e6:.0f} MB for {image.width * image.height / 1e6:.0f} MP"
    assert page.mode == "RGBA" and 6600 < page.width <= 7000 and 4600 < page.height <= 5000


def test_the_cut_keeps_the_page_and_drops_the_ground():
    page = image_ops.remove_black_background_opencv(_scan(4000, 3000))
    alpha = np.asarray(page.getchannel("A"))
    assert alpha[page.height // 2, page.width // 2] == 255
    assert page.width < 4000 and page.height < 3000  # the black border is cropped away
