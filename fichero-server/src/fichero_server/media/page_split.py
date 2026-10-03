"""Find the page(s) in a photograph and cut a spread at its gutter (`prep.split-at-the-gutter`, #5382).

The order comes from the review on the Sergio notebooks (fichero-projects
`projects/sergio-notebooks/prep-review.md`, 11 photos, 2026-10-03):

1. **Find the notebook** with Apple Vision's document outline
   (`VNDetectDocumentSegmentationRequest`): a tight outline on 11 of 11 photos, where today's
   `detect_content_bbox` returned the whole frame on all 11 (the grey table passes its threshold).
2. **Never cut a closed notebook.** An outline narrower than it is tall is one page: the three closed
   covers measured 0.70-0.75 wide-to-high, the eight open notebooks 1.36-1.44. The legacy split cut
   two of the three covers because it had no outline to measure.
3. **Find the gutter inside the outline**, not at the image's middle: the darkest column of the
   middle band (the legacy `split.py` idea). The spirals sat 50-250 px off the photo's centre, so
   a fixed half cut into the text on every spread.
4. **Report how sure it is.** The gutter's depth (how much darker than the band's median) is the
   confidence; below the threshold the spread is proposed for review, not cut
   (`prep.unsure-becomes-a-proposal`).

Everything here is pure geometry on numbers and arrays except `detect_document_outline`, which asks
Apple Vision and returns None where it is unavailable, so the split degrades to the whole frame.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

#: An outline at least this much wider than tall is an open spread; narrower is one page.
SINGLE_PAGE_MAX_ASPECT = 1.0
#: Below this gutter depth a spread is proposed, not cut. Measured on the eight open Sergio notebooks:
#: 0.19-0.63 (C04_090, a pale spiral shadow, is the lowest); a closed cover's centre measured 0.07-0.08.
MIN_GUTTER_CONFIDENCE = 0.15
#: The gutter is searched in this fraction of the outline's width, around its middle.
GUTTER_BAND = (0.35, 0.65)
#: Below this Vision confidence the outline is not trusted and the whole frame is used.
MIN_OUTLINE_CONFIDENCE = 0.5
#: Column profiles are taken every STEP pixels (the gutter is ~100 px wide at 3000 px).
PROFILE_STEP = 4


@dataclass(frozen=True)
class Outline:
    """Where the document is in the image, in pixels of the image's own (unrotated) frame."""

    box: tuple[int, int, int, int]  # left, top, right, bottom
    confidence: float
    method: str  # "apple-vision" or "frame"
    quad: tuple[tuple[float, float], ...] | None = None  # normalised, top-left origin, clockwise from top-left

    @property
    def aspect(self) -> float:
        left, top, right, bottom = self.box
        return (right - left) / max(1, bottom - top)


def whole_frame(width: int, height: int) -> Outline:
    """The fallback when no outline is found: the image itself, said so by its method."""
    return Outline((0, 0, width, height), 0.0, "frame")


def column_profile(gray: np.ndarray, box: tuple[int, int, int, int], step: int = PROFILE_STEP) -> np.ndarray:
    """Mean brightness of every `step`-th column inside `box`, over its middle 80% of rows.

    The top and bottom tenth are left out: the outline's edges and the table show there, not the
    gutter."""
    left, top, right, bottom = box
    margin = (bottom - top) // 10
    region = np.asarray(gray, dtype=np.float32)[top + margin:bottom - margin, left:right:step]
    return region.mean(axis=0) if region.size else np.zeros(0, dtype=np.float32)


def find_gutter(profile: np.ndarray, step: int = PROFILE_STEP,
                band: tuple[float, float] = GUTTER_BAND) -> tuple[int, float]:
    """(x offset in pixels from the profile's left edge, confidence 0-1) of the darkest column in the band.

    Confidence is the gutter's depth: (band median - darkest) / band median. A spiral or a gutter
    shadow is a column much darker than the paper around it; a cover or a page with no gutter
    has none, and its depth is near 0."""
    profile = np.asarray(profile, dtype=np.float32)
    n = len(profile)
    if n < 10:
        return 0, 0.0
    smooth = np.convolve(profile, np.ones(3) / 3, mode="same")
    lo, hi = int(band[0] * n), max(int(band[0] * n) + 1, int(band[1] * n))
    window = smooth[lo:hi]
    i = int(np.argmin(window))
    median = float(np.median(window))
    depth = (median - float(window[i])) / median if median > 0 else 0.0
    return (lo + i) * step, max(0.0, min(1.0, depth))


