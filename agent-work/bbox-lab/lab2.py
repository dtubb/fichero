"""Vision region experiments (2026-09-03) — Daniel's question:

  "Can we get much better results from the Apple Vision detect regions?
   Like, could giving it the actual text improve results?"

Builds on `lab.py` (2026-09-02 overnight): same ink mask, same metrics, same
overlay convention. What is new here:

  E1 text-guided alignment — feed the page's KNOWN transcript into the
     production `merge_reviewed_text_onto_geometry` and measure the geometry
     that comes out, not just the text.
  E2 two-pass zoom — re-OCR each detected line/region on a 2-4x upscaled crop.
  E3 strip density — full page vs N overlapping strips on top of production.
  E4 request sweep — recognition level, revision, languages, language
     correction, automatic language detection: BOXES only.
  E5 region derivation — cluster word boxes into lines/blocks and compare with
     Vision's own line observations.

Samples: `samples_text/` — scratch COPIES of Marshall page images that have a
`.transcript.txt` beside them in the read-only import tree, so every page here
has known text. Never touches ~/Fichero or the import originals.

Usage:  PYTHONPATH=fichero-server/src .venv/bin/python agent-work/bbox-lab/lab2.py <cmd>
"""
from __future__ import annotations

import glob
import json
import os
import sys
import time

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lab import cached_mask, ink_mask  # noqa: E402

LAB = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(LAB, "samples_text")
OUT = os.path.join(LAB, "out2")
os.makedirs(OUT, exist_ok=True)


# ------------------------------------------------------------------ samples

def pages() -> list[tuple[str, str, str]]:
    """(name, image_path, reviewed_text) for every text-paired sample."""
    rows = []
    for img in sorted(glob.glob(os.path.join(SAMPLES, "*.jpg"))):
        name = os.path.splitext(os.path.basename(img))[0]
        txt = os.path.join(SAMPLES, f"{name}.txt")
        rows.append((name, img, open(txt).read() if os.path.exists(txt) else ""))
    return rows


# ------------------------------------------------------------------ metrics

def box_metrics(image_path: str, boxes, *, mask=None) -> dict:
    """Geometry-only metrics for a list of objects carrying `.bbox`.

    ink_recall   — fraction of the page's TEXT ink inside some box (coverage)
    tightness    — fraction of the boxed area that is ink (does a box swallow paper)
    hit_rate     — fraction of boxes that contain real ink at all. A box on
                   blank paper is a FALSE placement: it looks authoritative and
                   points at nothing. Recall alone cannot see these.
    """
    mask = cached_mask(image_path) if mask is None else mask
    h, w = mask.shape
    union = np.zeros_like(mask)
    hits = 0
    counted = 0
    for b in boxes:
        x, y, bw, bh = b.bbox
        x0, y0 = max(0, int(x * w)), max(0, int(y * h))
        x1, y1 = min(w, int((x + bw) * w)), min(h, int((y + bh) * h))
        if x1 <= x0 or y1 <= y0:
            continue
        counted += 1
        union[y0:y1, x0:x1] = True
        if int(mask[y0:y1, x0:x1].sum()) >= 30:
            hits += 1
    total_ink = int(mask.sum())
    union_ink = int((mask & union).sum())
    union_area = int(union.sum())
    return {
        "boxes": counted,
        "ink_recall": round(union_ink / total_ink, 3) if total_ink else None,
        "tightness": round(union_ink / union_area, 3) if union_area else None,
        "hit_rate": round(hits / counted, 3) if counted else None,
    }


def overlay(image_path: str, groups, out_path: str, title: str = "") -> None:
    """groups: list of (boxes, rgb) drawn back-to-front."""
    img = Image.open(image_path).convert("RGB")
    scale = min(1.0, 1600 / img.width)
    if scale < 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)))
    w, h = img.size
    draw = ImageDraw.Draw(img, "RGBA")
    for boxes, color in groups:
        for b in boxes:
            x, y, bw, bh = b.bbox
            draw.rectangle([x * w, y * h, (x + bw) * w, (y + bh) * h],
                           outline=color, width=2)
    if title:
        draw.rectangle([0, 0, w, 26], fill=(0, 0, 0, 170))
        draw.text((8, 6), title, fill=(255, 255, 255, 255))
    img.save(out_path)


