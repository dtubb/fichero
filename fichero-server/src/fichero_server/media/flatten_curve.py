"""Flatten a bound page whose text lines curve toward the gutter (`prep.flatten.curve-toward-the-gutter`, #5382).

Text lines are found as connected components of the ink mask joined along the line; each line's baseline (the bottom
edge of its ink) is fitted with a quadratic. A page whose median baseline sag is over `CURVE_MIN` of the page height is
flattened: every baseline is moved to the height it has at the line's middle, and the rows between baselines follow
(a smooth displacement field, `cv2.remap`). A straight page, a blank page or a page with too few lines is left alone
(`flatten_curve` returns None).

ponytail: the field interpolates linearly between baselines down each column and is then blurred, not the thin-plate
spline of the spec (scipy is not a declared dependency of the engine); it does not even out the stretch toward the
gutter, and it reads the whole page, not the gutter side. Upgrade path: a thin-plate spline through the same control
points, and the bake-off keeping the step only where reading does not get worse (`prep.flatten.judged-by-the-gutter-third`).
"""
from __future__ import annotations

from typing import Any

import numpy as np

WORK_SIDE = 1000
#: Median baseline sag (the largest gap between the fitted curve and its chord) over this share of the page's height.
CURVE_MIN = 0.005
#: A line is at least this share of the page's width; fewer lines than this and there is nothing to measure.
LINE_MIN_WIDTH = 0.3
MIN_LINES = 3
#: Control points kept per line on the row.
SAMPLES = 9


def _baselines(gray: np.ndarray) -> list[tuple[np.ndarray, int, int]]:
    """Each text line's quadratic baseline `(coefficients, x_left, x_right)` in the working image's pixels."""
    import cv2

    h, w = gray.shape
    _, ink = cv2.threshold(cv2.GaussianBlur(gray, (3, 3), 0), 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if ink.mean() / 255 > 0.5 or not ink.any():
        return []
    # The mount around a padded page box is "ink" too and joins every line to the frame: ink that touches the edge is not text.
    count, labels = cv2.connectedComponents(ink)
    edge = np.unique(np.concatenate([labels[0], labels[-1], labels[:, 0], labels[:, -1]]))
    ink[np.isin(labels, edge[edge > 0])] = 0
    if not ink.any():
        return []
    joined = cv2.dilate(ink, cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, round(0.04 * w)), 3)))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(joined)
    lines = []
    for i in range(1, count):
        x, y, bw, bh, _area = (int(v) for v in stats[i])
        if bw < LINE_MIN_WIDTH * w or bh > 0.15 * h:
            continue
        mine = (labels[y:y + bh, x:x + bw] == i) & (ink[y:y + bh, x:x + bw] > 0)
        columns = np.flatnonzero(mine.any(axis=0))
        if len(columns) < 0.25 * bw:
            continue
        bottoms = bh - 1 - np.argmax(mine[::-1, columns], axis=0) + y
        xs = (columns + x).astype(float)
        keep = np.ones(len(xs), bool)
        for _ in range(3):  # descenders and stray marks sit below the baseline: refit without the outliers
            coefficients = np.polyfit(xs[keep], bottoms[keep], 2)
            residual = bottoms - np.polyval(coefficients, xs)
            limit = max(2.0, 2.5 * float(np.median(np.abs(residual[keep]))))
            keep = np.abs(residual) <= limit
            if keep.sum() < 10:
                break
        lines.append((coefficients, x, x + bw - 1))
    return lines


def _sag(coefficients: np.ndarray, left: int, right: int) -> float:
    return abs(float(coefficients[0])) * (right - left) ** 2 / 4


def flatten_curve(image: Any) -> tuple[Any, list[list[float]]] | None:
    """The page flattened and the control points `[x, y, dy]` (fractions of the page) of the field, or None where the
    page is straight, blank or has too few text lines."""
    import cv2
    from PIL import Image

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    scale = min(1.0, WORK_SIDE / max(height, width))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if scale < 1:
        gray = cv2.resize(gray, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    h, w = gray.shape
    lines = _baselines(gray)
    if len(lines) < MIN_LINES:
        return None
    if float(np.median([_sag(*line) for line in lines])) / h < CURVE_MIN:
        return None
    # Each baseline goes to the height it has at the line's middle; the field is the source row for each output row.
    ordered = sorted(lines, key=lambda line: np.polyval(line[0], (line[1] + line[2]) / 2))
    targets = np.array([np.polyval(c, (a + b) / 2) for c, a, b in ordered])
    xs = np.arange(w, dtype=float)
    offsets = np.stack([np.polyval(c, np.clip(xs, a, b)) - t for (c, a, b), t in zip(ordered, targets)])
    rows = np.arange(h, dtype=float)
    field = np.stack([np.interp(rows, targets, offsets[:, x]) for x in range(w)], axis=1).astype(np.float32)
    field = cv2.GaussianBlur(field, (0, 0), max(2.0, 0.01 * h))
    full = cv2.resize(field, (width, height), interpolation=cv2.INTER_LINEAR) / scale
    map_x, map_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    flat = cv2.remap(rgb, map_x, map_y + full, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    picks = np.linspace(0, w - 1, SAMPLES).round().astype(int)
    points = [[round(float(x) / w, 5), round(float(t) / h, 5), round(float(offsets[i, x]) / h, 5)]
              for i, t in enumerate(targets) for x in picks]
    return Image.fromarray(flat), points
