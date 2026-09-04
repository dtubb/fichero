"""Stage B — draw Kraken lines beside Apple Vision word boxes, and score them.

Runs under the ENGINE venv (needs pyobjc + Fichero's own OCR helper); stage A
runs under the scratch Kraken venv. They meet through stage A's JSON.

Apple Vision boxes come from `apple_vision_ocr_with_geometry`, the same helper
the product uses — not a reimplementation — so the comparison is against what
Fichero actually shows users today. Its boxes are normalized top-left
fractions, Kraken's are absolute pixels; both are resolved against the ONE
pixel frame recorded in stage A, and the frame is printed on the overlay so a
reader can never wonder which picture a box describes.

Usage:
    PYTHONPATH=fichero-server/src python overlay_report.py OUT_DIR [--skip-vision]
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time

from PIL import Image, ImageDraw

OUT_DIR = Path(sys.argv[1] if len(sys.argv) > 1 else "agent-work/experiments/kraken")
SKIP_VISION = "--skip-vision" in sys.argv
#: The bbox lab already measured Apple Vision on these exact pages, so the
#: experiment has a quantitative BEFORE rather than only pictures. On
#: 1913_p05 Vision returned 403 "lines" for 966 words; on 1923_p03_part1,
#: 163 lines for 174 words. Roughly one "line" per word is the fragmentation
#: a real segmenter is supposed to replace.
BASELINE_PATH = Path("agent-work/bbox-lab/out/metrics_baseline.json")


def _baseline() -> dict:
    if not BASELINE_PATH.exists():
        return {}
    try:
        return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _verdict_markdown(rows: list[dict]) -> str:
    """The one-page table Daniel decides from."""
    lines = [
        "# Kraken segmenter vs Apple Vision — verdict",
        "",
        "Kraken's `blla` segmenter finds LINES (polygon + baseline) and reads nothing.",
        "Apple Vision reads and returns word boxes. The baseline columns are the bbox",
        "lab's earlier Vision run on these same pages (`out/metrics_baseline.json`).",
        "",
        "| page | frame | Kraken lines | Kraken secs | old-Vision words | old-Vision secs | macOS26 doc lines | macOS26 doc words | macOS26 secs | baseline lines | baseline words | notes |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        base = row.get("baseline") or {}
        notes = []
        if row.get("kraken_error"):
            notes.append(f"kraken error: {row['kraken_error']}")
        if row.get("vision_error"):
            notes.append(f"vision: {row['vision_error']}")
        if row.get("documents_error"):
            notes.append(f"macOS26: {row['documents_error']}")
        lines.append(
            "| {page} | {frame} | {kl} | {ks} | {vw} | {vs} | {dl} | {dw} | {ds} | {bl} | {bw} | {notes} |".format(
                page=row["page"],
                frame=row["frame"],
                kl=row["kraken_lines"],
                ks=row["kraken_seconds"],
                vw=row["vision_words"],
                vs=row["vision_seconds"] if row["vision_seconds"] is not None else "-",
                dl=row.get("documents_lines") if row.get("documents_lines") is not None else "-",
                dw=row.get("documents_words") if row.get("documents_words") is not None else "-",
                ds=row.get("documents_seconds") if row.get("documents_seconds") is not None else "-",
                bl=base.get("lines", "-"),
                bw=base.get("words", "-"),
                notes="; ".join(notes) or "",
            )
        )
    lines += [
        "",
        "**Per-page, where each engine wins** — filled in from the overlays.",
        "Daniel's criterion is better OR DIFFERENT: an engine that catches what",
        "the others miss on degraded pages earns its place even if it loses on",
        "clean ones, so this section names complementary strengths rather than",
        "declaring one winner.",
        "",
        "Lines-a-human-sees and gross-failure notes (merged lines, phantom regions,",
        "swallowed margins) are filled in from the overlays, not computed — counting",
        "them automatically would be inventing a ground truth this experiment does",
        "not have.",
        "",
    ]
    return "\n".join(lines)

KRAKEN_POLYGON = (0, 122, 255)
KRAKEN_BASELINE = (255, 45, 85)
VISION_WORD = (52, 199, 89)
DOCUMENTS_LINE = (255, 149, 0)
LABEL_BG = (0, 0, 0)


def _panel(image: Image.Image, title: str, subtitle: str) -> Image.Image:
    """One page image with a caption bar naming what is drawn and on what."""
    panel = Image.new("RGB", (image.width, image.height + 44), (255, 255, 255))
    panel.paste(image, (0, 44))
    draw = ImageDraw.Draw(panel)
    draw.rectangle([0, 0, panel.width, 44], fill=LABEL_BG)
    draw.text((10, 6), title, fill=(255, 255, 255))
    draw.text((10, 24), subtitle, fill=(200, 200, 200))
    return panel


def _draw_kraken(image: Image.Image, record: dict) -> Image.Image:
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    for line in record.get("lines", []):
        polygon = [tuple(point) for point in line.get("polygon", [])]
        if len(polygon) >= 3:
            # width=3: a 1px outline on a 2000px page disappears entirely in the
            # contact sheet, which reads as "found nothing" rather than "drawn
            # too thin" — the exact misreading this experiment must not cause.
            draw.polygon(polygon, outline=KRAKEN_POLYGON, width=3)
        baseline = [tuple(point) for point in line.get("baseline", [])]
        if len(baseline) >= 2:
            draw.line(baseline, fill=KRAKEN_BASELINE, width=3)
    return canvas


def _draw_vision(image: Image.Image, boxes: list, frame: dict) -> Image.Image:
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    width, height = frame["width"], frame["height"]
    for box in boxes:
        # Normalized top-left fractions -> this frame's pixels. The engine
        # already flipped Vision's bottom-left origin at its own boundary.
        x, y, w, h = box
        draw.rectangle(
            [x * width, y * height, (x + w) * width, (y + h) * height],
            outline=VISION_WORD,
            width=2,
        )
    return canvas


def _draw_documents(image: Image.Image, record: dict, frame: dict) -> Image.Image:
    """macOS 26 RecognizeDocumentsRequest: normalized polygons, already flipped
    to top-left by the Swift harness at its own boundary."""
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    width, height = frame["width"], frame["height"]
    for line in record.get("lines", []):
        polygon = [(px * width, py * height) for px, py in line.get("polygon", [])]
        if len(polygon) >= 3:
            draw.polygon(polygon, outline=DOCUMENTS_LINE, width=3)
    return canvas


def _vision_boxes(source_path: str) -> tuple[list, float, str | None]:
    """Word boxes from Fichero's own Apple Vision path.

    Cached to JSON: re-rendering an overlay is free, but re-running Vision is
    inference, and inference is the scarce resource on this machine. The cache
    is keyed by page and holds the boxes, not the pictures.
    """
    cache = OUT_DIR / f"{Path(source_path).stem}.vision.json"
    if cache.exists():
        payload = json.loads(cache.read_text(encoding="utf-8"))
        return payload["boxes"], payload["seconds"], payload.get("error")

    from fichero_server.workflows.tools.vision_base import apple_vision_ocr_with_geometry

    began = time.time()
    try:
        result = apple_vision_ocr_with_geometry(source_path, language="es")
    except Exception as exc:
        return [], round(time.time() - began, 1), f"{type(exc).__name__}: {exc}"
    seconds = round(time.time() - began, 1)

    boxes = []
    for box in getattr(result, "word_boxes", None) or []:
        bbox = getattr(box, "bbox", None) or (box.get("bbox") if isinstance(box, dict) else None)
        if bbox and len(bbox) == 4:
            boxes.append([float(v) for v in bbox])
    cache.write_text(
        json.dumps({"boxes": boxes, "seconds": seconds, "error": None}, indent=2), encoding="utf-8"
    )
    return boxes, seconds, None


def main() -> int:
    records = sorted(OUT_DIR.glob("*.kraken.json"))
    if not records:
        print(f"no stage-A output in {OUT_DIR} — run kraken_segment.py first")
        return 1

    baseline = _baseline()
    rows = []
    for record_path in records:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        frame = record["pixel_frame"]
        source = Path(record["source_path"])
        if not source.exists():
            print(f"missing page image: {source}")
            continue
        page = Image.open(source).convert("RGB")

        kraken_panel = _panel(
            _draw_kraken(page, record),
            f"KRAKEN blla — {record['line_count']} lines in {record['seconds']}s",
            f"{source.name} · frame {frame['width']}x{frame['height']} · polygons blue, baselines red",
        )

        vision_boxes, vision_seconds, vision_error = ([], None, "skipped")
        if not SKIP_VISION:
            vision_boxes, vision_seconds, vision_error = _vision_boxes(str(source))
        vision_panel = _panel(
            _draw_vision(page, vision_boxes, frame),
            f"APPLE VISION — {len(vision_boxes)} word boxes"
            + (f" in {vision_seconds}s" if vision_seconds is not None else ""),
            f"{source.name} · frame {frame['width']}x{frame['height']} · words green"
            + (f" · {vision_error}" if vision_error else ""),
        )

        # Third arm: macOS 26's document-structure request, when its Swift
        # harness has run. Absent, the sheet is simply two panels — the arm is
        # never faked with an empty panel that could read as "found nothing".
        documents_path = OUT_DIR / f"{source.stem}.documents.json"
        documents = json.loads(documents_path.read_text(encoding="utf-8")) if documents_path.exists() else None
        panels = [kraken_panel, vision_panel]
        if documents is not None:
            panels.append(
                _panel(
                    _draw_documents(page, documents, frame),
                    f"macOS 26 RecognizeDocuments — {documents['line_count']} lines, "
                    f"{documents['word_count']} words in {documents['seconds']}s",
                    f"{source.name} · frame {frame['width']}x{frame['height']} · line regions orange"
                    + (f" · {documents['error']}" if documents.get("error") else ""),
                )
            )

        gap = 16
        side_by_side = Image.new(
            "RGB",
            (sum(p.width for p in panels) + gap * (len(panels) - 1), max(p.height for p in panels)),
            (255, 255, 255),
        )
        offset = 0
        for panel in panels:
            side_by_side.paste(panel, (offset, 0))
            offset += panel.width + gap
        # These pages are 2000-3100 px wide, so a side-by-side is ~6000 px —
        # unreadable as a whole and slow to open. Geometry is drawn at FULL
        # resolution (never scale coordinates), then the composed sheet is
        # thumbnailed for eyeballing; the full-res panels stay on disk for
        # anyone who wants to zoom into a single line.
        target = OUT_DIR / f"{source.stem}.overlay.png"
        kraken_panel.save(OUT_DIR / f"{source.stem}.kraken.png")
        vision_panel.save(OUT_DIR / f"{source.stem}.vision.png")
        contact_sheet = side_by_side.copy()
        contact_sheet.thumbnail((2600, 2600))
        contact_sheet.save(target)

        rows.append(
            {
                "page": source.name,
                "frame": f"{frame['width']}x{frame['height']}",
                "kraken_lines": record["line_count"],
                "kraken_seconds": record["seconds"],
                "kraken_error": record.get("error"),
                "vision_words": len(vision_boxes),
                "vision_seconds": vision_seconds,
                "vision_error": vision_error,
                "overlay": str(target),
                "documents_lines": (documents or {}).get("line_count"),
                "documents_words": (documents or {}).get("word_count"),
                "documents_seconds": (documents or {}).get("seconds"),
                "documents_error": (documents or {}).get("error"),
                "baseline": baseline.get(source.stem),
            }
        )
        print(f"wrote {target}", flush=True)

    (OUT_DIR / "verdict.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    (OUT_DIR / "verdict.md").write_text(_verdict_markdown(rows), encoding="utf-8")
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