def dump(tag: str, rows: dict) -> dict:
    with open(os.path.join(OUT, f"metrics_{tag}.json"), "w") as f:
        json.dump(rows, f, indent=2)
    print(json.dumps({tag: rows}, indent=2))
    return rows


# --------------------------------------------------------- raw vision call

def raw_vision(
    image_path: str,
    *,
    level: str = "accurate",
    revision: int | None = None,
    languages: tuple[str, ...] = ("en",),
    correction: bool = True,
    autodetect: bool | None = None,
    min_text_height: float | None = None,
    upscale: float = 1.0,
):
    """ONE VNRecognizeTextRequest, no escalation — so a sweep isolates the
    request parameter under test from the production retry ladder.

    `upscale` resamples the image first; boxes stay normalized, so they remain
    valid in the original page frame.
    """
    import Vision
    from Quartz import CGImageSourceCreateWithURL, CGImageSourceCreateImageAtIndex
    from Foundation import NSURL
    from fichero_server.workflows.tools import vision_base

    path = image_path
    tmp = None
    if upscale != 1.0:
        with Image.open(image_path) as im:
            im = im.convert("RGB").resize(
                (int(im.width * upscale), int(im.height * upscale)), Image.LANCZOS)
            tmp = os.path.join(OUT, "_up.png")
            im.save(tmp)
        path = tmp

    url = NSURL.fileURLWithPath_(path)
    src = CGImageSourceCreateWithURL(url, None)
    cg = CGImageSourceCreateImageAtIndex(src, 0, None)

    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(
        Vision.VNRequestTextRecognitionLevelAccurate if level == "accurate"
        else Vision.VNRequestTextRecognitionLevelFast)
    if revision is not None:
        req.setRevision_(revision)
    req.setRecognitionLanguages_(list(languages))
    req.setUsesLanguageCorrection_(correction)
    if autodetect is not None and hasattr(req, "setAutomaticallyDetectsLanguage_"):
        req.setAutomaticallyDetectsLanguage_(autodetect)
    if min_text_height is not None:
        req.setMinimumTextHeight_(min_text_height)

    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(cg, None)
    ok, _ = handler.performRequests_error_([req], None)
    results = req.results() if ok else None
    if not results:
        return vision_base.VisionOCRResult(text="", line_boxes=[], word_boxes=[])
    return vision_base._vision_geometry_from_results(results)


def production(image_path: str, reference_text: str | None = None):
    from fichero_server.workflows.tools import vision_base
    return vision_base.apple_vision_ocr_with_geometry(image_path, "en", reference_text)


# --------------------------------------------------------------- E1 merge

def to_geometry_result(result, image_path: str):
    """VisionOCRResult -> OCRGeometryResult (what geometry_merge consumes)."""
    from fichero_server.workflows.tools import vision_base
    return vision_base._apple_geometry_result(result)


def cmd_merge() -> None:
    """E1 — text-guided alignment: known transcript onto measured boxes."""
    from fichero_server.media import geometry_merge

    rows = {}
    for name, path, text in pages():
        if not text.strip():
            continue
        mask = cached_mask(path)
        t0 = time.time()
        measured = production(path)
        secs = round(time.time() - t0, 1)
        geo = to_geometry_result(measured, path)
        base = box_metrics(path, measured.word_boxes, mask=mask)
        base["seconds"] = secs
        row = {"vision": base}

        if geo is None:
            rows[name] = {**row, "merge": {"refused": True, "reason": "no geometry"}}
            continue
        outcome = geometry_merge.merge_reviewed_text_onto_geometry(text, geo)
        if outcome.refused or outcome.result is None:
            row["merge"] = {"refused": True, "reason": outcome.reason,
                            "lines_matched": outcome.lines_matched,
                            "lines_total": outcome.lines_total}
            rows[name] = row
            continue
        from fichero_server.media.ocr_geometry import OCRGeometryLevel
        words = [b for b in outcome.result.boxes if b.level == OCRGeometryLevel.WORD]
        meas = [b for b in words if (b.metadata or {}).get("provenance") != geometry_merge.DERIVED]
        deriv = [b for b in words if (b.metadata or {}).get("provenance") == geometry_merge.DERIVED]
        row["merge"] = {
            "refused": False,
            "coverage": round(outcome.coverage, 3),
            "lines_matched": outcome.lines_matched,
            "lines_total": outcome.lines_total,
            "measured_words": outcome.measured_words,
            "derived_words": outcome.derived_words,
            "all": box_metrics(path, words, mask=mask),
            "measured_only": box_metrics(path, meas, mask=mask) if meas else None,
            "derived_only": box_metrics(path, deriv, mask=mask) if deriv else None,
        }
        overlay(path,
                [(measured.word_boxes, (120, 120, 120, 140)),
                 (meas, (0, 180, 60, 230)), (deriv, (255, 140, 0, 230))],
                os.path.join(OUT, f"{name}__merge.png"),
                f"merge  cov={outcome.coverage:.2f} meas={len(meas)} deriv={len(deriv)}")
        rows[name] = row
    dump("e1_merge", rows)


