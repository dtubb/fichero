"""Measure Find Regions with and without the page crop on real scans (#6189, `prep.page.kraken-time-saved-is-reported`).

    PYTHONPATH=src python scripts/measure_page_crop.py IMAGE [IMAGE ...]

For each image: Kraken's blla on the whole frame ("before") and on the page's crop ("after", `media.find_page` +
`recipes.regions.page_crop`/`shift_payload`). Prints seconds, lines on the ruler or card or off the page (false lines),
and lines lost (a line whose centre is on the paper in "before" with no line of "after" overlapping it). Reads the
files only; never writes a library. One model call per image per side (no reruns).
"""
from __future__ import annotations

import sys
import tempfile
import time

from PIL import Image

Image.MAX_IMAGE_PIXELS = None


def _centres(payload: dict) -> list[tuple[float, float]]:
    w, h = payload["width"], payload["height"]
    out = []
    for ln in payload["lines"]:
        xs, ys = [p[0] for p in ln["polygon"]], [p[1] for p in ln["polygon"]]
        out.append(((min(xs) + max(xs)) / 2 / w, (min(ys) + max(ys)) / 2 / h))
    return out


def main(paths: list[str]) -> None:
    from fichero_server.llm.kraken_runtime import segment_lines
    from fichero_server.media.find_page import find_page
    from fichero_server.recipes.regions import page_crop, shift_payload

    for path in paths:
        with Image.open(path) as im:
            found = find_page(im.convert("RGB"))
        if found is None:
            print(path, "no page found"); continue
        bx, by, bw, bh = found.box
        inside = lambda c: bx <= c[0] <= bx + bw and by <= c[1] <= by + bh  # noqa: E731
        t = time.monotonic(); before = segment_lines(path); t_before = time.monotonic() - t
        with tempfile.TemporaryDirectory() as scratch:
            cut = page_crop(path, list(found.box), scratch)
            t = time.monotonic(); raw = segment_lines(cut[0]); t_after = time.monotonic() - t
            after = shift_payload(raw, *cut[1], *cut[2])
        cb, ca = _centres(before), _centres(after)
        false_before = sum(1 for c in cb if not inside(c))
        lost = sum(1 for c in cb if inside(c) and not any(abs(c[0] - a[0]) < 0.03 and abs(c[1] - a[1]) < 0.01 for a in ca))
        print(f"{path.split('/')[-1]}: before {t_before:.1f}s {len(cb)} lines ({false_before} off the page) | "
              f"after {t_after:.1f}s {len(ca)} lines ({sum(1 for c in ca if not inside(c))} off) | "
              f"lost on paper {lost} | crop {bw * bh:.0%} of image", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
