"""What is wrong with a page's segments before it is exported.

`segment-editor.validate-before-export`: per pass, the lines outside every region, outlines that cross themselves,
outlines that overlap another of the same level by more than a tenth, segments with no shape, lines with no baseline,
a reading order with a repeat, an entry naming nothing, or a segment missing from it, words whose stretches do not
tile their line's reading, and regions with no lines (`segment-editor.edge.empty-region`). Pure: it reads the rows it
is given and writes nothing; the route gathers them.
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import Any

import cv2
import numpy as np

from fichero_server.media import line_join

#: How much of the smaller of two outlines of one level may lie inside the other before it is reported.
OVERLAP_SHARE = 0.1
#: The raster two outlines are compared on, per unit of the page's fractions.
_GRID = 1024
#: The kinds a reading order holds; words and characters are read through their line.
ORDERED_KINDS = frozenset({"region", "line"})
#: The kinds that are a line's level.
LINE_KINDS = frozenset({"line"})


def _problem(kind: str, segment_ids: list[str], detail: str, **extra: Any) -> dict:
    return {"kind": kind, "segment_ids": segment_ids, "detail": detail, **extra}


def _area_cells(outline: list[list[float]], origin: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    cells = np.array([[round(x * _GRID), round(y * _GRID)] for x, y in outline], dtype=np.int32) - origin
    cv2.fillPoly(mask, [cells], 1)
    return mask.astype(bool)


def overlap_share(first: list[list[float]], second: list[list[float]]) -> float:
    """How much of the smaller outline lies inside the other, 0 to 1."""
    a, b = line_join.bounds(first), line_join.bounds(second)
    if a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1]:
        return 0.0
    origin = np.array([min(a[0], b[0]) * _GRID, min(a[1], b[1]) * _GRID], dtype=np.int32) - 1
    shape = (int(max(a[3], b[3]) * _GRID - origin[1]) + 2, int(max(a[2], b[2]) * _GRID - origin[0]) + 2)
    one, two = _area_cells(first, origin, shape), _area_cells(second, origin, shape)
    smaller = min(int(one.sum()), int(two.sum()))
    return float((one & two).sum()) / smaller if smaller else 0.0


def words_tile(text: str, spans: list[list[int]]) -> bool:
    """Whether the words' stretches tile the line's reading: inside it, not overlapping, and every character that is
    not a space in one of them."""
    covered = [False] * len(text)
    for start, end in sorted(spans):
        if not 0 <= start < end <= len(text) or any(covered[start:end]):
            return False
        covered[start:end] = [True] * (end - start)
    return all(flag or char.isspace() for flag, char in zip(covered, text))


def check_pass(
    rows: list[Any], orders: list[tuple[Any, list[Any]]], line_texts: dict[str, str],
) -> list[dict]:
    """Every problem on one pass's live `rows`, given its reading orders (each with its entries) and the counting
    reading of each line that has one."""
    problems: list[dict] = []
    live = {row.id: row for row in rows if row.deleted_at is None}
    outlines = {row.id: line_join.outline_of(row.anchor) for row in live.values()}
    regions = [row for row in live.values() if row.kind == "region"]

    for row in live.values():
        outline = outlines[row.id]
        if outline is None:
            problems.append(_problem("no-shape", [row.id], "has no outline or box"))
        elif row.anchor is not None and row.anchor.polygon and line_join.crosses_itself(row.anchor.polygon):
            problems.append(_problem("self-crossing", [row.id], "its outline crosses itself"))
        if row.kind in LINE_KINDS:
            if not row.baseline or len(row.baseline) < 2:
                problems.append(_problem("no-baseline", [row.id], "a line with no baseline"))
            # A parent that is no longer live (its region deleted) holds nothing: the line is in no region
            # (review 2026-11-14). A live parent of another kind (a table cell) still holds it.
            orphaned = bool(row.parent_segment_id) and row.parent_segment_id not in live
            if orphaned or (regions and not row.parent_segment_id):
                problems.append(_problem("line-outside-regions", [row.id], "a line in no region"))
    for region in regions:
        if not any(child.parent_segment_id == region.id for child in live.values()):
            problems.append(_problem("empty-region", [region.id], "a region with no lines"))

    by_kind: dict[str, list[Any]] = {}
    for row in live.values():
        if outlines[row.id] is not None:
            by_kind.setdefault(row.kind, []).append(row)
    for kind, same in by_kind.items():
        for first, second in combinations(same, 2):
            share = overlap_share(outlines[first.id], outlines[second.id])
            if share > OVERLAP_SHARE:
                problems.append(_problem(
                    "overlap", [first.id, second.id], f"two {kind}s overlap by {round(share * 100)}%",
                    share=round(share, 3),
                ))

    ordered = {row.id for row in live.values() if row.kind in ORDERED_KINDS}
    for order, entries in orders:
        named = [entry.segment_id for entry in entries]
        repeats = sorted(segment_id for segment_id, count in Counter(named).items() if count > 1)
        if repeats:
            problems.append(_problem("order-repeat", repeats, f"in the order {order.name!r} more than once",
                                     order_id=order.id))
        dangling = sorted({segment_id for segment_id in named if segment_id not in live})
        if dangling:
            problems.append(_problem("order-gap", dangling, f"the order {order.name!r} names segments that are gone",
                                     order_id=order.id))
        missing = sorted(ordered - set(named))
        if missing:
            problems.append(_problem("order-missing", missing, f"missing from the order {order.name!r}",
                                     order_id=order.id))

    for line_id, text in line_texts.items():
        words = [row for row in live.values()
                 if row.parent_segment_id == line_id and row.kind == "word" and (row.metadata or {}).get("reading_span")]
        if words and not words_tile(text, [list(word.metadata["reading_span"]) for word in words]):
            problems.append(_problem("words-do-not-tile", [line_id, *(w.id for w in words)],
                                     "the words' stretches do not cover the line's reading once each"))
    return problems