# ---------------------------------------------------------------- E2 zoom

def zoom_lines(image_path: str, base, *, factor: float = 3.0, pad: float = 0.01):
    """Re-OCR every detected LINE on an upscaled crop; keep the crop's word
    boxes where the crop reproduces the line, mapped back to the page frame."""
    from fichero_server.workflows.tools import vision_base
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    words: list = []
    kept_lines = 0
    for line in base.line_boxes:
        x, y, bw, bh = line.bbox
        x0 = max(0.0, x - pad); y0 = max(0.0, y - pad)
        x1 = min(1.0, x + bw + pad); y1 = min(1.0, y + bh + pad)
        crop = img.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))
        if crop.width < 16 or crop.height < 8:
            continue
        crop = crop.resize((int(crop.width * factor), int(crop.height * factor)),
                           Image.LANCZOS)
        cpath = os.path.join(OUT, "_zoomcrop.png")
        crop.save(cpath)
        sub = raw_vision(cpath)
        if not sub.word_boxes:
            continue
        fx, fy = (x1 - x0), (y1 - y0)
        for b in sub.word_boxes:
            bx, by, bw2, bh2 = b.bbox
            b.bbox = [x0 + bx * fx, y0 + by * fy, bw2 * fx, bh2 * fy]
        words.extend(sub.word_boxes)
        kept_lines += 1
    return vision_base.VisionOCRResult(
        text=base.text, line_boxes=base.line_boxes, word_boxes=words), kept_lines


def cmd_zoom() -> None:
    """E2 — do word boxes improve when each line is re-read zoomed in?"""
    rows = {}
    for name, path, _ in pages():
        mask = cached_mask(path)
        base = production(path)
        row = {"production": box_metrics(path, base.word_boxes, mask=mask)}
        for factor in (2.0, 3.0, 4.0):
            t0 = time.time()
            zoomed, kept = zoom_lines(path, base, factor=factor)
            m = box_metrics(path, zoomed.word_boxes, mask=mask)
            m["lines_reread"] = kept
            m["lines_total"] = len(base.line_boxes)
            m["seconds"] = round(time.time() - t0, 1)
            row[f"zoom{factor:g}x"] = m
            if factor == 3.0:
                overlay(path, [(base.word_boxes, (120, 120, 120, 150)),
                               (zoomed.word_boxes, (0, 180, 60, 230))],
                        os.path.join(OUT, f"{name}__zoom3x.png"),
                        f"zoom3x  n={m['boxes']} recall={m['ink_recall']} tight={m['tightness']}")
        # whole-page upscale, single pass, for contrast
        for factor in (2.0,):
            t0 = time.time()
            up = raw_vision(path, upscale=factor)
            m = box_metrics(path, up.word_boxes, mask=mask)
            m["seconds"] = round(time.time() - t0, 1)
            row[f"page_upscale{factor:g}x"] = m
        row["single_pass"] = box_metrics(path, raw_vision(path).word_boxes, mask=mask)
        rows[name] = row
    dump("e2_zoom", rows)


# -------------------------------------------------------------- E3 strips

def strip_pass(image_path: str, *, count: int, overlap: float = 0.08):
    """N overlapping horizontal strips, each OCR'd whole, boxes mapped back."""
    from fichero_server.workflows.tools import vision_base
    img = Image.open(image_path).convert("RGB")
    W, H = img.size
    lines: list = []
    words: list = []
    span = 1.0 / count
    for i in range(count):
        y0 = max(0.0, i * span - overlap * span)
        y1 = min(1.0, (i + 1) * span + overlap * span)
        crop = img.crop((0, int(y0 * H), W, int(y1 * H)))
        cpath = os.path.join(OUT, "_strip.png")
        crop.save(cpath)
        sub = raw_vision(cpath)
        fy = y1 - y0
        for b in sub.line_boxes + sub.word_boxes:
            bx, by, bw, bh = b.bbox
            b.bbox = [bx, y0 + by * fy, bw, bh * fy]
        for line in sub.line_boxes:
            if vision_base._is_duplicate_line(line, lines):
                continue
            lines.append(line)
            s, e = line.char_start, line.char_end
            if s is not None and e is not None:
                words.extend(w for w in sub.word_boxes
                             if w.char_start is not None and s <= w.char_start < e)
    text, lines, words = vision_base._rebase_geometry_reading_order(lines, words)
    return vision_base.VisionOCRResult(text=text, line_boxes=lines, word_boxes=words)


