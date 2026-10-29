"""Prepare Images, Set Up side: the answers suggested from five sample pages and the time line
(`prep.setup.three-questions-suggested-from-a-sample`, `prep.estimate.time-on-this-mac-before-start`, #5580).

An answer is suggested when three of the five sample pages agree (owner 2026-10-29): the first, quarter, middle, three
quarters and last page of the project. Not built: the mirrored-verso match and the sample's Find Lines figures (the
missed-lines question keeps its default for now).
"""
from __future__ import annotations

from typing import Any

#: Seconds a page takes through the operations, the seed figure shown as an estimate until a run's own is kept.
SEED_SECONDS_PER_PAGE = 0.32
COVERS_UNDER = 0.85
#: A rule is a long thin faint line; this many of them down the page make it ruled paper.
RULES_AT_LEAST = 6


def sample_ids(ids: list[str]) -> list[str]:
    """The first, quarter, middle, three-quarter and last pages (fewer when the project has fewer)."""
    n = len(ids)
    if n <= 5:
        return list(ids)
    return [ids[i] for i in (0, n // 4, n // 2, 3 * n // 4, n - 1)]


def is_ruled(image: Any) -> bool:
    import cv2
    import numpy as np

    gray = np.asarray(image.convert("L"))
    scale = min(1.0, 900 / max(gray.shape))
    if scale < 1:
        gray = cv2.resize(gray, (round(gray.shape[1] * scale), round(gray.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    paper = cv2.medianBlur(gray, 2 * max(7, round(0.03 * max(gray.shape))) + 1)
    faint = ((paper.astype(np.int16) - gray) > 15).astype(np.uint8)
    lines = cv2.morphologyEx(faint, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(5, gray.shape[1] // 3), 1)))
    count, _, _, _ = cv2.connectedComponentsWithStats(lines)
    return count - 1 >= RULES_AT_LEAST


def _agrees(hits: int, seen: int) -> bool:
    return seen > 0 and hits * 5 >= 3 * seen  # three of five


def suggest(db: Any) -> dict[str, dict[str, Any]]:
    """`{question key: {value, agree, why}}` for the questions the sample answers; a question it cannot answer is absent."""
    from PIL import Image

    from fichero_server.media.find_page import find_page
    from fichero_server.media.upright import upright
    from fichero_server.models import Document
    from fichero_server.recipes.prepare import is_faded
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    from pathlib import Path

    library = str(Path(db.path).parent)
    wide = covers = faded = ruled = seen = 0
    for doc_id in sample_ids(db.unit_of_work_ids()):
        doc = db.get(Document, doc_id)
        path = _resolve_abs_path(doc, library) if doc is not None else None
        try:
            with Image.open(path) as opened:
                image = upright(opened)
        except (OSError, AttributeError, TypeError):
            continue
        seen += 1
        found = find_page(image)
        if found is not None:
            wide += found.box[2] * image.width > found.box[3] * image.height
            covers += found.box[2] * found.box[3] < COVERS_UNDER
        faded += is_faded(path)
        ruled += is_ruled(image)
    out: dict[str, dict[str, Any]] = {}

    def put(key: str, value: Any, hits: int, why: str) -> None:
        out[key] = {"value": value, "agree": f"{hits} of {seen}", "why": why}

    if _agrees(wide, seen):
        put("two_pages_per_image", True, wide, "the outlines are wider than tall")
    if _agrees(covers, seen):
        put("beside_the_page", "dark-mount", covers, "the page covers under 85% of the picture")
    paper = [name for name, hits in (("ruled", ruled), ("faded", faded)) if _agrees(hits, seen)]
    if paper:
        put("the_paper", paper, max(ruled if "ruled" in paper else 0, faded if "faded" in paper else 0),
            "the sample shows " + " and ".join(paper) + " paper")
    return out


def estimate(pages: int) -> str:
    """The Start line's time: the seed figure, marked as an estimate."""
    minutes = max(1, round(pages * SEED_SECONDS_PER_PAGE / 60))
    return f"About {minutes} min for {pages} pages on this Mac (estimate). Nothing leaves this Mac."
