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

from typing import Any

import numpy as np

#: Ink under this share of the page's pixels, after the ruling mask: blank.
INK_MAX = 0.002
WORK_SIDE = 900
#: A dark mark must be this much darker than the paper around it; a mark smaller than this many pixels is dust.
CONTRAST = 40
SPECK = 12
#: Ruling is a dark line at least this share of the picture's side long and not more than RULE_THICK pixels thick.
RULE_LENGTH = 0.12
RULE_THICK = 5


def ink_share(image: Any) -> float:
    """The share of the page's pixels that are ink once ruled lines and specks are taken out (0.0 to 1.0)."""
    import cv2

    gray = np.asarray(image.convert("L"))
    scale = min(1.0, WORK_SIDE / max(gray.shape))
    if scale < 1:
        gray = cv2.resize(gray, (round(gray.shape[1] * scale), round(gray.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    h, w = gray.shape
    paper = cv2.medianBlur(gray, 2 * max(7, round(0.03 * max(h, w))) + 1)  # the page's own light, ink included
    dark = ((paper.astype(np.int16) - gray) > CONTRAST).astype(np.uint8)
    long_side = max(5, round(RULE_LENGTH * max(h, w)))
    ruling = cv2.bitwise_or(
        cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (long_side, 1))),
        cv2.morphologyEx(dark, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, long_side))))
    ruling = cv2.dilate(ruling, np.ones((RULE_THICK, RULE_THICK), np.uint8))
    ink = cv2.bitwise_and(dark, cv2.bitwise_not(ruling) & 1)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(ink)
    kept = sum(int(stats[i, cv2.CC_STAT_AREA]) for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= SPECK)
    return kept / (h * w)


def is_blank(image: Any) -> bool:
    return ink_share(image) < INK_MAX


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