def cmd_strips() -> None:
    """E3 — does denser strip tiling find lines the full page misses?"""
    rows = {}
    for name, path, _ in pages():
        mask = cached_mask(path)
        row = {"single_pass": box_metrics(path, raw_vision(path).word_boxes, mask=mask),
               "production": box_metrics(path, production(path).word_boxes, mask=mask)}
        for count in (3, 6, 10):
            t0 = time.time()
            res = strip_pass(path, count=count)
            m = box_metrics(path, res.word_boxes, mask=mask)
            m["lines"] = len(res.line_boxes)
            m["seconds"] = round(time.time() - t0, 1)
            row[f"strips{count}"] = m
        rows[name] = row
    dump("e3_strips", rows)


# --------------------------------------------------------------- E4 sweep

SWEEP = [
    ("accurate_en", dict(level="accurate", languages=("en",))),
    ("fast_en", dict(level="fast", languages=("en",))),
    ("accurate_es", dict(level="accurate", languages=("es",))),
    ("accurate_es_en", dict(level="accurate", languages=("es", "en"))),
    ("accurate_nocorrect", dict(level="accurate", languages=("en",), correction=False)),
    ("accurate_autodetect", dict(level="accurate", languages=("en",), autodetect=True)),
    ("accurate_minheight0", dict(level="accurate", languages=("en",), min_text_height=0.0)),
]


def cmd_sweep() -> None:
    """E4 — request parameters, measured on BOXES not on text."""
    import Vision
    revs = list(Vision.VNRecognizeTextRequest.supportedRevisions())
    print("supported revisions:", revs)
    rows = {"_revisions": revs}
    for name, path, _ in pages():
        mask = cached_mask(path)
        row = {}
        for tag, opts in SWEEP:
            t0 = time.time()
            res = raw_vision(path, **opts)
            m = box_metrics(path, res.word_boxes, mask=mask)
            m["lines"] = len(res.line_boxes)
            m["chars"] = len(res.text)
            m["seconds"] = round(time.time() - t0, 1)
            row[tag] = m
        for rev in revs:
            res = raw_vision(path, revision=int(rev))
            m = box_metrics(path, res.word_boxes, mask=mask)
            m["lines"] = len(res.line_boxes)
            row[f"revision{int(rev)}"] = m
        rows[name] = row
    dump("e4_sweep", rows)


# ------------------------------------------------------------- E5 regions

def cluster_lines(words, *, gap: float = 0.6):
    """Group word boxes into lines by vertical band overlap, then into blocks
    by horizontal proximity. Returns (line_rects, block_rects) as simple
    box-alikes so box_metrics can read them."""
    class _B:
        __slots__ = ("bbox",)

        def __init__(self, bbox):
            self.bbox = bbox

    if not words:
        return [], []
    items = sorted(words, key=lambda b: b.bbox[1] + b.bbox[3] / 2)
    lines: list[list] = []
    for b in items:
        cy = b.bbox[1] + b.bbox[3] / 2
        placed = False
        for group in lines:
            gy = np.mean([g.bbox[1] + g.bbox[3] / 2 for g in group])
            gh = np.mean([g.bbox[3] for g in group])
            if abs(cy - gy) <= gap * gh:
                group.append(b)
                placed = True
                break
        if not placed:
            lines.append([b])

    def envelope(group):
        x0 = min(g.bbox[0] for g in group)
        y0 = min(g.bbox[1] for g in group)
        x1 = max(g.bbox[0] + g.bbox[2] for g in group)
        y1 = max(g.bbox[1] + g.bbox[3] for g in group)
        return _B([x0, y0, x1 - x0, y1 - y0])

    line_rects = [envelope(g) for g in lines]
    blocks: list[list] = []
    for lr in sorted(line_rects, key=lambda b: b.bbox[1]):
        if blocks:
            prev = blocks[-1][-1]
            vgap = lr.bbox[1] - (prev.bbox[1] + prev.bbox[3])
            if vgap <= 1.2 * prev.bbox[3]:
                blocks[-1].append(lr)
                continue
        blocks.append([lr])
    return line_rects, [envelope(b) for b in blocks]


