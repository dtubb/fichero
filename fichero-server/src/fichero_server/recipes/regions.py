"""A recipe's `find-regions` step, run by Kraken's built-in segmenter (the default, `prep.regions.open-default`,
#5668) or a YOLO layout model (`prep.yolo.regions-card`, #5525).

Each page image's regions are saved the way every region detector's are: one `regions` artifact per page, its
boxes the shared geometry, stamped with the model that found them (`provider="kraken"` or `"yolo"`), so the page
model makes them a machine's pass (never a person's) and the Layers list names who found them.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable


def geometry(regions: list[Any], width: int, height: int, *, model: str, provider: str = "yolo") -> Any:
    """Regions as the shared geometry: one REGION box each, the model's own label kept as its `kind_raw`."""
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    boxes = [OCRGeometryBox(text="", bbox=list(r.rect), level=OCRGeometryLevel.REGION, confidence=r.confidence,
                            provider=provider, model=model, source=provider,
                            metadata={"kind_raw": r.kind_raw,
                                      "pixel_frame": {"width": width, "height": height}})
             for r in regions]
    return OCRGeometryResult(text="", provider=provider, model=model, boxes=boxes, source=provider,
                             metadata={"pixel_frame": {"width": width, "height": height}})


def kraken_regions(path: str) -> list[Any]:
    """Kraken's built-in segmenter's regions on one page, each with the box around its outline and its type as the
    label (`blla` names them "text"); the lines it also finds are left to Find lines."""
    from types import SimpleNamespace

    from fichero_server.llm.kraken_runtime import segment_lines

    found = segment_lines(path)
    width, height = float(found["width"]), float(found["height"])
    out = []
    for region in found.get("regions") or []:
        xs = [float(x) for x, _ in region.get("polygon") or []]
        ys = [float(y) for _, y in region.get("polygon") or []]
        if xs and ys:  # normalised [x, y, w, h], as YOLO's
            out.append(SimpleNamespace(
                rect=[min(xs) / width, min(ys) / height, (max(xs) - min(xs)) / width, (max(ys) - min(ys)) / height],
                confidence=None, kind_raw=str(region.get("type") or "text")))
    return out


def find_regions(db: Any, documents: list[str], run_id: str, model: str,
                 stop: Callable[[], bool] | None = None, provider: str = "yolo") -> dict[str, int]:
    """Each page image's regions found and saved, by Kraken's segmenter (`provider="kraken"`) or a YOLO model; the
    account: `pages` read, `regions` found, `no_image` (a PDF's page or a text file: nothing to look at). `stop` is
    asked before each page."""
    from PIL import Image

    from fichero_server.llm import LLMConfig
    from fichero_server.llm.yolo_runtime import detect_regions
    from fichero_server.models import Document
    from fichero_server.workflows.tools.detect_regions import TOOL_CONFIG
    from fichero_server.workflows.tools.llm_base import save_artifact

    library = str(Path(db.path).parent)
    account = {"pages": 0, "regions": 0, "no_image": 0}
    for doc_id in documents:
        if stop is not None and stop():
            break
        doc = db.get(Document, doc_id)
        try:
            with Image.open(doc.path) as image:
                width, height = image.size
        except (AttributeError, TypeError, OSError):
            account["no_image"] += 1
            continue
        found = kraken_regions(doc.path) if provider == "kraken" else detect_regions(doc.path, model)
        asyncio.run(save_artifact(
            document_id=doc.id, file_path=doc.path, content="", data=None, library_path=library,
            llm_config=LLMConfig(provider=provider, model=model), task_id=run_id, tool_config=TOOL_CONFIG,
            ocr_geometry=geometry(found, width, height, model=model, provider=provider)))
        account["pages"] += 1
        account["regions"] += len(found)
    return account
