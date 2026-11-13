"""One line cut by a knife stroke: where the stroke crosses the baseline, and the parts it leaves.

`segment-editor.split-knife`: a stroke, a polyline in the same fractions as the line's outline, cuts the
baseline wherever it crosses it; a stroke that crosses twice makes three parts, and one that crosses the
baseline nowhere leaves the line alone. The outline is cut along the stroke itself: drawn on a raster
(OpenCV, as `line_join` does), the stroke erased from it, and each piece of what is left given to the
part whose baseline it holds. Where the stroke stops short of the outline's edge, the rest of the cut
goes to the nearer baseline, so a short stroke still makes whole parts.

Pure geometry on the stored fractions, no image. Parts come back in reading order, first to last.
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from fichero_server.media.line_join import _GRID, _TRACE_TOLERANCE, _along, _cells

Point = list[float]

#: The width of the cut the stroke makes in the raster, in cells: wide enough to sever, narrow enough
#: that the parts still meet along it.
_KERF = 3


def _crossing(a: Point, b: Point, c: Point, d: Point) -> tuple[float, float] | None:
    """Where segment ab meets segment cd, as (t along ab, u along cd), each 0 to 1; None when they do not."""
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) < 1e-15:
        return None
    qx, qy = c[0] - a[0], c[1] - a[1]
    t = (qx * sy - qy * sx) / denominator
    u = (qx * ry - qy * rx) / denominator
    if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
        return t, u
    return None


def reading_baseline(baseline: list[Point], direction: str | None) -> list[Point]:
    """The baseline run the way the line reads (rtl from the right, ttb from the top)."""
    points = [[float(p[0]), float(p[1])] for p in baseline]
    ax, ay = _along(direction)
    if (points[-1][0] - points[0][0]) * ax + (points[-1][1] - points[0][1]) * ay < 0:
        points.reverse()
    return points


def _lengths(points: list[Point]) -> list[float]:
    return [math.dist(p, q) for p, q in zip(points, points[1:])]


def crossings(baseline: list[Point], stroke: list[Point]) -> list[float]:
    """Each place the stroke crosses the baseline, as a distance along it from its first point, 0 to 1,
    in order, with crossings closer than a thousandth of the line counted once."""
    lengths = _lengths(baseline)
    total = sum(lengths)
    if total <= 0 or len(stroke) < 2:
        return []
    found: list[float] = []
    walked = 0.0
    for (a, b), length in zip(zip(baseline, baseline[1:]), lengths):
        for c, d in zip(stroke, stroke[1:]):
            hit = _crossing(a, b, c, d)
            if hit is not None:
                found.append((walked + hit[0] * length) / total)
        walked += length
    found.sort()
    kept: list[float] = []
    for at in found:
        if 0.0 < at < 1.0 and (not kept or at - kept[-1] > 1e-3):
            kept.append(at)
    return kept


def baseline_pieces(baseline: list[Point], cuts: list[float]) -> list[list[Point]]:
    """The baseline cut at each fraction of its length, in order: len(cuts) + 1 pieces."""
    lengths = _lengths(baseline)
    total = sum(lengths)
    pieces: list[list[Point]] = []
    current: list[Point] = [baseline[0]]
    walked = 0.0
    pending = list(cuts)
    for (a, b), length in zip(zip(baseline, baseline[1:]), lengths):
        while pending and length > 0 and pending[0] * total <= walked + length:
            t = (pending.pop(0) * total - walked) / length
            point = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
            current.append(point)
            pieces.append(current)
            current = [point]
        current.append(b)
        walked += length
    pieces.append(current)
    return [[[round(x, 6), round(y, 6)] for x, y in piece] for piece in pieces]


def cut_outline(outline: list[Point], pieces: list[list[Point]], stroke: list[Point]) -> list[list[Point]] | None:
    """The outline cut along the stroke into one polygon per baseline piece, in the pieces' order; None
    when some piece is left with nothing of the outline (the stroke ran along a baseline, not across it)."""
    cells = _cells(outline)
    origin = cells.min(axis=0) - 2
    size = cells.max(axis=0) - origin + 3
    mask = np.zeros((int(size[1]), int(size[0])), dtype=np.uint8)
    cv2.fillPoly(mask, [cells - origin], 255)
    cut = mask.copy()
    cv2.polylines(cut, [_cells(stroke) - origin], False, 0, thickness=_KERF)
    count, labels = cv2.connectedComponents(cut, connectivity=4)

    # Each piece's distance field, and which pieces each piece of the cut outline holds.
    distances = []
    for piece in pieces:
        drawn = np.full(mask.shape, 255, dtype=np.uint8)
        cv2.polylines(drawn, [_cells(piece) - origin], False, 0, thickness=1)
        distances.append(cv2.distanceTransform(drawn, cv2.DIST_L2, 3))
    stack = np.stack(distances)
    owners: dict[int, list[int]] = {}
    for index, piece in enumerate(pieces):
        for x, y in _cells(piece) - origin:
            if 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1] and labels[y, x] > 0:
                owners.setdefault(int(labels[y, x]), []).append(index)

    assigned = np.full(mask.shape, -1, dtype=np.int32)
    nearest = np.argmin(stack, axis=0)
    for component in range(1, count):
        where = labels == component
        holders = sorted(set(owners.get(component, [])))
        if len(holders) == 1:
            assigned[where] = holders[0]
        elif holders:
            # The stroke stopped short: split what it left whole by the nearer of the pieces it holds.
            sub = np.argmin(stack[holders], axis=0)
            assigned[where] = np.array(holders)[sub][where]
        else:
            # A crumb the stroke cut off that holds no baseline goes to the nearest piece.
            assigned[where] = nearest[where]
    # The kerf itself goes back to the nearest piece, so the parts meet along the cut.
    kerf = (mask > 0) & (labels == 0)
    assigned[kerf] = nearest[kerf]

    polygons: list[list[Point]] = []
    for index in range(len(pieces)):
        part = np.where(assigned == index, 255, 0).astype(np.uint8)
        contours, _ = cv2.findContours(part, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        outer = max(contours, key=cv2.contourArea)
        traced = cv2.approxPolyDP(outer, _TRACE_TOLERANCE, True).reshape(-1, 2) + origin
        if len(traced) < 3:
            return None
        polygons.append([[round(float(x) / _GRID, 6), round(float(y) / _GRID, 6)] for x, y in traced])
    return polygons


def reading_offsets(cuts: list[float], length: int, char_positions: list[float] | None) -> tuple[list[int], bool]:
    """Where to cut a reading of `length` characters for each crossing (fractions along the line as it
    reads): before the character whose position is nearest, when positions are known; else in proportion.
    Returns the offsets, strictly rising and inside the reading, and whether they are estimates."""
    if length < len(cuts) + 1:
        return [], True
    known = char_positions is not None and len(char_positions) == length and length > 1
    offsets: list[int] = []
    for at in cuts:
        if known:
            offset = min(range(1, length), key=lambda i: abs(char_positions[i] - at))
        else:
            offset = round(at * length)
        low = offsets[-1] + 1 if offsets else 1
        offsets.append(min(max(offset, low), length - 1))
    if offsets and (offsets[-1] >= length or any(b <= a for a, b in zip(offsets, offsets[1:]))):
        return [], not known
    return offsets, not known


def part_holding(point: Point, polygons: list[list[Point]]) -> int:
    """The index of the part whose outline holds `point`, or the nearest one when none does
    (`segment-editor.edge.knife-through-words`: a word goes with the part its centre falls in)."""
    probe = (float(point[0]) * _GRID, float(point[1]) * _GRID)
    distances = [
        cv2.pointPolygonTest(np.array(_cells(polygon), dtype=np.float32), probe, True) for polygon in polygons
    ]
    return int(np.argmax(distances))