def cmd_regions() -> None:
    """E5 — clustered lines/blocks vs Vision's own line observations."""
    rows = {}
    for name, path, _ in pages():
        mask = cached_mask(path)
        res = production(path)
        line_rects, block_rects = cluster_lines(res.word_boxes)
        rows[name] = {
            "vision_lines": {**box_metrics(path, res.line_boxes, mask=mask),
                             "n": len(res.line_boxes)},
            "clustered_lines": {**box_metrics(path, line_rects, mask=mask),
                                "n": len(line_rects)},
            "clustered_blocks": {**box_metrics(path, block_rects, mask=mask),
                                 "n": len(block_rects)},
            "words": {**box_metrics(path, res.word_boxes, mask=mask)},
        }
        overlay(path, [(res.line_boxes, (40, 90, 255, 170)),
                       (line_rects, (0, 200, 80, 220)),
                       (block_rects, (220, 40, 200, 220))],
                os.path.join(OUT, f"{name}__regions.png"),
                f"blue=vision lines  green=clustered  magenta=blocks")
    dump("e5_regions", rows)


COMMANDS = {
    "merge": cmd_merge,
    "zoom": cmd_zoom,
    "strips": cmd_strips,
    "sweep": cmd_sweep,
    "regions": cmd_regions,
}



# --------------------------------------------- E1b directional-guard probe

def cmd_merge_relaxed() -> None:
    """E1b — the ratio guard is symmetric; the failure it protects against is
    not. Run the SAME alignment with the count guard lifted and let the
    coverage floor (already in the merge) be the judge, then measure whether
    the boxes it produces actually sit on ink.
    """
    from fichero_server.media import geometry_merge
    from fichero_server.media.ocr_geometry import OCRGeometryLevel

    rows = {}
    for name, path, text in pages():
        if not text.strip():
            continue
        mask = cached_mask(path)
        measured = production(path)
        geo = to_geometry_result(measured, path)
        row = {"vision": box_metrics(path, measured.word_boxes, mask=mask)}
        outcome = geometry_merge.merge_reviewed_text_onto_geometry(
            text, geo, max_line_count_ratio=10_000.0)
        if outcome.refused or outcome.result is None:
            row["relaxed"] = {"refused": True, "reason": outcome.reason,
                              "lines_matched": outcome.lines_matched,
                              "lines_total": outcome.lines_total}
            rows[name] = row
            continue
        words = [b for b in outcome.result.boxes if b.level == OCRGeometryLevel.WORD]
        meas = [b for b in words
                if (b.metadata or {}).get("provenance") != geometry_merge.DERIVED]
        deriv = [b for b in words
                 if (b.metadata or {}).get("provenance") == geometry_merge.DERIVED]
        row["relaxed"] = {
            "refused": False,
            "coverage": round(outcome.coverage, 3),
            "lines_matched": outcome.lines_matched,
            "lines_total": outcome.lines_total,
            "measured_words": outcome.measured_words,
            "derived_words": outcome.derived_words,
            "all": box_metrics(path, words, mask=mask),
            "measured_only": box_metrics(path, meas, mask=mask) if meas else None,
            "derived_only": box_metrics(path, deriv, mask=mask) if deriv else None,
        }
        overlay(path,
                [(measured.word_boxes, (120, 120, 120, 130)),
                 (meas, (0, 180, 60, 235)), (deriv, (255, 140, 0, 235))],
                os.path.join(OUT, f"{name}__merge_relaxed.png"),
                f"relaxed  cov={outcome.coverage:.2f} meas={len(meas)} deriv={len(deriv)}")
        rows[name] = row
    dump("e1b_merge_relaxed", rows)


COMMANDS["merge_relaxed"] = cmd_merge_relaxed




# ------------------------------------- E4b request tuning THROUGH the ladder

