"""Leave Out: lines that are not writing are marked LEFT OUT before Read (`designer.clean.leaves-out-non-text`, #6070).

A stage after Find Lines and before Read. It never deletes: a left-out line keeps its row, `is_furniture` is set (the one
left-out flag Read and the Reader already skip) and `metadata["left_out"]` says why, so a person can bring it back from the
Inspector (`segment.update`, `is_furniture` false). A line is left out when it is

* too small to be useful: far thinner than the page's median line, or a speck (`too small`),
* off the page: its centre is outside the page's box, e.g. the black scanner bed (`off the page`),
* damaged or bleed-through: Kraken's shape confidence is very low AND the ink contrast under it is low
  (`likely bleed-through`).

ponytail: first slice. "Too small" and "off the page" are on by default; bleed-through needs a contrast reading (the image
under the line) and is skipped where there is none. The page box comes from the document's own `page_box` metadata
([x, y, w, h], fractions) where Clean Up found one; with none, nothing is "off the page". Upgrade path: a cloud vision check
per region where cloud is allowed, and the page MASK (not its box) from find-the-page.
"""
from __future__ import annotations

import statistics
from collections.abc import Callable
from typing import Any

TOO_SMALL = "too small"
OFF_THE_PAGE = "off the page"
BLEED = "likely bleed-through"
#: A line whose thinner side is under this share of the page's median line is too small to be a line of writing.
THIN_BELOW = 0.25
#: Fewer lines than this on a page and the median says nothing: only a speck is too small.
MEDIAN_NEEDS = 5
#: A speck: under this share of the page's area, whatever the other lines are (0.005% = a 0.7% by 0.7% box).
SPECK_AREA = 5e-5
#: Shape confidence and ink contrast (0-1) both under these: damage or bleed-through, not writing.
LOW_CONFIDENCE = 0.15
LOW_CONTRAST = 0.12


def _thickness(line: dict[str, float]) -> float:
    return min(line["w"], line["h"])


def decide(lines: list[dict[str, Any]], *, page_box: list[float] | None = None,
           contrast_of: Callable[[dict[str, Any]], float | None] | None = None,
           too_small: bool = True, off_page: bool = True, bleed: bool = True) -> dict[str, str]:
    """Which lines to leave out, and why: `{id: reason}`. Each line is `{id, x, y, w, h, confidence}` (fractions of the
    page). A line gets the first reason that applies; the rest are kept."""
    out: dict[str, str] = {}
    median = statistics.median(_thickness(ln) for ln in lines) if len(lines) >= MEDIAN_NEEDS else None
    for ln in lines:
        reason = None
        if off_page and page_box is not None:
            cx, cy = ln["x"] + ln["w"] / 2, ln["y"] + ln["h"] / 2
            bx, by, bw, bh = page_box
            if not (bx <= cx <= bx + bw and by <= cy <= by + bh):
                reason = OFF_THE_PAGE
        if reason is None and too_small:
            if ln["w"] * ln["h"] < SPECK_AREA or (median and _thickness(ln) < THIN_BELOW * median):
                reason = TOO_SMALL
        if reason is None and bleed and contrast_of is not None and ln.get("confidence") is not None:
            contrast = contrast_of(ln)
            if ln["confidence"] < LOW_CONFIDENCE and contrast is not None and contrast < LOW_CONTRAST:
                reason = BLEED
        if reason:
            out[ln["id"]] = reason
    return out


def _ink_contrast(image: Any, line: dict[str, Any]) -> float | None:
    """The spread between the box's darkest and lightest 5% of grey (0-1), or None for an empty box."""
    width, height = image.size
    box = (int(line["x"] * width), int(line["y"] * height), int((line["x"] + line["w"]) * width),
           int((line["y"] + line["h"]) * height))
    if box[2] <= box[0] or box[3] <= box[1]:
        return None
    grey = sorted(image.crop(box).convert("L").getdata())
    cut = max(1, len(grey) // 20)
    return (sum(grey[-cut:]) / cut - sum(grey[:cut]) / cut) / 255


def leave_out_pages(db: Any, documents: list[str], run_id: str,
                    stop: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Mark each page's lines that are not writing; the account: `pages`, `left_out`, and `why` (count by reason).
    Nothing is deleted, a line already left out is not touched, and running it again marks nothing new."""
    from pathlib import Path

    from fichero_server.models import Document, Segment
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    library = Path(db.path).parent
    account: dict[str, Any] = {"pages": 0, "left_out": 0, "why": {}}
    for doc_id in documents:
        if stop is not None and stop():
            break
        rows = [r for r in db.query(Segment, document_id=doc_id) if r.kind == "line" and r.deleted_at is None]
        if not rows:
            continue
        account["pages"] += 1
        doc = db.get(Document, doc_id)
        page_box = ((doc.metadata or {}).get("page_box") if doc is not None else None)
        lines = [{"id": r.id, "x": r.bbox_x, "y": r.bbox_y, "w": r.bbox_w, "h": r.bbox_h, "confidence": r.confidence}
                 for r in rows if not r.is_furniture]
        image = _open(_resolve_abs_path(doc, str(library))) if doc is not None else None
        contrast = (lambda ln: _ink_contrast(image, ln)) if image is not None else None
        verdicts = decide(lines, page_box=page_box, contrast_of=contrast)
        for row in rows:
            why = verdicts.get(row.id)
            if why is None:
                continue
            row.is_furniture = True
            row.metadata = {**(row.metadata or {}), "left_out": {"why": why, "by": "leave-out", "run": run_id}}
            row.version += 1
            db.save(row)
            account["left_out"] += 1
            account["why"][why] = account["why"].get(why, 0) + 1
    return account


def _open(path: str | None) -> Any | None:
    from pathlib import Path

    if not path or not Path(path).is_file():
        return None
    from PIL import Image

    try:
        image = Image.open(path)
        image.draft("L", (1600, 1600))
        return image.convert("L")
    except OSError:
        return None


def run_step(db: Any, documents: list[str], parent: str, step: dict[str, Any],
             stop: Callable[[], bool] | None = None) -> tuple[str | None, str, str | None]:
    """The recipe run's card: (its job, its end, why). The account (`left_out`) rides on the step."""
    step["left_out"] = leave_out_pages(db, documents, parent, stop=stop)
    if stop is not None and stop():
        return None, "cancelled", "Stopped by you"
    return None, "done", None
