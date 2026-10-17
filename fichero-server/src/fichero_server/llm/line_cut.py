"""The line cut and the answer parser, ONE implementation (`compute.job.one-runner`).

The line reader (this engine) and the reading runner (which runs on a cluster or Hugging Face with no engine) both use
these. The package ships this file beside the runner as `_fichero/line_cut.py`, so it imports only the standard library
and Pillow.
"""
from __future__ import annotations

import json
import re

from PIL import Image, ImageDraw, ImageStat

_MAX_CROP_WIDTH = 1600


def crop_line(page: Image.Image, polygon_px: list) -> Image.Image:
    """The line's polygon bounds, padded by a third of its height, at most 1,600 px wide, with everything
    outside the polygon (a sixth of its height beyond it, for ascenders) painted the crop's paper colour,
    so no neighbouring line shows (#5445): the picture the teacher reads. A student is trained on exactly
    this cut (`training.line_pairs`), so it learns the teacher's task and is asked it the same way."""
    xs = [p[0] for p in polygon_px]
    ys = [p[1] for p in polygon_px]
    height = max(ys) - min(ys)
    pad = height / 3
    box = tuple(round(v) for v in (max(0, min(xs) - pad), max(0, min(ys) - pad),
                                   min(page.width, max(xs) + pad), min(page.height, max(ys) + pad)))
    crop = page.crop(box).convert("RGB")
    mask = Image.new("L", crop.size, 0)
    shape = [(x - box[0], y - box[1]) for x, y in polygon_px]
    draw = ImageDraw.Draw(mask)
    draw.polygon(shape, fill=255)
    draw.line(shape + shape[:1], fill=255, width=max(1, round(pad)), joint="curve")
    crop = Image.composite(crop, Image.new("RGB", crop.size, tuple(ImageStat.Stat(crop).median)), mask)
    if crop.width > _MAX_CROP_WIDTH:
        crop = crop.resize((_MAX_CROP_WIDTH, round(crop.height * _MAX_CROP_WIDTH / crop.width)))
    return crop


def _says_null(text: str) -> bool:
    """The word null alone is a model's way of saying "no text", never the line's text (#5447)."""
    return text.strip().strip("\"'").strip().lower() == "null"


def parse_answer(raw: str, n: int) -> list[str | None] | None:
    """The model's JSON array of n readings, or None when it is not exactly that."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip())
    try:
        answer = json.loads(text)
    except ValueError:
        return None
    if not isinstance(answer, list) or len(answer) != n:
        return None
    if not all(a is None or isinstance(a, str) for a in answer):
        return None
    return [a.strip() if isinstance(a, str) and a.strip() and not _says_null(a) else None for a in answer]