class _ReqProxy:
    """A VNRecognizeTextRequest with the lab's tuning applied at birth, so a
    production escalation that builds its own request gets it too."""

    def __init__(self, real_cls, revision, correction):
        self._cls, self._rev, self._corr = real_cls, revision, correction

    def alloc(self):
        outer = self

        class _Alloc:
            def init(self):
                req = outer._cls.alloc().init()
                if outer._rev is not None:
                    req.setRevision_(outer._rev)
                if outer._corr is not None:
                    req.setUsesLanguageCorrection_(outer._corr)
                return req
        return _Alloc()

    def __getattr__(self, name):
        return getattr(self._cls, name)


class _VisionProxy:
    def __init__(self, real, revision, correction):
        self._real, self._rev, self._corr = real, revision, correction

    def __getattr__(self, name):
        if name == "VNRecognizeTextRequest":
            return _ReqProxy(self._real.VNRecognizeTextRequest, self._rev, self._corr)
        return getattr(self._real, name)


def production_tuned(image_path, *, revision=None, correction=None):
    """Production ladder with every request it builds carrying the tuning."""
    import Vision as _real
    sys.modules["Vision"] = _VisionProxy(_real, revision, correction)
    try:
        return production(image_path)
    finally:
        sys.modules["Vision"] = _real


def cmd_revision() -> None:
    """E4b — does the revision-1 / correction-off gain survive the escalations?"""
    rows = {}
    for name, path, _ in pages():
        mask = cached_mask(path)
        row = {}
        for tag, kw in (
            ("prod_default", {}),
            ("prod_rev1", dict(revision=1)),
            ("prod_nocorrect", dict(correction=False)),
            ("prod_rev1_nocorrect", dict(revision=1, correction=False)),
        ):
            t0 = time.time()
            res = production_tuned(path, **kw)
            m = box_metrics(path, res.word_boxes, mask=mask)
            m["lines"] = len(res.line_boxes)
            m["seconds"] = round(time.time() - t0, 1)
            row[tag] = m
        rows[name] = row
    dump("e4b_revision", rows)


COMMANDS["revision"] = cmd_revision




# ------------------------------- E4c revision as an ADDITIVE escalation pass

def merge_second_detector(base, extra):
    """Fold a second full-page pass into `base` using the production dedupe:
    a line the base already holds is dropped, a line it does not is added with
    its words. Additive by construction — nothing measured is discarded."""
    from fichero_server.workflows.tools import vision_base
    lines = list(base.line_boxes)
    words = list(base.word_boxes)
    added = 0
    for line in extra.line_boxes:
        if vision_base._is_duplicate_line(line, lines):
            continue
        lines.append(line)
        s, e = line.char_start, line.char_end
        if s is not None and e is not None:
            words.extend(w for w in extra.word_boxes
                         if w.char_start is not None and s <= w.char_start < e)
        added += 1
    if not added:
        return base, 0
    text, lines, words = vision_base._rebase_geometry_reading_order(lines, words)
    return vision_base.VisionOCRResult(
        text=text, line_boxes=lines, word_boxes=words), added


def cmd_second_detector() -> None:
    """E4c — keep revision 3 as the reader, add revision 1 (and .fast) purely
    as extra DETECTORS whose unseen lines are folded in."""
    rows = {}
    for name, path, _ in pages():
        mask = cached_mask(path)
        t0 = time.time()
        base = production(path)
        base_secs = round(time.time() - t0, 1)
        row = {"production": {**box_metrics(path, base.word_boxes, mask=mask),
                              "lines": len(base.line_boxes), "seconds": base_secs}}
        for tag, kw in (("plus_rev1", dict(revision=1)),
                        ("plus_fast", dict(level="fast"))):
            t0 = time.time()
            extra = raw_vision(path, **kw)
            merged, added = merge_second_detector(base, extra)
            m = box_metrics(path, merged.word_boxes, mask=mask)
            m["lines"] = len(merged.line_boxes)
            m["lines_added"] = added
            m["extra_seconds"] = round(time.time() - t0, 1)
            row[tag] = m
        rows[name] = row
    dump("e4c_second_detector", rows)


COMMANDS["second_detector"] = cmd_second_detector




# ==================================================================== E8 IoU
#
# The backfill's real question: given a page image and its text but NO boxes,
# how good are the boxes we produce? Ground truth is the problem — no Marshall
# page ships hand-drawn word rectangles. So the truth is MANUFACTURED honestly:
# Vision's own measured boxes ARE ground truth for Vision's own text. Hide some
# of them, hand the alignment the text, and measure what comes back against
# what was hidden.
#
# Two knobs, because the backfill faces two distinct hardships:
#   ablation — the transcript names words this page's OCR never boxed. That is
#              what interpolation has to cover.
#   corruption — the transcript disagrees with the OCR's reading, which is the
#              normal case on an old hand. That is what the alignment has to
#              survive.

