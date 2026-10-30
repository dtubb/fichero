"""Find the paper in a photograph with no model (`prep.find-the-page`, `image.enhance.page-crop`, #5382, #6185, #6198).

The classical finder, for a page on a dark mount or a light table with a ruler, a colour card or a hand beside it:

1. The background colour is the median of the image's outer frame; every pixel's distance from it (CIE Lab) is the
   "not background" map. Dark mount and light table are the same case.
2. Otsu splits that map; a big opening removes strips (a ruler's rim, a card's edge) thinner than the opening.
3. Of the pieces left, the page is the one with the most area near the centre; a piece that is a long thin strip on the
   image's edge (a ruler) or a small patch is never the page.
4. The box is trimmed on each side of rows/columns that are mostly background, so a ruler or card the page touches is
   cut off rather than kept.

Pure numpy/OpenCV, so it ships (OpenCV is bundled). Where nothing page-like is found it says so (`None`), and the
caller keeps the whole frame. The box is in fractions of the image, `[x, y, w, h]`: the unit Leave Out reads.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

#: Work on this long side; the box is scaled back up.
WORK_SIDE = 900
#: A page piece is at least this share of the image.
MIN_AREA = 0.08
#: A piece on an edge, thinner than this share of the image's short side, is furniture (a ruler), not a page.
STRIP_THIN = 0.12
#: A row or column of the box with less than this share of page pixels is trimmed off the box.
TRIM_BELOW = 0.25
#: Lab distance from the paper's colour under which a pixel of the piece still counts as paper (at least).
PAPER_TOLERANCE = 40.0
#: A piece beside the page smaller than this share of the image is dust, not furniture.
CARD_MIN_AREA = 0.004
#: A colour card is a filled rectangle: its pixels fill at least this share of its box, and it is at most 4:1.
CARD_FILL = 0.85
#: The rim around the page's box, as a share of the long side, that is not searched for furniture.
PAGE_PAD = 0.02
#: The rim added around the paper's box, as a share of the long side (the spec's 30 px on a 3000 px photograph).
PAD_SHARE = 0.01
#: The opening that removes thin strips, as a share of the working long side.
OPEN_SHARE = 0.012


@dataclass(frozen=True)
class PageFound:
    box: tuple[float, float, float, float]  # x, y, w, h as fractions of the image
    confidence: float
    method: str = "contour"
    #: What was left out beside the paper: `{"kind": "ruler" | "colour card", "box": [x, y, w, h]}`, fractions of the image.
    furniture: tuple[dict[str, Any], ...] = ()
    #: The paper's four corners, top-left, top-right, bottom-right, bottom-left, fractions of the image (`prep.square.*`
    #: warps from them). A box-shaped finder fills the box's corners.
    quad: tuple[tuple[float, float], ...] = ()

    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        """left, top, right, bottom in pixels of an image `width` x `height`."""
        x, y, w, h = self.box
        return round(x * width), round(y * height), round((x + w) * width), round((y + h) * height)


#: Vision's outline is trusted at or above this; below it the contour finder answers (`prep.page.opencv-default-yolo-optional`).
VISION_MIN = 0.5
#: Vision is shown the image at this long side: the corners are fractions, so the size does not change the answer.
VISION_SIDE = 1400
#: Vision's outline must be at least this share paper inside (`_paper_share`): a wrong outline above 0.5 confidence is not cropped to.
VISION_PAPER_SHARE = 0.7


def find_page(image: Any, *, vision: bool = True) -> PageFound | None:
    """The page on a PIL image: Apple Vision's outline first, then the contour finder; None when neither finds a page
    (the caller keeps the whole frame). Neither alters the original. ponytail: no YOLO page card yet (4.1 trains it)."""
    contour = find_page_contour(image)
    outline = find_page_vision(image) if vision else None
    if outline is None:
        return contour
    if contour is not None and not outline.furniture:  # Vision names no ruler or card; the contour finder saw them
        outline = PageFound(outline.box, outline.confidence, outline.method, contour.furniture, outline.quad)
    return outline


def find_page_vision(image: Any) -> PageFound | None:
    """Apple Vision's document outline of a PIL image (the upright frame), or None where it is unavailable, unsure or
    the outline is the whole frame."""
    import tempfile
    from pathlib import Path

    from fichero_server.media.page_split import detect_document_outline

    from PIL import Image

    small = image
    if max(small.size) > VISION_SIDE:
        scale = VISION_SIDE / max(small.size)  # shrunk before the RGB copy: no full-size copy of a big scan
        small = small.resize((max(1, round(small.width * scale)), max(1, round(small.height * scale))), Image.Resampling.BOX)
    small = small.convert("RGB")
    with tempfile.TemporaryDirectory() as scratch:
        shot = Path(scratch) / "page.jpg"
        small.save(shot, quality=90)
        outline = detect_document_outline(str(shot))
    if outline is None or outline.confidence < VISION_MIN or not outline.quad:
        return None
    xs, ys = [p[0] for p in outline.quad], [p[1] for p in outline.quad]
    box = (max(0.0, min(xs)), max(0.0, min(ys)), min(1.0, max(xs)) - max(0.0, min(xs)), min(1.0, max(ys)) - max(0.0, min(ys)))
    if box[2] * box[3] > 0.97:
        return None
    if _paper_share(image, outline.quad) < VISION_PAPER_SHARE:
        return None  # the outline takes in mount, table or furniture: not trusted, the contour finder answers
    return PageFound(box, round(outline.confidence, 3), "vision", quad=tuple(outline.quad))


def _paper_share(image: Any, quad: Any) -> float:
    """The share of the outline's inside that is paper: pixels within `PAPER_TOLERANCE` (CIE Lab) of the inside's median
    colour. An outline that straddles paper and mount, or covers half a page, has a low share."""
    import cv2

    rgb = _work_copy(image)
    h, w = rgb.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    cv2.fillPoly(mask, [np.array([[x * w, y * h] for x, y in quad], dtype=np.int32)], 1)
    inside = mask.astype(bool)
    if not inside.any():
        return 0.0
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 2), cv2.COLOR_RGB2LAB).astype(np.float32)[inside]
    return float((np.linalg.norm(lab - np.median(lab, axis=0), axis=1) < PAPER_TOLERANCE).mean())


def _work_copy(image: Any) -> np.ndarray:
    """The image as RGB at `WORK_SIDE` on its long side. Shrunk BEFORE it is converted, so a 66 MP scan never exists as a
    full-size RGB array here (the review measured +575 MB)."""
    from PIL import Image

    width, height = image.size
    scale = WORK_SIDE / max(width, height)
    if scale < 1:
        image = image.resize((max(1, round(width * scale)), max(1, round(height * scale))), Image.Resampling.BOX)
    return np.asarray(image.convert("RGB"))


def find_page_contour(image: Any) -> PageFound | None:
    """The contour finder: the page's box on a PIL image, or None when no piece looks like a page."""
    import cv2

    rgb = _work_copy(image)
    h, w = rgb.shape[:2]
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 2), cv2.COLOR_RGB2LAB).astype(np.float32)
    frame = max(2, round(0.02 * min(h, w)))
    ring = np.concatenate([lab[:frame].reshape(-1, 3), lab[-frame:].reshape(-1, 3),
                           lab[:, :frame].reshape(-1, 3), lab[:, -frame:].reshape(-1, 3)])
    distance = np.linalg.norm(lab - np.median(ring, axis=0), axis=2)
    scaled = np.clip(distance * (255 / max(float(distance.max()), 1.0)), 0, 255).astype(np.uint8)
    _, mask = cv2.threshold(scaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    size = max(3, round(OPEN_SHARE * max(h, w)) | 1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (size, size)))
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    best, best_score = None, 0.0
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if area < MIN_AREA * h * w:
            continue
        on_edge = x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1
        if on_edge and min(bw, bh) < STRIP_THIN * min(h, w):
            continue  # a ruler along an edge
        cx, cy = centroids[i]
        centrality = 1.0 - 0.5 * np.hypot((cx - w / 2) / w, (cy - h / 2) / h) * 2
        score = float(area) * max(centrality, 0.1)
        if score > best_score:
            best, best_score = i, score
    if best is None:
        return None
    piece = labels == best
    # Paper colour from the piece's middle; what is far from it (a ruler or card the page touches) is not paper.
    bx, by, bw, bh = stats[best][:4]
    centre = lab[by + bh // 4: by + 3 * bh // 4, bx + bw // 4: bx + 3 * bw // 4].reshape(-1, 3)
    paper = np.median(centre, axis=0)
    spread = np.percentile(np.linalg.norm(centre - paper, axis=1), 70)
    piece = piece & (np.linalg.norm(lab - paper, axis=2) < max(PAPER_TOLERANCE, 2.5 * spread))
    if not piece.any():
        return None
    x0, y0, x1, y1 = _trim(piece)
    if x1 <= x0 or y1 <= y0:
        return None
    box = piece[y0:y1, x0:x1]
    fill = float(box.mean())
    if (x1 - x0) * (y1 - y0) > 0.97 * h * w:
        return None  # the whole frame: nothing was left out
    # The box is trimmed by rows and columns, which cuts the pointed corners of a tilted page; the corners come from the
    # whole piece with a ruler's thin attachment opened away instead.
    size = max(3, round(0.03 * max(h, w)) | 1)
    opened = cv2.morphologyEx(piece.astype(np.uint8), cv2.MORPH_OPEN,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (size, size))).astype(bool)
    quad = _quad(opened if opened.any() else piece[y0:y1, x0:x1], 0 if opened.any() else x0, 0 if opened.any() else y0, w, h)
    # A page photographed at an angle fills little of its upright box but all of its own quad: the confidence is the
    # paper's share of the larger of the two (a ragged guess still scores low in both).
    xs, ys = [p[0] * w for p in quad], [p[1] * h for p in quad]
    area = 0.5 * abs(sum(xs[i] * ys[(i + 1) % 4] - xs[(i + 1) % 4] * ys[i] for i in range(4)))
    if area > 0:
        fill = max(fill, min(1.0, float(piece.sum()) / area))
    # The box takes in the corners (a tilted page's points lie outside the trimmed box) and a rim of PAD_SHARE of the long
    # side (30 px on a 3000 px photograph), so Kraken never loses a line in a corner; the quad's corners come from the
    # opened piece, so a ruler the page touches is still out.
    pad = round(PAD_SHARE * max(h, w))
    bx0, by0 = max(0, min(x0, int(min(xs))) - pad), max(0, min(y0, int(min(ys))) - pad)
    bx1, by1 = min(w, max(x1, int(np.ceil(max(xs)))) + pad), min(h, max(y1, int(np.ceil(max(ys)))) + pad)
    return PageFound((bx0 / w, by0 / h, (bx1 - bx0) / w, (by1 - by0) / h), round(fill, 3),
                     furniture=tuple(_furniture(mask, (x0, y0, x1, y1))), quad=quad)


