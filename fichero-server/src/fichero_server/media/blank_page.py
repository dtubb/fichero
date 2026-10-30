"""Blank pages: found, marked, hidden, unhidden (`prep.blank-pages-marked`, `prep.blank-pages-hidden-in-the-item-view`,
`prep.check.blank-mark-is-a-correction`, #5382, #1791).

A page is blank when its ink, after the ruling is taken out, is under `INK_MAX` of its pixels: graph paper and ruled
paper with nothing written on them. A blank page is kept (imported, its row and files untouched), marked by a row in its
edit chain (`mark_blank`, `who: run <id>` or `person`) and hidden in the item view by `exclude_from_processing`, which
every later step already honours (a work unit is never made from an excluded page). A person can mark any page blank or
not blank; unmarking clears the flag and writes the correction row, and the caller queues the page through the steps it
skipped. The original is never changed.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import numpy as np

#: Ink under this share of the page's pixels, after the ruling mask: blank.
INK_MAX = 0.002
#: "Sure" (`prep.blank-pages-marked`): ink under this share after the ruling mask, a tenth of INK_MAX. Between the two a
#: page is unsure: three short pen strokes on a ruled ledger page are about 0.0005, and a page hidden by mistake is
#: never read, so unsure becomes a proposal and the page stays.
INK_SURE = 0.0002
#: Ink is measured at this long side at most (memory), never the 900 px the paper's light is estimated at: shrinking a
#: scan to 900 px averaged thin pencil strokes below the contrast cut and hid pages with writing (review 2026-10-29).
WORK_SIDE = 4000
PAPER_SIDE = 900
#: A dark mark must be this much darker than the paper around it; a page is hidden as blank only when nothing is there
#: even at the fainter cut (pencil, a faded pen), where show-through and stains still stay under it.
CONTRAST = 40
CONTRAST_FAINT = 25
#: A mark is dust unless it is at least this long, as a share of the picture's long side, and a few pixels in area.
SPECK_EXTENT = 0.004
SPECK_AREA = 4
#: Ruling is a dark line at least this share of the picture's side long; it is taken out RULE_THICK-at-900-px thick.
RULE_LENGTH = 0.12
RULE_THICK = 5


def work_gray(image: Any, box: list[float] | None = None) -> Any:
    """The page (or the part of it `box` names, fractions of the picture) as grey, at most WORK_SIDE on the long side."""
    import cv2

    gray = np.asarray(image.convert("L"))
    if box is not None:
        rows, cols = gray.shape
        x, y, w, h = box
        gray = gray[round(y * rows):max(round((y + h) * rows), round(y * rows) + 1),
                    round(x * cols):max(round((x + w) * cols), round(x * cols) + 1)]
    scale = min(1.0, WORK_SIDE / max(gray.shape))
    if scale < 1:
        gray = cv2.resize(gray, (round(gray.shape[1] * scale), round(gray.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    return gray


def marks(gray: Any, lighter_than: int = CONTRAST, up_to: int | None = None) -> Any:
    """Where the marks are, as a boolean array the size of `gray`: pixels darker than the paper around them by more than
    `lighter_than` (and, with `up_to`, no more than that: the faint band show-through lives in), once ruled lines and
    specks are taken out."""
    import cv2

    h, w = gray.shape
    # The page's own light, ink included, estimated on a small copy and laid back at full size.
    small_scale = min(1.0, PAPER_SIDE / max(h, w))
    small = gray if small_scale >= 1 else cv2.resize(
        gray, (round(w * small_scale), round(h * small_scale)), interpolation=cv2.INTER_AREA)
    paper = cv2.medianBlur(small, 2 * max(7, round(0.03 * max(small.shape))) + 1)
    if paper.shape != gray.shape:
        paper = cv2.resize(paper, (w, h), interpolation=cv2.INTER_LINEAR)
    under = cv2.subtract(paper, gray)  # saturating: marks only where darker than the paper
    dark = ((under > lighter_than) if up_to is None else (under > lighter_than) & (under <= up_to)).astype(np.uint8)
    long_side = max(5, round(RULE_LENGTH * max(h, w)))
    ruling = cv2.bitwise_or(
        cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (long_side, 1))),
        cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, long_side))))
    thick = max(RULE_THICK, round(max(h, w) / PAPER_SIDE))  # a scan's ruling halo is thicker, in pixels
    ruling = cv2.dilate(ruling, np.ones((thick, thick), np.uint8))
    ink = cv2.bitwise_and(dark, cv2.bitwise_not(ruling) & 1)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink)
    reach = SPECK_EXTENT * max(h, w)
    keep = np.zeros(count, dtype=bool)
    for i in range(1, count):
        keep[i] = (stats[i, cv2.CC_STAT_AREA] >= SPECK_AREA
                   and max(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]) >= reach)
    return keep[labels]


def ink_share(image: Any, box: list[float] | None = None, contrast: int = CONTRAST) -> float:
    """The share of the page's pixels that are ink once ruled lines and specks are taken out (0.0 to 1.0). `box`
    (`[x, y, w, h]`, fractions of the picture) is the page found in it: the share is of the paper, not of the mount."""
    gray = work_gray(image, box)
    return float(marks(gray, contrast).sum()) / gray.size


def is_blank(image: Any, box: list[float] | None = None) -> bool:
    return ink_share(image, box) < INK_MAX


def blank_verdict(image: Any, has_lines: bool | Callable[[], bool] = False, box: list[float] | None = None) -> str:
    """`blank` only when sure (ink under INK_SURE and no text line found on the page); `unsure` when the ink is under
    INK_MAX but not that little, or a line was found; else `ink`. `has_lines` may be a function, asked only when the ink
    alone would call the page blank (a text read costs seconds); `box` is the page's box, the share being of the paper."""
    share = ink_share(image, box)
    if share >= INK_MAX:
        return "ink"
    if share >= INK_SURE or ink_share(image, box, CONTRAST_FAINT) >= INK_SURE:
        return "unsure"
    return "unsure" if (has_lines() if callable(has_lines) else has_lines) else "blank"