def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    x0, y0 = max(ax, bx), max(ay, by)
    x1, y1 = min(ax + aw, bx + bw), min(ay + ah, by + bh)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    return inter / (aw * ah + bw * bh - inter)


def _corrupt(text: str, rate: float, seed: int = 7) -> str:
    """Substitute characters at `rate`, preserving length and whitespace — so a
    word's index and char span survive and the truth stays addressable."""
    import random
    rng = random.Random(seed)
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    out = []
    for ch in text:
        if ch.isalpha() and rng.random() < rate:
            out.append(rng.choice(alphabet))
        else:
            out.append(ch)
    return "".join(out)


def cmd_iou() -> None:
    """E8 — recovered-box IoU and word coverage under ablation + corruption."""
    import random
    from fichero_server.media import geometry_merge
    from fichero_server.media.ocr_geometry import (
        OCRGeometryLevel, OCRGeometryResult,
    )

    rows = {}
    for name, path, _ in pages():
        # Truth is ONE coherent pass, not the escalated page: the escalation
        # ladder merges lines from several crops, and a word's char span is
        # only guaranteed unique inside the pass that produced it. Pairing a
        # recovered box to its truth box needs an unambiguous key.
        base = raw_vision(path)
        truth_geo = to_geometry_result(base, path)
        if truth_geo is None or not truth_geo.boxes:
            continue
        truth_words = [b for b in truth_geo.boxes
                       if b.level == OCRGeometryLevel.WORD
                       and b.char_start is not None]
        truth_by_span = {b.char_start: b for b in truth_words}
        page_text = base.text
        row = {"truth_words": len(truth_words), "lines": len(base.line_boxes)}

        for ablate in (0.0, 0.25, 0.5):
            for corrupt in (0.0, 0.15, 0.30):
                rng = random.Random(11)
                kept = [b for b in truth_geo.boxes
                        if b.level != OCRGeometryLevel.WORD
                        or rng.random() >= ablate]
                measured = OCRGeometryResult(
                    text=truth_geo.text, provider=truth_geo.provider,
                    model=truth_geo.model, boxes=kept,
                )
                reviewed = _corrupt(page_text, corrupt)
                outcome = geometry_merge.merge_reviewed_text_onto_geometry(
                    reviewed, measured)
                tag = f"ablate{int(ablate*100)}_corrupt{int(corrupt*100)}"
                if outcome.refused or outcome.result is None:
                    row[tag] = {"refused": True, "reason": outcome.reason[:90]}
                    continue
                got = [b for b in outcome.result.boxes
                       if b.level == OCRGeometryLevel.WORD]
                # Corruption substitutes characters without changing length,
                # so a reviewed word's char span IS its truth word's span.
                pairs = [(g, truth_by_span[g.char_start]) for g in got
                         if g.char_start in truth_by_span]
                ious = [_iou(g.bbox, t.bbox) for g, t in pairs]
                meas = [i for (g, _), i in zip(pairs, ious)
                        if (g.metadata or {}).get("provenance") != geometry_merge.DERIVED]
                deriv = [i for (g, _), i in zip(pairs, ious)
                         if (g.metadata or {}).get("provenance") == geometry_merge.DERIVED]
                row[tag] = {
                    "refused": False,
                    "coverage": round(len(got) / max(len(truth_words), 1), 3),
                    "paired": len(pairs),
                    "mean_iou": round(float(np.mean(ious)), 3) if ious else None,
                    "iou_at_50": round(
                        sum(1 for i in ious if i >= 0.5) / len(ious), 3) if ious else None,
                    "measured_n": len(meas),
                    "measured_iou": round(float(np.mean(meas)), 3) if meas else None,
                    "derived_n": len(deriv),
                    "derived_iou": round(float(np.mean(deriv)), 3) if deriv else None,
                }
        rows[name] = row
    dump("e8_iou", rows)


COMMANDS["iou"] = cmd_iou




# ------------------------------------------------- E6 preprocess before OCR

