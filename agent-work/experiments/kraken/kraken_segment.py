"""Stage A — run Kraken's neural segmenter over a page and dump line geometry.

Runs under the SCRATCH KRAKEN VENV, never the engine env. Kraken drags in
torch, lightning, coremltools, scikit-image and friends; the engine env stays
free of all of it for the same reason the MLX runtime is a separate venv. This
script therefore imports kraken and nothing from `fichero_server`.

Stage B (`overlay_report.py`) runs under the ENGINE venv, because Apple Vision
needs pyobjc and Fichero's own OCR helper. The two stages meet through the JSON
this one writes — which is also why every record here names the pixel frame it
was measured on (the bbox program's root-cause rule: a box that does not name
its frame is a box nobody can place).

Usage:
    /tmp/kraken-venv/bin/python kraken_segment.py OUT_DIR PAGE [PAGE ...]
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time


def _as_points(value) -> list[list[float]]:
    """Kraken hands back tuples/arrays; JSON wants plain nested lists."""
    if value is None:
        return []
    return [[float(x), float(y)] for x, y in value]


def _lines_from_segmentation(segmentation) -> list[dict[str, object]]:
    """Support both the object API (kraken >=5) and the legacy dict form."""
    raw_lines = getattr(segmentation, "lines", None)
    if raw_lines is None and isinstance(segmentation, dict):
        raw_lines = segmentation.get("lines", [])
    lines: list[dict[str, object]] = []
    for index, line in enumerate(raw_lines or []):
        if isinstance(line, dict):
            baseline, boundary, tags = line.get("baseline"), line.get("boundary"), line.get("tags")
        else:
            baseline = getattr(line, "baseline", None)
            boundary = getattr(line, "boundary", None)
            tags = getattr(line, "tags", None)
        lines.append(
            {
                "index": index,
                "baseline": _as_points(baseline),
                "polygon": _as_points(boundary),
                "tags": tags if isinstance(tags, (dict, list, str, type(None))) else str(tags),
            }
        )
    return lines


def _regions_from_segmentation(segmentation) -> dict[str, int]:
    raw = getattr(segmentation, "regions", None)
    if raw is None and isinstance(segmentation, dict):
        raw = segmentation.get("regions", {})
    if not raw:
        return {}
    return {str(key): len(value or []) for key, value in dict(raw).items()}


def main() -> int:
    out_dir = Path(sys.argv[1])
    pages = [Path(p) for p in sys.argv[2:]]
    out_dir.mkdir(parents=True, exist_ok=True)

    import_began = time.time()
    from PIL import Image
    import kraken
    from kraken import blla

    import_seconds = round(time.time() - import_began, 1)
    version = getattr(kraken, "__version__", "unknown")
    print(f"kraken {version}: import took {import_seconds}s", flush=True)

    for page in pages:
        image = Image.open(page)
        if image.mode != "RGB":
            image = image.convert("RGB")
        began = time.time()
        error = None
        try:
            # No `model=` argument: that is the DEFAULT blla segmenter, which is
            # what the evaluation is about. Passing a model would silently make
            # this a different experiment.
            segmentation = blla.segment(image)
            lines = _lines_from_segmentation(segmentation)
            regions = _regions_from_segmentation(segmentation)
        except Exception as exc:  # scratch harness: record it, never mask it
            lines, regions = [], {}
            error = f"{type(exc).__name__}: {exc}"
        seconds = round(time.time() - began, 1)

        payload = {
            "page": page.name,
            "source_path": str(page),
            # THE PIXEL FRAME. Kraken's coordinates are absolute pixels of this
            # exact image, so the frame travels with them or they mean nothing.
            "pixel_frame": {"width": image.width, "height": image.height},
            "kraken_version": version,
            "import_seconds": import_seconds,
            "seconds": seconds,
            "line_count": len(lines),
            "regions": regions,
            "error": error,
            "lines": lines,
        }
        target = out_dir / f"{page.stem}.kraken.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(
            f"{page.name}: {len(lines)} lines in {seconds}s "
            f"({image.width}x{image.height}) err={error} -> {target}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
