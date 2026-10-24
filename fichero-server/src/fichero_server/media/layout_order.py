"""Reading order from position: regions and lines in the order a person reads them.

Kraken lists regions by TYPE then in its own order, and a detector lists them by score, so the first
region of a page need not be its top (TEst 12 IMG_009 read the page's second block first). This orders
boxes from where they are: an XY-cut, the cut taken on the axis with the widest gap (a column gutter
beats a paragraph gap), columns taken in the page's direction, marginalia put after the body block they
sit beside. Pure geometry, no model.

ponytail: a recursive XY-cut, no learned layout. It orders a page whose blocks have gaps between them;
a page with blocks that interlock (an L-shaped region) falls back to top-then-side, which is the order
the old box key gave. Upgrade to a learned order only if the corpus measure shows a class it misses.
"""

from __future__ import annotations

from typing import Any

#: The kinds that sit BESIDE the body and are read after the block they sit beside.
#: Kraken's `marginalia`, and SegmOnto's margin and numbering zones (what imported PAGE files call them).
MARGINALIA = frozenset({"marginalia", "margin", "marginal", "margintextzone", "marginzone", "numberingzone"})
#: Each box's core, the middle of its extent, is what must not overlap for a cut: lines whose outlines
#: touch still have a gap between their cores.
_CORE = 0.15
#: A column gutter must be this many times the widest gap down the page before columns are read first: a
#: paragraph gap is small beside a gutter, but blocks that merely overlap sideways are not columns.
_COLUMN_BIAS = 2.0
#: The most a box's core shrinks, as a share of the group's extent on the axis.
_MAX_PAD = 0.02

Box = tuple[float, float, float, float]  # x0, y0, x1, y1


def columns_run_right_to_left(direction: str | None) -> bool:
    """Whether the page's columns are read right to left: right-to-left scripts, and vertical text whose
    columns advance leftward (Chinese, Japanese: `ttb`). `ttb-lr` (Mongolian) and the rest run left to right."""
    return direction in ("rtl", "ttb")


def _groups(boxes: list[Box], members: list[int], axis: int) -> tuple[list[list[int]], float]:
    """`members` cut into runs along `axis` (0 = x, 1 = y) wherever no box's core spans, in increasing
    position, with the widest gap found as a share of the group's extent on that axis."""
    cores = []
    span = max(boxes[i][axis + 2] for i in members) - min(boxes[i][axis] for i in members)
    for i in members:
        lo, hi = boxes[i][axis], boxes[i][axis + 2]
        # Capped at a share of the whole extent, so a TALL block's gap is not exaggerated by its own size.
        pad = min((hi - lo) * _CORE, span * _MAX_PAD)
        cores.append((lo + pad, hi - pad, i))
    cores.sort()
    extent = max(hi for _, hi, _ in cores) - min(lo for lo, _, _ in cores)
    groups, current, reach, widest = [], [cores[0][2]], cores[0][1], 0.0
    for lo, hi, i in cores[1:]:
        if lo >= reach:
            widest = max(widest, lo - reach)
            groups.append(current)
            current, reach = [i], hi
        else:
            current.append(i)
            reach = max(reach, hi)
    groups.append(current)
    return groups, (widest / extent if extent > 0 else 0.0)


def _cut(boxes: list[Box], members: list[int], rtl: bool) -> list[int]:
    if len(members) <= 1:
        return list(members)
    across, across_gap = _groups(boxes, members, 0)
    down, down_gap = _groups(boxes, members, 1)
    if len(across) > 1 and (len(down) == 1 or across_gap > _COLUMN_BIAS * down_gap):
        runs = list(reversed(across)) if rtl else across
    elif len(down) > 1:
        runs = down
    else:
        # Nothing separates them: top, then along the line in the page's direction.
        def centre(i: int) -> tuple[float, float]:
            return ((boxes[i][1] + boxes[i][3]) / 2, -(boxes[i][0] + boxes[i][2]) / 2 if rtl else (boxes[i][0] + boxes[i][2]) / 2)
        return sorted(members, key=centre)
    return [i for run in runs for i in _cut(boxes, run, rtl)]


def reading_order(boxes: list[Box], *, direction: str | None = None, kinds: list[str | None] | None = None) -> list[int]:
    """The indexes of `boxes` in reading order. `kinds[i]` names a box's kind: marginalia are left out of
    the cut and placed after the body box they overlap most vertically (last when none overlaps)."""
    rtl = columns_run_right_to_left(direction)
    kinds = kinds or [None] * len(boxes)
    body = [i for i in range(len(boxes)) if str(kinds[i] or "").lower() not in MARGINALIA]
    margins = [i for i in range(len(boxes)) if i not in set(body)]
    ordered = _cut(boxes, body, rtl) if body else []
    host: dict[int, list[int]] = {}
    for m in sorted(margins, key=lambda i: boxes[i][1]):
        def overlap(b: int) -> float:
            return min(boxes[m][3], boxes[b][3]) - max(boxes[m][1], boxes[b][1])
        best = max(ordered, key=overlap, default=None) if ordered else None
        host.setdefault(best if best is not None and overlap(best) > 0 else (ordered[-1] if ordered else m), []).append(m)
    if not ordered:
        return sorted(margins, key=lambda i: boxes[i][1])
    return [j for i in ordered for j in [i, *host.get(i, [])]]


def _bbox(polygon: list[list[float]]) -> Box:
    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def order_payload(payload: dict[str, Any], direction: str | None = None) -> dict[str, Any]:
    """A segmentation's `regions` and `lines` (Kraken's payload) in reading order: regions by position, each
    region's lines top-down (or by column), a line in no region placed among the regions where it sits.
    Lines and regions with no usable polygon keep their relative place at the end. The geometry's
    `line_index` counts the NEW order, so the transcript lines and the boxes still pair up."""
    regions, lines = list(payload.get("regions") or []), list(payload.get("lines") or [])
    units: list[tuple[Box, str | None, list[int], int | None, int | None]] = []  # box, kind, its line indexes, region idx, line idx
    in_region: dict[str, list[int]] = {}
    for li, line in enumerate(lines):
        if line.get("region") is not None:
            in_region.setdefault(str(line["region"]), []).append(li)
    unplaced: list[int] = []
    for ri, region in enumerate(regions):
        polygon = region.get("polygon") or []
        if len(polygon) < 3:
            unplaced.append(ri)
            continue
        units.append((_bbox(polygon), str(region.get("type") or ""), in_region.get(str(region.get("id")), []), ri, None))
    region_ids = {str(r.get("id")) for r in regions}
    for li, line in enumerate(lines):
        if (line.get("region") is None or str(line["region"]) not in region_ids) and len(line.get("polygon") or []) >= 3:
            units.append((_bbox(line["polygon"]), None, [li], None, li))
    if not units:
        return payload
    order = reading_order([u[0] for u in units], direction=direction, kinds=[u[1] for u in units])
    new_regions = [regions[units[i][3]] for i in order if units[i][3] is not None] + [regions[i] for i in unplaced]
    new_lines: list[dict[str, Any]] = []
    seen: set[int] = set()
    for i in order:
        _box, _kind, member_lines, _ri, _li = units[i]
        usable = [li for li in member_lines if len(lines[li].get("polygon") or []) >= 3]
        boxes = [_bbox(lines[li]["polygon"]) for li in usable]
        for k in (reading_order(boxes, direction=direction) if boxes else []):
            seen.add(usable[k])
            new_lines.append(lines[usable[k]])
    new_lines += [line for li, line in enumerate(lines) if li not in seen]
    return {**payload, "regions": new_regions, "lines": new_lines}
