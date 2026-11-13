"""A line's outline drawn again from its baseline and the page image.

`segment-editor.regenerate-polygon-from-baseline`: Kraken's polygonal-environment routine
(`kraken.lib.segmentation.calculate_polygonal_environment`, the call eScriptorium's "recalculate masks"
makes) on the current image, with the page's other baselines as bounds so outlines do not overlap. Where
it finds no ink to measure, a fixed height in image pixels draws a band over the baseline instead.

Kraken ships in the engine's Kraken bundle, not its core; without it only the fixed height can draw.
"""

from __future__ import annotations

import logging
import math
from typing import Any

logger = logging.getLogger(__name__)

#: How far a fixed-height band reaches below the baseline, as a share of its height: the descenders.
_DESCENT = 0.25
#: The share of an outline's pixels that must be dark for it to have measured ink.
_INK_SHARE = 0.01

Points = list[list[float]]


def kraken_available() -> bool:
    try:
        from kraken.lib.segmentation import calculate_polygonal_environment  # noqa: F401
    except Exception:  # pragma: no cover - the bundle decides
        return False
    return True


def has_ink(gray: Any, polygon: Points) -> bool:
    """Whether the outline holds ink: more than `_INK_SHARE` of its pixels darker than mid-grey."""
    import cv2
    import numpy as np

    pixels = np.asarray(gray)
    mask = np.zeros(pixels.shape, dtype=np.uint8)
    cv2.fillPoly(mask, [np.array([[round(x), round(y)] for x, y in polygon], dtype=np.int32)], 1)
    inside = mask.astype(bool)
    if not inside.any():
        return False
    return float((pixels[inside] < 128).mean()) > _INK_SHARE


def band(baseline: Points, height: float) -> Points:
    """A band `height` pixels tall over the baseline (and a quarter of that under it): each point moved along
    the line's normal, up for the top edge and down for the bottom, the bottom walked back."""
    top, bottom = [], []
    for i, (x, y) in enumerate(baseline):
        a = baseline[max(i - 1, 0)]
        b = baseline[min(i + 1, len(baseline) - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy) or 1.0
        # The normal pointing up the page for a line read left to right (image y grows downward).
        nx, ny = dy / length, -dx / length
        top.append([x + nx * height, y + ny * height])
        bottom.append([x - nx * height * _DESCENT, y - ny * height * _DESCENT])
    return top + bottom[::-1]


def outlines(image: Any, baselines: list[Points], bounds: list[Points], fixed_height: float | None) -> list[Points | None]:
    """One outline per baseline, in image pixels, or None where none can be drawn.

    `image` is the page as a PIL image; `bounds` are the neighbouring baselines, which no outline crosses.
    """
    found: list[Points | None] = [None] * len(baselines)
    if kraken_available() and baselines:
        from kraken.lib.segmentation import calculate_polygonal_environment

        try:
            drawn = calculate_polygonal_environment(
                image.convert("L"),
                baselines=[[(int(round(x)), int(round(y))) for x, y in line] for line in baselines],
                suppl_obj=[[(int(round(x)), int(round(y))) for x, y in line] for line in bounds] or None,
            )
            found = [
                [[float(x), float(y)] for x, y in polygon] if polygon is not None and len(polygon) >= 3 else None
                for polygon in drawn
            ]
        except Exception as why:  # Kraken refuses some pages outright (no ink, a degenerate line)
            logger.info("outline from baseline: kraken drew nothing (%s)", why)
        # On a page with no ink Kraken still answers, with an outline that runs to the page's edge; an outline
        # holding (almost) no dark pixels measured nothing and is not kept.
        gray = image.convert("L")
        found = [polygon if polygon is not None and has_ink(gray, polygon) else None for polygon in found]
    if fixed_height:
        found = [polygon if polygon is not None else band(line, fixed_height) for polygon, line in zip(found, baselines)]
    return found
