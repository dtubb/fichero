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
TRIM_BELOW = 0.5
#: Lab distance from the paper's colour under which a pixel of the piece still counts as paper (at least).
PAPER_TOLERANCE = 22.0
#: A piece beside the page smaller than this share of the image is dust, not furniture.
CARD_MIN_AREA = 0.004
#: A colour card is a filled rectangle: its pixels fill at least this share of its box, and it is at most 4:1.
CARD_FILL = 0.85
#: The rim around the page's box, as a share of the long side, that is not searched for furniture.
PAGE_PAD = 0.02
#: The opening that removes thin strips, as a share of the working long side.
OPEN_SHARE = 0.012


@dataclass(frozen=True)
class PageFound:
    box: tuple[float, float, float, float]  # x, y, w, h as fractions of the image
    confidence: float
    method: str = "contour"
    #: What was left out beside the paper: `{"kind": "ruler" | "colour card", "box": [x, y, w, h]}`, fractions of the image.
    furniture: tuple[dict[str, Any], ...] = ()

    def pixels(self, width: int, height: int) -> tuple[int, int, int, int]:
        """left, top, right, bottom in pixels of an image `width` x `height`."""
        x, y, w, h = self.box
        return round(x * width), round(y * height), round((x + w) * width), round((y + h) * height)


def find_page(image: Any) -> PageFound | None:
    """The page's box on a PIL image, or None when no piece looks like a page (the caller keeps the whole frame)."""
    import cv2

    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    scale = WORK_SIDE / max(height, width)
    if scale < 1:
        rgb = cv2.resize(rgb, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
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
    piece = piece & (np.linalg.norm(lab - paper, axis=2) < max(PAPER_TOLERANCE, 1.5 * spread))
    if not piece.any():
        return None
    x0, y0, x1, y1 = _trim(piece)
    if x1 <= x0 or y1 <= y0:
        return None
    box = piece[y0:y1, x0:x1]
    fill = float(box.mean())
    if (x1 - x0) * (y1 - y0) > 0.97 * h * w:
        return None  # the whole frame: nothing was left out
    return PageFound((x0 / w, y0 / h, (x1 - x0) / w, (y1 - y0) / h), round(fill, 3),
                     furniture=tuple(_furniture(mask, (x0, y0, x1, y1))))


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
