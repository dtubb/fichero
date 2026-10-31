"""Square a lopsided page from its four corners (`prep.square.perspective-from-the-quad`, #5382).

The page is warped to a rectangle: `cv2.getPerspectiveTransform` and `cv2.warpPerspective`, to the size the longer
opposite sides give, white fill. The quad is the finder's (`media.find_page`: Vision's outline or the contour polygon) or
a person's dragged corners, in fractions of the upright image, ordered top-left, top-right, bottom-right, bottom-left.
The homography is returned so every later shape maps back to the photograph (`unsquare_points`).
"""
from __future__ import annotations

import math
from typing import Any

#: A side's angle from the frame's axes over this many degrees, or opposite sides differing by over this share, is lopsided.
TILT_DEGREES = 1.0
SIDE_MISMATCH = 0.02


def _pixels(quad: Any, size: tuple[int, int]) -> list[tuple[float, float]]:
    return [(float(x) * size[0], float(y) * size[1]) for x, y in quad]


def quad_is_rectangular(quad: Any, size: tuple[int, int]) -> bool:
    """Whether the quad (fractions) on an image of `size` is already a rectangle, so squaring writes nothing."""
    if len(quad) != 4:
        return True
    tl, tr, br, bl = _pixels(quad, size)
    for (ax, ay), (bx, by), horizontal in ((tl, tr, True), (bl, br, True), (tl, bl, False), (tr, br, False)):
        dx, dy = bx - ax, by - ay
        off = math.degrees(math.atan2(dy, dx)) if horizontal else math.degrees(math.atan2(dx, dy))
        if abs(off) > TILT_DEGREES:
            return False
    top, bottom = math.dist(tl, tr), math.dist(bl, br)
    left, right = math.dist(tl, bl), math.dist(tr, br)
    return abs(top - bottom) <= SIDE_MISMATCH * max(top, bottom) and abs(left - right) <= SIDE_MISMATCH * max(left, right)


def square_page(image: Any, quad: Any) -> tuple[Any, list[list[float]]]:
    """The page of PIL `image` warped to a rectangle from `quad`, and the 3x3 homography (photograph -> squared)."""
    import cv2
    import numpy as np
    from PIL import Image

    tl, tr, br, bl = _pixels(quad, image.size)
    width = max(2, round(max(math.dist(tl, tr), math.dist(bl, br))))
    height = max(2, round(max(math.dist(tl, bl), math.dist(tr, br))))
    source = np.array([tl, tr, br, bl], dtype=np.float32)
    target = np.array([(0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)], dtype=np.float32)
    homography = cv2.getPerspectiveTransform(source, target)
    warped = cv2.warpPerspective(np.asarray(image.convert("RGB")), homography, (width, height),
                                 flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
    return Image.fromarray(warped), homography.tolist()


def unsquare_points(homography: Any, points: Any) -> list[tuple[float, float]]:
    """Points in the squared page's pixels mapped back to the photograph's pixels."""
    import cv2
    import numpy as np

    inverse = np.linalg.inv(np.asarray(homography, dtype=np.float64))
    mapped = cv2.perspectiveTransform(np.asarray(points, dtype=np.float64).reshape(-1, 1, 2), inverse)
    return [(float(x), float(y)) for x, y in mapped.reshape(-1, 2)]
