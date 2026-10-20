#!/usr/bin/env python3
"""Does a different line crop rescue the lines Apple Vision came back empty on? (#5894, the bake-off's vision arm)

Vision only: no model, no network, no Kraken, no key. Reads the bake-off's `lines.json` and the page images, takes the lines
whose `--arm` (default `vision`) text is empty, and hands Apple Vision four crops of each:

  today        `line_cut.crop_line` as the line reader cuts it (padded a third of the line height, outside the polygon
               painted the crop's median colour, never upscaled)
  white        the same cut, the outside painted white
  up2          today's cut, upscaled 2x (Lanczos)
  up2_white    white, upscaled 2x

It counts how many of the empties each variant reads, and separately for the REAL-WORD empties (Kraken read text there
and the polygon is at least `WIDE_PX` wide: not a fragment). `today` should rescue about none (they were empty); that is the
check the probe is sound. Nothing is changed in `line_cut`: the cloud readers see `crop_line` and must go on seeing it. If one
variant rescues a quarter or more of the real-word empties the app change is specced then.

  python fichero-server/scripts/vision_crop_probe.py --pages DIR --lines out-free/lines.json --out DIR [--arm vision]

Run it in the engine's venv on the M4 (Quartz, Pillow); the text it reads back is a Vision reading, not ground truth.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

WIDE_PX = 120  # as in ab_kraken_cloud.py: a narrower polygon is a fragment
LANGUAGE = "es-ES"
RESCUE_SHARE = 0.25  # the bar for changing the app's crop
VARIANTS = ("today", "white", "up2", "up2_white")


def cut(page, polygon, *, white: bool, scale: int):
    """`crop_line`'s cut (bounds padded by a third of the height, the polygon and a stroke of that width kept, the rest filled),
    with the fill white or the crop's median colour, upscaled by `scale`. Written out here, not imported, because `crop_line`
    has no fill argument and is not to be changed for a probe."""
    from PIL import Image, ImageDraw, ImageStat

    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    pad = (max(ys) - min(ys)) / 3
    box = tuple(round(v) for v in (max(0, min(xs) - pad), max(0, min(ys) - pad),
                                   min(page.width, max(xs) + pad), min(page.height, max(ys) + pad)))
    crop = page.crop(box).convert("RGB")
    mask = Image.new("L", crop.size, 0)
    shape = [(x - box[0], y - box[1]) for x, y in polygon]
    draw = ImageDraw.Draw(mask)
    draw.polygon(shape, fill=255)
    draw.line(shape + shape[:1], fill=255, width=max(1, round(pad)), joint="curve")
    fill = (255, 255, 255) if white else tuple(ImageStat.Stat(crop).median)
    crop = Image.composite(crop, Image.new("RGB", crop.size, fill), mask)
    if scale > 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.LANCZOS)
    return crop


def variants(page, polygon) -> dict:
    return {"today": cut(page, polygon, white=False, scale=1), "white": cut(page, polygon, white=True, scale=1),
            "up2": cut(page, polygon, white=False, scale=2), "up2_white": cut(page, polygon, white=True, scale=2)}


def real_word(row: dict) -> bool:
    """Kraken read text there and the polygon is a line's width, not a fragment's."""
    xs = [p[0] for p in row["polygon"]]
    return bool((row.get("kraken") or "").strip()) and max(xs) - min(xs) >= WIDE_PX


def vision_text(image) -> str:
    """Apple Vision on one picture through the engine's own call, as the line reader makes it."""
    from fichero_server.workflows.tools.vision_base import apple_vision_ocr

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        path = Path(tmp.name)
    try:
        image.save(path, format="PNG")
        return (apple_vision_ocr(str(path), LANGUAGE) or "").strip()
    except Exception as exc:  # noqa: BLE001 -- a picture Vision refuses reads as empty, and the probe goes on
        return ""
    finally:
        path.unlink(missing_ok=True)


def probe(rows: list[dict], pages: Path, *, arm: str = "vision", ocr=vision_text) -> dict:
    """For each row whose `arm` text is empty: what each variant reads. `ocr(image) -> text` is replaceable for a test."""
    from PIL import Image

    empties = [r for r in rows if not (r.get(arm) or "").strip()]
    results = []
    cache: dict[str, Image.Image] = {}
    for row in empties:
        if row["page"] not in cache:
            cache[row["page"]] = Image.open(pages / row["page"])
            cache[row["page"]].load()
        read = {name: ocr(img) for name, img in variants(cache[row["page"]], row["polygon"]).items()}
        results.append({"page": row["page"], "id": row["id"], "kraken": row.get("kraken", ""), "real_word": real_word(row),
                        "read": read})
    real = [r for r in results if r["real_word"]]
    count = lambda group, name: sum(1 for r in group if r["read"][name])  # noqa: E731
    return {"arm": arm, "empties": len(results), "real_word_empties": len(real),
            "rescued": {n: count(results, n) for n in VARIANTS}, "rescued_real_word": {n: count(real, n) for n in VARIANTS},
            "bar": RESCUE_SHARE, "decision": {
                n: bool(real) and count(real, n) / len(real) >= RESCUE_SHARE for n in VARIANTS if n != "today"},
            "lines": results}


def report_md(r: dict) -> str:
    rows = ["| variant | empties it reads | real-word empties it reads |", "|---|---|---|"]
    for n in VARIANTS:
        rows.append(f"| {n} | {r['rescued'][n]} of {r['empties']} | {r['rescued_real_word'][n]} of {r['real_word_empties']} |")
    yes = [n for n, ok in r["decision"].items() if ok]
    verdict = (f"**{', '.join(yes)}** read at least {r['bar']:.0%} of the real-word empties: specify a crop change for Apple "
               "Vision only (the cloud readers keep `crop_line`)." if yes else
               f"No variant reads {r['bar']:.0%} of the real-word empties: leave `crop_line` as it is; the misses are Vision's "
               "own limit on this hand.")
    sample = [f"- {x['page']} #{x['id']} (Kraken: {x['kraken']!r}): " + ", ".join(
        f"{n}={t!r}" for n, t in x["read"].items() if t) for x in r["lines"] if any(x["read"].values())][:30]
    return ("\n".join([f"# Vision crop probe on {r['empties']} empty lines ({r['arm']} arm)\n",
                       f"Real word = Kraken read text and the polygon is at least {WIDE_PX} px wide. Texts below are Apple "
                       "Vision readings, **not ground truth**; `today` should read about none (they were empty).\n", *rows,
                       f"\n{verdict}\n", "## What was read", *(sample or ["(nothing)"])]) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages", type=Path, required=True)
    ap.add_argument("--lines", type=Path, required=True, help="the bake-off's lines.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--arm", default="vision")
    args = ap.parse_args(argv)
    rows = json.loads(args.lines.read_text(encoding="utf-8"))["lines"]
    result = probe(rows, args.pages, arm=args.arm)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "probe.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    (args.out / "report.md").write_text(report_md(result), encoding="utf-8")
    print(report_md(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
