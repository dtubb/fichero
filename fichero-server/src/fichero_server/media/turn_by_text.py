"""Turn a page upright by its text (`prep.turn-by-the-text`, #5382).

One Apple Vision text read on a reduced copy. Vision reads sideways and upside-down text as well as upright (measured
2026-10-29: the same 72 words at 0, 90, 180 and 270 degrees), so the spec's "most words at four turns" cannot decide;
what does is WHERE the lines it returns sit in reading order. Vision returns lines in the text's own reading order
(first line first): on an upright page the lines go down the picture, upside down they go up, laid on a side they go
left-to-right or right-to-left, and the lines' own aspect says whether the text runs along or across the picture.
The turn that undoes it is a lossless quarter turn (`rotate`, `angle` counter-clockwise as PIL turns), recorded with its
reason. EXIF is applied first (`prep.image.one-upright-frame`); fewer than `MIN_LINES` lines, or lines that do not agree,
mean no turn.
"""
from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

#: The reduced copy's long side.
REDUCED_SIDE = 1400
#: Fewer lines than this and the order of the lines says nothing.
MIN_LINES = 3
#: At least this share of consecutive line pairs must step the same way along the page.
AGREE = 0.7

Line = tuple[float, float, float, float]  # x, y, w, h as fractions of the picture, in Vision's reading order


def read_lines(image: Any) -> list[Line]:
    """The text lines Apple Vision finds in a PIL image, in reading order (empty where Vision is unavailable)."""
    from fichero_server.workflows.tools.vision_base import apple_vision_ocr_with_geometry

    small = image.convert("RGB")
    small.thumbnail((REDUCED_SIDE, REDUCED_SIDE))
    with tempfile.TemporaryDirectory() as scratch:
        shot = Path(scratch) / "turn.png"
        small.save(shot)
        try:
            geometry = apple_vision_ocr_with_geometry(str(shot), "en")
        except Exception:  # noqa: BLE001  Vision absent, or the picture unreadable: no lines read
            return []
    return [tuple(b.bbox[:4]) for b in geometry.line_boxes]


def turn_by_text(image: Any, *, reader: Callable[[Any], list[Line]] | None = None) -> dict[str, Any]:
    """`{"angle": 0|90|180|270, "lines": n, "reason": ...}`; the angle is the turn to apply, 0 writes nothing."""
    lines = (reader or read_lines)(image)
    if len(lines) < MIN_LINES:
        return {"angle": 0, "lines": len(lines), "reason": f"{len(lines)} lines read: too few to tell"}
    width, height = image.size
    along = sorted(w * width / max(h * height, 1e-9) for _x, _y, w, h in lines)[len(lines) // 2] >= 1.0
    axis = 1 if along else 0  # lines stack down the picture (y) or across it (x)
    steps = [b[axis] - a[axis] for a, b in zip(lines, lines[1:])]
    forward = sum(1 for s in steps if s > 0) / len(steps)
    backward = sum(1 for s in steps if s < 0) / len(steps)
    if forward >= AGREE:
        angle = 0 if along else 270  # laid by 90 counter-clockwise: undo with 270
    elif backward >= AGREE:
        angle = 180 if along else 90
    else:
        return {"angle": 0, "lines": len(lines), "reason": "the lines do not agree which way the page runs"}
    reason = "upright: its lines run down the page" if angle == 0 else \
        f"turned {angle}° from its text: {len(lines)} lines read {'upward' if backward >= AGREE and along else 'sideways'}"
    return {"angle": angle, "lines": len(lines), "reason": reason}
