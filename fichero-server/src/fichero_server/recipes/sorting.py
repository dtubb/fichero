"""Sorting the pages by kind before they are lined or read (#5578, `source.onboard.auto.reader-per-material`).

A page's kind (handwriting, print, typescript, blank) is the document attribute `material`; `material_set_by` says
who set it: `sorting` (this job) or `person` (a change through the document update route). A person's kind is never
overwritten, and a kind already set is not worked out again.

* **blank** is Find the Documents' blank-verso rule (`finddocs.job.blank_versos`, #5579): one code path for the
  pages a run leaves unread.
* the rest are told apart from the image only when the step reads different kinds with different readers: machine
  text (print, typescript) or handwriting.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

KIND = "material"
SET_BY = "material_set_by"
BY_SORTING, BY_PERSON = "sorting", "person"
BLANK = "blank"
#: Of the inked span of a page, the share of rows with (almost) no ink above which its text is machine-made.
MACHINE_GAP_SHARE = 0.25
_WIDTH = 400


def kinds(db: Any, page_ids: list[str], materials: list[str]) -> dict[str, str]:
    """{page id: kind} for `page_ids`, sorting the pages not sorted yet. `materials` are the kinds the step has
    readers for; with fewer than two, only blank pages are sorted (every other page has the one reader)."""
    from fichero_server.finddocs.job import blank_versos
    from fichero_server.models import Document

    docs = {pid: db.get(Document, pid) for pid in page_ids}
    out: dict[str, str] = {}
    for pid, doc in docs.items():
        attrs = doc.attributes if doc is not None and isinstance(doc.attributes, dict) else {}
        if attrs.get(KIND):
            out[pid] = str(attrs[KIND])
    unsorted = [pid for pid in page_ids if pid not in out and docs[pid] is not None]
    blanks = blank_versos(db, unsorted) if unsorted else set()
    machine = next((m for m in ("print", "typescript") if m in materials), "print")
    for pid in unsorted:
        if pid in blanks:
            kind = BLANK
        elif len(materials) > 1:
            looks = _machine_made(docs[pid].path)
            if looks is None:
                continue  # nothing to look at: read by the step's own reader, left unsorted
            kind = machine if looks else "handwriting"
        else:
            continue
        doc = docs[pid]
        doc.attributes = {**(doc.attributes if isinstance(doc.attributes, dict) else {}), KIND: kind,
                          SET_BY: BY_SORTING}
        db.save(doc)
        out[pid] = kind
    return out


def _machine_made(path: str | None) -> bool | None:
    """Whether the page's text looks machine-made (print, typescript), None when there is no image to look at.

    ponytail: a heuristic, not a classifier. Machine text sits on straight lines with clean gaps between them;
    handwriting's ascenders, descenders and drifting lines fill those gaps. It cannot tell print from typescript,
    and a skewed photograph of print reads as handwriting. Upgrade path: a small classifier trained on the pages
    people corrected (`material_set_by` = person).
    """
    if not path or not Path(path).is_file():
        return None
    from PIL import Image, ImageOps

    try:
        with Image.open(path) as image:
            image.draft("L", (_WIDTH * 2, _WIDTH * 2))
            gray = ImageOps.grayscale(image)
            gray.thumbnail((_WIDTH, _WIDTH * 2))
            width, height = gray.size
            pixels = gray.tobytes()
    except OSError:
        return None
    paper = sorted(pixels)[len(pixels) // 2]
    rows = [sum(1 for p in pixels[y * width:(y + 1) * width] if p < paper - 50) for y in range(height)]
    inked = [y for y, n in enumerate(rows) if n]
    if not inked:
        return None
    span = rows[inked[0]:inked[-1] + 1]
    floor = max(span) * 0.02
    return sum(1 for n in span if n <= floor) / len(span) >= MACHINE_GAP_SHARE
