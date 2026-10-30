"""Prepare Images, Set Up side: the answers suggested from five sample pages and the time line
(`prep.setup.three-questions-suggested-from-a-sample`, `prep.estimate.time-on-this-mac-before-start`, #5580).

An answer is suggested when three of the five sample pages agree (owner 2026-10-29): the first, quarter, middle, three
quarters and last page of the project. The missed-lines answer reads the lines the sample pages already have (ink outside
the line boxes on three of five; the characters-per-width half needs readings and is not built); show-through is a mirrored
faint copy of the previous page. Neither is measured on real scans yet.
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


#: Ink beyond the line boxes: of all the ink on a page, this share outside every line (and a rim of this much of the page's
#: height around each) says the segmenter missed lines or words (`check_missed_lines`).
MISSED_SHARE = 0.03
LINE_RIM = 0.008
#: Show-through (`the_paper`): marks fainter than ink but this far under the paper's own light, within this reach of the
#: previous page's ink seen from the back; "mirrored" is the horizontal flip.
FAINT_FROM, FAINT_TO = 6, 35
MIRROR_REACH = 0.01
MIRROR_HIT_SHARE, MIRROR_OVER_CHANCE, FAINT_AT_LEAST = 0.5, 3.0, 0.0005


def outside_share(image: Any, polygons: list[list[list[float]]]) -> float | None:
    """The share of the page's ink (as the blank test counts it) that lies outside every line's outline, `polygons` being
    fractions of the picture; None when the page has no ink to speak of."""
    import cv2
    import numpy as np

    from fichero_server.media.blank_page import INK_MAX, marks, work_gray

    gray = work_gray(image)
    ink = marks(gray)
    if ink.sum() < INK_MAX * gray.size:
        return None
    h, w = gray.shape
    boxes = np.zeros((h, w), np.uint8)
    for polygon in polygons:
        cv2.fillPoly(boxes, [np.array([[x * w, y * h] for x, y in polygon], np.int32)], 1)
    rim = max(1, round(LINE_RIM * h))
    boxes = cv2.dilate(boxes, np.ones((2 * rim + 1, 2 * rim + 1), np.uint8))
    return float((ink & (boxes == 0)).sum()) / float(ink.sum())


def shows_through(previous: Any, image: Any) -> bool | None:
    """Whether `image` carries a faint mirrored copy of the PREVIOUS page's ink: the previous page's strong ink flipped
    left to right (its back seen through this leaf); the faint marks of this page (6 to 35 levels under the paper's light,
    clear of this page's own ink) fall on it more than half the time and over three times what chance would put there (the
    share of the page it covers). None when this page has too few faint marks to say."""
    import cv2
    import numpy as np

    from fichero_server.media.blank_page import CONTRAST, marks, work_gray

    gray = work_gray(image)
    h, w = gray.shape
    own = marks(gray, FAINT_TO)
    reach = max(2, round(MIRROR_REACH * w))
    own = cv2.dilate(own.astype(np.uint8), np.ones((reach, reach), np.uint8)) > 0
    faint = marks(gray, FAINT_FROM, FAINT_TO) & ~own
    if faint.sum() < FAINT_AT_LEAST * gray.size:
        return None
    back = cv2.resize(marks(work_gray(previous), CONTRAST).astype(np.uint8), (w, h), interpolation=cv2.INTER_AREA)
    back = cv2.dilate(cv2.flip(back, 1), np.ones((2 * reach + 1, 2 * reach + 1), np.uint8)) > 0
    hit = float((faint & back).sum()) / float(faint.sum())
    chance = float(back.mean())
    return hit > MIRROR_HIT_SHARE and hit > MIRROR_OVER_CHANCE * chance


def _page_path(db: Any, doc_id: str) -> str | None:
    from pathlib import Path

    from fichero_server.models import Document
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    doc = db.get(Document, doc_id)
    return _resolve_abs_path(doc, str(Path(db.path).parent)) if doc is not None else None


def _page_image(db: Any, doc_id: str, *, frame_upright: bool = True) -> Any | None:
    from PIL import Image

    from fichero_server.media.upright import upright

    path = _page_path(db, doc_id)
    try:
        with Image.open(path) as opened:
            return upright(opened) if frame_upright else opened.convert("RGB")
    except (OSError, AttributeError, TypeError):
        return None


def _fraction_polygons(lines: Any) -> list[list[list[float]]]:
    from fichero_server.llm.working_lines import in_pixels

    return [in_pixels(row, 1.0, 1.0)["polygon"] for row in lines.lines]


def suggest(db: Any) -> dict[str, dict[str, Any]]:
    """`{question key: {value, agree, why}}` for the questions the sample answers; a question it cannot answer is absent."""
    from fichero_server.llm.working_lines import working_lines
    from fichero_server.media.find_page import find_page
    from fichero_server.media.upright import FRAME_UPRIGHT
    from fichero_server.recipes.prepare import is_faded

    ids = db.unit_of_work_ids()
    wide = covers = faded = ruled = seen = 0
    missed = lined = through = backed = 0
    for doc_id in sample_ids(ids):
        image = _page_image(db, doc_id)
        if image is None:
            continue
        seen += 1
        found = find_page(image)
        if found is not None:
            wide += found.box[2] * image.width > found.box[3] * image.height
            covers += found.box[2] * found.box[3] < COVERS_UNDER
        faded += is_faded(_page_path(db, doc_id))
        ruled += is_ruled(image)
        lines = working_lines(db, doc_id)
        if lines is not None:
            same_frame = _page_image(db, doc_id, frame_upright=lines.frame == FRAME_UPRIGHT)
            share = outside_share(same_frame, _fraction_polygons(lines))
            if share is not None:
                lined += 1
                missed += share > MISSED_SHARE
        index = ids.index(doc_id)
        before = _page_image(db, ids[index - 1]) if index > 0 else None
        if before is not None and (says := shows_through(before, image)) is not None:
            backed += 1
            through += says
    out: dict[str, dict[str, Any]] = {}

    def put(key: str, value: Any, hits: int, of: int, why: str) -> None:
        out[key] = {"value": value, "agree": f"{hits} of {of}", "why": why}

    if _agrees(wide, seen):
        put("two_pages_per_image", True, wide, seen, "the outlines are wider than tall")
    if _agrees(covers, seen):
        put("beside_the_page", "dark-mount", covers, seen, "the page covers under 85% of the picture")
    paper = [name for name, hits, of in (("ruled", ruled, seen), ("faded", faded, seen), ("show-through", through, backed))
             if _agrees(hits, of)]
    if paper:
        counts = {"ruled": (ruled, seen), "faded": (faded, seen), "show-through": (through, backed)}
        hits, of = max((counts[name] for name in paper), key=lambda pair: pair[0] / max(pair[1], 1))
        put("the_paper", paper, hits, of, "the sample shows " + " and ".join(paper) + " paper")
    if lined >= 3 and _agrees(missed, lined):
        put("check_missed_lines", True, missed, lined,
            f"over {MISSED_SHARE:.0%} of the ink lies outside the lines found (the characters-per-width test is not built yet)")
    return out


def estimate(pages: int) -> str:
    """The Start line's time: the seed figure, marked as an estimate."""
    minutes = max(1, round(pages * SEED_SECONDS_PER_PAGE / 60))
    return f"About {minutes} min for {pages} pages on this Mac (estimate). Nothing leaves this Mac."