def is_hidden_blank(doc: Any) -> bool:
    """A page hidden as blank: excluded AND the engine's blank mark true (a page excluded for another reason is not)."""
    return bool(doc.exclude_from_processing) and bool(((doc.metadata or {}).get("blank") or {}).get("blank"))


def mark_blank(db: Any, doc_id: str, blank: bool, *, who: str, reason: str = "") -> None:
    """Mark a page blank (hidden, skipped) or not blank (shown again): one row in its edit chain with `who`, and the
    flag `exclude_from_processing` every later step honours. The page's row, files and original are kept."""
    from fichero_server.models import Document, ImageEditChain
    from fichero_server.core.timeutil import utc_now

    doc = db.get(Document, doc_id)
    if doc is None:
        raise KeyError(doc_id)
    doc.exclude_from_processing = blank
    meta = dict(doc.metadata or {})
    meta["blank"] = {"blank": blank, "by": who, "reason": reason}  # kept when unmarked: a re-run never overrides a person
    if who == "person":  # a person's word answers the run's proposal, hide or keep: it leaves the list
        proposals = {k: v for k, v in (meta.get("prep_proposals") or {}).items() if k != "blank"}
        meta["prep_proposals"] = proposals
    doc.metadata = meta
    doc.updated_at = utc_now()
    db.save(doc)
    row = {"op": "mark_blank", "params": {"blank": blank}, "who": who, "reason": reason, "created_at": utc_now().isoformat()}
    chains = list(db.query(ImageEditChain, document_id=doc_id))
    if chains:
        chains[0].operations = [*chains[0].operations, row]
        chains[0].updated_at = utc_now()
        db.save(chains[0])
    else:
        db.save(ImageEditChain(document_id=doc_id, operations=[row]))


def unhide(db: Any, doc_id: str) -> str:
    """A person's one click on a hidden page: not blank, shown again, the correction row written. Returns the page's id,
    for the caller to queue through the steps it skipped."""
    mark_blank(db, doc_id, False, who="person", reason="unhidden by a person")
    return doc_id


def queue_unhidden(db: Any, doc_id: str) -> dict[str, int]:
    """An unhidden page goes through the steps it skipped: the page operations, then the contrast step if it is faded
    (`prep.check.blank-mark-is-a-correction`). One page, so it is run here; the account says what each did."""
    from fichero_server.recipes.page_crop import crop_pages
    from fichero_server.recipes.prepare import prepare_pages

    return {**crop_pages(db, [doc_id], "unhide", prepare=True), **prepare_pages(db, [doc_id], "unhide")}