def _quad(piece: np.ndarray, x0: int, y0: int, w: int, h: int) -> tuple[tuple[float, float], ...]:
    """The piece's four corners (top-left, top-right, bottom-right, bottom-left) as fractions of the whole image: the
    largest contour's four-corner polygon, else its minimum-area rectangle."""
    import cv2

    contours, _ = cv2.findContours(piece.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    big = max(contours, key=cv2.contourArea)
    poly = cv2.approxPolyDP(big, 0.02 * cv2.arcLength(big, True), True)
    pts = poly.reshape(-1, 2).astype(np.float32) if len(poly) == 4 else cv2.boxPoints(cv2.minAreaRect(big))
    pts = pts + np.array([x0, y0], dtype=np.float32)
    # Order by sum and difference of coordinates: top-left has the smallest sum, bottom-right the largest.
    s, d = pts.sum(axis=1), pts[:, 0] - pts[:, 1]
    ordered = [pts[np.argmin(s)], pts[np.argmax(d)], pts[np.argmax(s)], pts[np.argmin(d)]]
    return tuple((round(float(px) / w, 5), round(float(py) / h, 5)) for px, py in ordered)


def _furniture(mask: np.ndarray, page: tuple[int, int, int, int]) -> list[dict[str, Any]]:
    """The pieces beside the page: a long thin strip on an edge is a ruler; a compact, colourless patch is a colour card."""
    import cv2

    h, w = mask.shape
    rest = mask.copy()
    pad = round(PAGE_PAD * max(h, w))  # the page's own rim (trimmed pixels) is not furniture
    rest[max(0, page[1] - pad):page[3] + pad, max(0, page[0] - pad):page[2] + pad] = 0
    count, _, stats, _ = cv2.connectedComponentsWithStats(rest)
    out = []
    for i in range(1, count):
        x, y, bw, bh, area = (int(v) for v in stats[i])
        if area < CARD_MIN_AREA * h * w:
            continue
        on_edge = x <= 1 or y <= 1 or x + bw >= w - 1 or y + bh >= h - 1
        long_side, short_side = max(bw, bh), max(1, min(bw, bh))
        if on_edge and short_side < STRIP_THIN * min(h, w) and long_side >= 3 * short_side:
            kind = "ruler"
        else:
            if area < CARD_FILL * bw * bh or long_side > 4 * short_side:
                continue  # not a rectangle: a hand, a shadow
            kind = "colour card"
        out.append({"kind": kind, "box": [round(x / w, 5), round(y / h, 5), round(bw / w, 5), round(bh / h, 5)]})
    return out


def _trim(piece: np.ndarray) -> tuple[int, int, int, int]:
    """The piece's bounding box with edge rows and columns that are mostly not the piece cut away."""
    ys, xs = np.nonzero(piece)
    x0, x1, y0, y1 = int(xs.min()), int(xs.max()) + 1, int(ys.min()), int(ys.max()) + 1
    for _ in range(4):
        sub = piece[y0:y1, x0:x1]
        cols, rows = sub.mean(axis=0), sub.mean(axis=1)
        nx0 = x0 + int(np.argmax(cols >= TRIM_BELOW)) if (cols >= TRIM_BELOW).any() else x0
        nx1 = x1 - int(np.argmax(cols[::-1] >= TRIM_BELOW)) if (cols >= TRIM_BELOW).any() else x1
        ny0 = y0 + int(np.argmax(rows >= TRIM_BELOW)) if (rows >= TRIM_BELOW).any() else y0
        ny1 = y1 - int(np.argmax(rows[::-1] >= TRIM_BELOW)) if (rows >= TRIM_BELOW).any() else y1
        if (nx0, nx1, ny0, ny1) == (x0, x1, y0, y1):
            break
        x0, x1, y0, y1 = nx0, nx1, ny0, ny1
    return x0, y0, x1, y1