def preprocess(image_path: str, kind: str) -> tuple[str, float]:
    """Write a preprocessed copy using the SERVER's own image ops, so a win
    here is a win we can ship by reusing code that already exists. Returns
    (path, deskew_angle_degrees)."""
    from fichero_server.media import image_ops
    from PIL import Image, ImageEnhance

    img = Image.open(image_path).convert("RGB")
    angle = 0.0
    if kind == "deskew":
        angle = image_ops.detect_deskew_angle(img)
        if abs(angle) > 0.1:
            img = img.rotate(angle, resample=Image.BICUBIC, expand=False,
                             fillcolor=(255, 255, 255))
    elif kind == "flatten":
        img = image_ops._flatten_illumination(img)
    elif kind == "contrast":
        img = ImageEnhance.Sharpness(
            ImageEnhance.Contrast(img).enhance(1.25)).enhance(1.1)
    elif kind == "deskew_flatten":
        angle = image_ops.detect_deskew_angle(img)
        if abs(angle) > 0.1:
            img = img.rotate(angle, resample=Image.BICUBIC, expand=False,
                             fillcolor=(255, 255, 255))
        img = image_ops._flatten_illumination(img)
    else:
        raise ValueError(kind)
    out = os.path.join(OUT, f"_pre_{kind}_{os.path.basename(image_path)}.png")
    img.save(out)
    return out, angle


def cmd_preprocess() -> None:
    """E6 — deskew / illumination flatten / contrast, through the ladder.

    Deskew ROTATES the page, so its boxes live in a rotated frame; the metric
    is computed against that frame's OWN ink mask. Comparing fractions across
    frames is legitimate (rotation preserves ink); comparing rectangles would
    not be, which is why only the fractions are reported for it.
    """
    rows = {}
    for name, path, _ in pages():
        mask = cached_mask(path)
        base = production(path)
        row = {"production": box_metrics(path, base.word_boxes, mask=mask)}
        for kind in ("deskew", "flatten", "contrast", "deskew_flatten"):
            t0 = time.time()
            try:
                prepped, angle = preprocess(path, kind)
                res = production(prepped)
                m = box_metrics(prepped, res.word_boxes)
            except Exception as exc:
                row[kind] = {"error": str(exc)[:120]}
                continue
            m["deskew_angle"] = round(angle, 3)
            m["seconds"] = round(time.time() - t0, 1)
            row[kind] = m
        rows[name] = row
    dump("e6_preprocess", rows)


# ------------------------------------------------------ E7 multi-scale merge

def _nms(boxes, iou_threshold: float = 0.5):
    """Keep the highest-confidence box in each cluster of overlapping ones.

    A union of passes double-draws every word the passes agree on, and a
    double-drawn box is not a better box — it is two claims about one word.
    """
    ordered = sorted(boxes, key=lambda b: -(b.confidence or 0.0))
    kept: list = []
    for box in ordered:
        if any(_iou(box.bbox, k.bbox) >= iou_threshold for k in kept):
            continue
        kept.append(box)
    return kept


def cmd_multiscale() -> None:
    """E7 — does the ensemble of full page + strips + zoom beat any one pass?"""
    from fichero_server.workflows.tools import vision_base

    rows = {}
    for name, path, _ in pages():
        mask = cached_mask(path)
        t0 = time.time()
        base = production(path)
        base_secs = round(time.time() - t0, 1)
        row = {"production": {**box_metrics(path, base.word_boxes, mask=mask),
                              "seconds": base_secs}}

        t0 = time.time()
        strips = strip_pass(path, count=3)
        strip_secs = round(time.time() - t0, 1)
        t0 = time.time()
        zoomed, _ = zoom_lines(path, base, factor=3.0)
        zoom_secs = round(time.time() - t0, 1)

        for tag, parts, secs in (
            ("page+strips", [base.word_boxes, strips.word_boxes],
             base_secs + strip_secs),
            ("page+zoom", [base.word_boxes, zoomed.word_boxes],
             base_secs + zoom_secs),
            ("page+strips+zoom",
             [base.word_boxes, strips.word_boxes, zoomed.word_boxes],
             base_secs + strip_secs + zoom_secs),
        ):
            union = [b for part in parts for b in part]
            kept = _nms(union)
            m = box_metrics(path, kept, mask=mask)
            m["union_before_nms"] = len(union)
            m["seconds"] = round(secs, 1)
            row[tag] = m
        rows[name] = row
    dump("e7_multiscale", rows)


COMMANDS["preprocess"] = cmd_preprocess
COMMANDS["multiscale"] = cmd_multiscale


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "merge"
    COMMANDS[what]()
