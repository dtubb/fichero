"""The content box is a numpy reduction and the dark-mount method keeps its answer (`prep.crop.content-bbox-is-fast`,
`prep.page.remove-background-is-the-dark-mount-method`, #6190, #6188). Fixtures are drawn, never the owner's scans."""
from __future__ import annotations

import time

import numpy as np
from PIL import Image

from fichero_server.media.image_ops import detect_content_bbox, remove_black_background_opencv


def _loop_reference(image):  # the per-pixel loop this replaced: the answer must not change
    gray = image.convert("L")
    px = gray.load()
    xs, ys = [], []
    for y in range(gray.height):
        for x in range(gray.width):
            if px[x, y] > 20:
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0, 0, image.width, image.height
    return min(xs), min(ys), max(xs) + 1 - min(xs), max(ys) + 1 - min(ys)


def _mount(w=600, h=400):
    rng = np.random.default_rng(3)
    arr = np.full((h, w, 3), 8, "uint8")
    arr[60:340, 90:520] = np.clip(215 + rng.normal(0, 5, (280, 430, 3)), 0, 255).astype("uint8")
    return Image.fromarray(arr)


def test_content_bbox_is_fast_and_gives_the_same_answer():
    small = _mount()
    assert detect_content_bbox(small) == _loop_reference(small) == (90, 60, 430, 280)
    assert detect_content_bbox(Image.new("RGB", (50, 40), 0)) == (0, 0, 50, 40)  # nothing: the whole frame
    big = Image.fromarray(np.full((2000, 3000, 3), 8, "uint8"))
    big.paste(Image.new("RGB", (2400, 1700), (200, 200, 200)), (300, 150))
    start = time.perf_counter()
    assert detect_content_bbox(big) == (300, 150, 2400, 1700)
    assert time.perf_counter() - start < 0.2  # the spec's bound is 0.5 s; the loop took 0.52 s


def test_remove_background_still_lifts_the_page_on_a_dark_mount():
    """An existing chain row named `remove_background` re-renders the page, unchanged (the feather adds a rim)."""
    lifted = remove_black_background_opencv(_mount())
    assert lifted.size == (448, 298) and lifted.mode == "RGBA"


def _faded_page():
    rng = np.random.default_rng(5)
    arr = np.clip(np.array([200, 190, 160]) + rng.normal(0, 3, (240, 320, 3)), 0, 255).astype("uint8")
    for y in range(40, 220, 30):
        arr[y:y + 4, 30:290] = (150, 140, 120)  # faint ink
    return Image.fromarray(arr)


def test_contrast_clahe_widens_the_lightness_and_keeps_the_colour():
    """`image.enhance.contrast-clahe`: LAB CLAHE on L (handwritten: clip 2.2, tile 8, x1.1 -5); a/b untouched."""
    import cv2

    from fichero_server.media.image_ops import apply_clahe_contrast, apply_operation

    page = _faded_page()
    out = apply_clahe_contrast(page)
    before, after = (cv2.cvtColor(np.asarray(i.convert("RGB")), cv2.COLOR_RGB2LAB) for i in (page, out))
    assert after[:, :, 0].std() > 1.25 * before[:, :, 0].std(), "ink stands out more"
    assert np.abs(after[:, :, 1:].astype(int) - before[:, :, 1:]).mean() < 2, "the page stays its colour"
    # params reach it through the edit chain, and the typescript profile is a different curve
    chained = apply_operation(page, {"op": "contrast", "params": {"profile": "typescript"}})
    assert np.abs(np.asarray(chained, int) - np.asarray(out, int)).mean() > 0.5
    # an old chain row (a bare factor) is still the PIL contrast, unchanged
    old = apply_operation(page, {"op": "contrast", "params": {"factor": 1.0}})
    assert np.array_equal(np.asarray(old), np.asarray(page))
