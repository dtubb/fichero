"""The Paintbrush's stroke made into a line (`segment-editor.paintbrush`): the painted area is the outline, the stroke's
own path the baseline. In the page image's pixels; pure, so it is tested without a page."""
from __future__ import annotations

import cv2
import numpy as np

Point = list[float]


def painted(stroke: list[list[float]], tolerance: float) -> tuple[list[Point], list[Point]] | None:
    """The outline of the area a stroke of `[x, y, width]` points paints (each point a disc of its width, joined by
    bands), simplified to `tolerance` pixels, and its centreline, simplified the same way. None when nothing is painted.
    """
    points = [p for p in stroke if len(p) >= 3 and p[2] > 0]
    if not points:
        return None
    pad = max(p[2] for p in points)
    left, top = min(p[0] for p in points) - pad, min(p[1] for p in points) - pad
    width = int(np.ceil(max(p[0] for p in points) + pad - left)) + 2
    height = int(np.ceil(max(p[1] for p in points) + pad - top)) + 2
    mask = np.zeros((height, width), dtype=np.uint8)

    def at(p: Point) -> tuple[int, int]:
        return int(round(p[0] - left)), int(round(p[1] - top))

    for p in points:
        cv2.circle(mask, at(p), max(int(round(p[2] / 2)), 1), 255, -1)
    for a, b in zip(points, points[1:]):
        cv2.line(mask, at(a), at(b), 255, max(int(round((a[2] + b[2]) / 2)), 1))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    biggest = max(contours, key=cv2.contourArea)
    outline = cv2.approxPolyDP(biggest, tolerance, True).reshape(-1, 2)
    if len(outline) < 3:
        return None
    path = np.array([[p[0], p[1]] for p in points], dtype=np.float32).reshape(-1, 1, 2)
    centre = cv2.approxPolyDP(path, tolerance, False).reshape(-1, 2) if len(points) > 2 else path.reshape(-1, 2)
    if len(centre) < 2:
        centre = np.array([points[0][:2], points[-1][:2]], dtype=np.float32)
    return (
        [[float(x) + left, float(y) + top] for x, y in outline],
        [[float(x), float(y)] for x, y in centre],
    )