def plan_split(size: tuple[int, int], outline: Outline, gutter_x: int | None, confidence: float, *,
               direction: str = "ltr", min_confidence: float = MIN_GUTTER_CONFIDENCE) -> dict[str, Any]:
    """Decide the pages of one image: their boxes (x, y, w, h, in reading order) and why.

    `gutter_x` is in image pixels. A single-page outline is one page, never cut; a spread is cut at
    its gutter when the gutter is clear, else kept whole and flagged as a proposal with the cut it
    would have made."""
    left, top, right, bottom = outline.box
    whole = [left, top, right - left, bottom - top]
    base = {"outline": list(outline.box), "outline_method": outline.method,
            "outline_confidence": round(outline.confidence, 3), "aspect": round(outline.aspect, 3),
            "gutter_x": gutter_x, "gutter_confidence": round(confidence, 3)}
    if outline.aspect < SINGLE_PAGE_MAX_ASPECT:
        return {**base, "decision": "single_page", "pages": [whole], "needs_review": False,
                "reason": f"outline is {outline.aspect:.2f} wide-to-high: one page, not cut"}
    if gutter_x is None or not (left < gutter_x < right) or confidence < min_confidence:
        return {**base, "decision": "proposed", "pages": [whole], "needs_review": True,
                "reason": f"a spread, but its gutter is unclear (confidence {confidence:.2f} < "
                          f"{min_confidence:.2f}): kept whole, cut proposed at x={gutter_x}"}
    pages = [[left, top, gutter_x - left, bottom - top], [gutter_x, top, right - gutter_x, bottom - top]]
    if direction == "rtl":
        pages.reverse()
    return {**base, "decision": "split", "pages": pages, "needs_review": False,
            "reason": f"a spread cut at its gutter x={gutter_x} (confidence {confidence:.2f})"}


def split_plan_for_image(gray: np.ndarray, outline: Outline, *, direction: str = "ltr",
                         min_confidence: float = MIN_GUTTER_CONFIDENCE) -> dict[str, Any]:
    """Outline -> gutter -> pages, for one greyscale image (height x width)."""
    height, width = np.asarray(gray).shape[:2]
    gutter_x, confidence = None, 0.0
    if outline.aspect >= SINGLE_PAGE_MAX_ASPECT:
        offset, confidence = find_gutter(column_profile(gray, outline.box))
        gutter_x = outline.box[0] + offset
    return plan_split((width, height), outline, gutter_x, confidence, direction=direction,
                      min_confidence=min_confidence)


def detect_document_outline(path: str) -> Outline | None:
    """Apple Vision's document outline for an image file, or None where Vision is unavailable or
    finds nothing it is sure of. Coordinates are in the file's own pixel frame (EXIF not applied),
    the frame `region_in_parent` is measured against."""
    try:
        import Vision  # type: ignore[import-not-found]
        from Foundation import NSURL  # type: ignore[import-not-found]
        from Quartz import (  # type: ignore[import-not-found]
            CGImageGetHeight,
            CGImageGetWidth,
            CGImageSourceCreateImageAtIndex,
            CGImageSourceCreateWithURL,
        )
    except ImportError:
        return None
    source = CGImageSourceCreateWithURL(NSURL.fileURLWithPath_(str(path)), None)
    image = CGImageSourceCreateImageAtIndex(source, 0, None) if source is not None else None
    if image is None:
        return None
    width, height = CGImageGetWidth(image), CGImageGetHeight(image)
    request = Vision.VNDetectDocumentSegmentationRequest.alloc().init()
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
    ok, _error = handler.performRequests_error_([request], None)
    results = list(request.results() or []) if ok else []
    if not results:
        return None
    best = max(results, key=lambda r: float(r.confidence()))
    if float(best.confidence()) < MIN_OUTLINE_CONFIDENCE:
        return None
    # Vision's normalised points have a bottom-left origin; the library's frames are top-left.
    quad = tuple((float(p.x), 1.0 - float(p.y))
                 for p in (best.topLeft(), best.topRight(), best.bottomRight(), best.bottomLeft()))
    xs, ys = [x * width for x, _ in quad], [y * height for _, y in quad]
    box = (max(0, int(min(xs))), max(0, int(min(ys))), min(width, int(round(max(xs)))), min(height, int(round(max(ys)))))
    return Outline(box, float(best.confidence()), "apple-vision", quad)
