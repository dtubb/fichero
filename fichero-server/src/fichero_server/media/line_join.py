"""Two or more lines joined into one: the outline, the baseline and the order they join in.

`segment-editor.merge-lines`: the outlines are joined into one polygon, their union, bridged across the
gap when two neighbours do not touch; the baselines are joined end to end in the page's reading order.
Pure geometry on the stored fractions, no image: the union is taken on a raster (OpenCV, a core
dependency; shapely ships only with the Kraken bundle) and traced back to a polygon.

ponytail: the bridge across a gap is the convex hull of the two facing halves, so the far half of each
line keeps its own shape; a gap wider than a line is bridged the same way rather than refused.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from fichero_server.media.layout_order import reading_order

#: The raster the union is drawn on, per unit of the page's fractions on each axis. A union is the same
#: under any scaling of the axes, so the page's own aspect is not needed.
_GRID = 4096
#: Douglas-Peucker tolerance on the traced outline, in raster cells: drops the staircase, keeps the ink.
_TRACE_TOLERANCE = 1.0
#: Scripts written without spaces between words, so a joined reading takes no separator (ISO 15924).
_UNSPACED_SCRIPTS = frozenset({"Hani", "Hans", "Hant", "Hira", "Kana", "Jpan", "Thai", "Khmr", "Laoo", "Mymr", "Tibt"})

Point = list[float]


def outline_of(anchor: Any) -> list[Point] | None:
    """A segment's outline: its polygon, else its rect's four corners; None when it has neither."""
    if anchor is None:
        return None
    if anchor.polygon and len(anchor.polygon) >= 3:
        return [[float(p[0]), float(p[1])] for p in anchor.polygon]
    if anchor.rect:
        x, y, w, h = (float(v) for v in anchor.rect)
        return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return None


def bounds(points: list[Point]) -> tuple[float, float, float, float]:
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def join_order(outlines: list[list[Point]], direction: str | None) -> list[int]:
    """The members' indexes in the page's reading order (`layout_order.reading_order` on their boxes)."""
    return reading_order([bounds(o) for o in outlines], direction=direction)


def _along(direction: str | None) -> tuple[float, float]:
    """The unit vector a line is read along."""
    if direction == "rtl":
        return (-1.0, 0.0)
    if direction in ("ttb", "btt"):
        return (0.0, 1.0 if direction == "ttb" else -1.0)
    return (1.0, 0.0)


def _cells(points: list[Point]) -> np.ndarray:
    return np.array([[round(p[0] * _GRID), round(p[1] * _GRID)] for p in points], dtype=np.int32)


def joined_outline(ordered: list[list[Point]], direction: str | None) -> list[Point]:
    """One simple polygon covering every outline, in the order given: the union where neighbours touch,
    the hull of their facing halves where they do not."""
    all_cells = np.concatenate([_cells(o) for o in ordered])
    origin = all_cells.min(axis=0) - 2
    size = all_cells.max(axis=0) - origin + 3
    mask = np.zeros((int(size[1]), int(size[0])), dtype=np.uint8)
    singles = []
    for outline in ordered:
        one = np.zeros_like(mask)
        cv2.fillPoly(one, [_cells(outline) - origin], 255)
        singles.append(one)
        mask |= one
    ax, ay = _along(direction)
    kernel = np.ones((3, 3), dtype=np.uint8)
    for (left, left_mask), (right, right_mask) in zip(zip(ordered, singles), zip(ordered[1:], singles[1:])):
        if np.any(cv2.dilate(left_mask, kernel) & right_mask):
            continue
        # The end of the first line and the start of the next, bridged by their hull.
        def projection(p: Point) -> float:
            return p[0] * ax + p[1] * ay
        left_mid = sum(projection(p) for p in left) / len(left)
        right_mid = sum(projection(p) for p in right) / len(right)
        facing = [p for p in left if projection(p) >= left_mid] + [p for p in right if projection(p) <= right_mid]
        hull = cv2.convexHull(_cells(facing) - origin)
        cv2.fillPoly(mask, [hull], 255)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    outer = max(contours, key=cv2.contourArea)
    traced = cv2.approxPolyDP(outer, _TRACE_TOLERANCE, True).reshape(-1, 2) + origin
    return [[round(float(x) / _GRID, 6), round(float(y) / _GRID, 6)] for x, y in traced]


def joined_baseline(ordered: list[list[Point] | None], direction: str | None) -> list[Point] | None:
    """The baselines end to end in the order given, each run the way the line reads; lines with none are
    skipped, and None when no line had one."""
    ax, ay = _along(direction)
    joined: list[Point] = []
    for baseline in ordered:
        if not baseline or len(baseline) < 2:
            continue
        points = [[float(p[0]), float(p[1])] for p in baseline]
        if (points[-1][0] - points[0][0]) * ax + (points[-1][1] - points[0][1]) * ay < 0:
            points.reverse()
        joined.extend(points)
    return joined if len(joined) >= 2 else None


def reading_separator(script: str | None) -> str:
    """What joins two lines' readings: a space, or nothing for a script written without spaces."""
    return "" if script in _UNSPACED_SCRIPTS else " "


def _edges_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    """Whether segment ab properly crosses segment cd (touching at an end is not a crossing)."""
    def side(p: Point, q: Point, r: Point) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    d1, d2, d3, d4 = side(c, d, a), side(c, d, b), side(a, b, c), side(a, b, d)
    return d1 * d2 < 0 and d3 * d4 < 0


def crosses_itself(polygon: list[Point]) -> bool:
    """Whether a closed outline crosses itself: two edges that are not neighbours meet."""
    count = len(polygon)
    if count < 4:
        return False
    edges = [(polygon[i], polygon[(i + 1) % count]) for i in range(count)]
    for i in range(count):
        for j in range(i + 2, count):
            if i == 0 and j == count - 1:
                continue
            if _edges_cross(*edges[i], *edges[j]):
                return True
    return False


def simple_outline(polygon: list[Point]) -> tuple[list[Point], bool]:
    """`segment-editor.edge.self-intersecting`: the outline as given when it is simple, else the outer boundary of
    the area it covers (its union, drawn on the raster and traced back), and whether it had to be simplified."""
    points = [[float(p[0]), float(p[1])] for p in polygon]
    if not crosses_itself(points):
        return points, False
    cells = _cells(points)
    origin = cells.min(axis=0) - 2
    size = cells.max(axis=0) - origin + 3
    mask = np.zeros((int(size[1]), int(size[0])), dtype=np.uint8)
    # Every loop of a figure-eight is inside the shape, whichever way it winds.
    cv2.fillPoly(mask, [cells - origin], 255)
    cv2.polylines(mask, [cells - origin], True, 255, thickness=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    hull = cv2.convexHull(np.concatenate(contours)) if len(contours) > 1 else max(contours, key=cv2.contourArea)
    traced = cv2.approxPolyDP(hull, _TRACE_TOLERANCE, True).reshape(-1, 2) + origin
    return [[round(float(x) / _GRID, 6), round(float(y) / _GRID, 6)] for x, y in traced], True
