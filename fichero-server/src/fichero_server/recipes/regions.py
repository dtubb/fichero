"""A recipe's `find-regions` step, run by a YOLO layout model (`prep.yolo.regions-card`, #5525).

Each page image's regions are saved the way every region detector's are: one `regions` artifact per page, its
boxes the shared geometry, stamped with the model that found them (`provider="yolo"`), so the page model makes
them a machine's pass (never a person's) and the Layers list names YOLO.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable


def geometry(regions: list[Any], width: int, height: int, *, model: str) -> Any:
    """YOLO's regions as the shared geometry: one REGION box each, the model's own label kept as its `kind_raw`."""
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    boxes = [OCRGeometryBox(text="", bbox=list(r.rect), level=OCRGeometryLevel.REGION, confidence=r.confidence,
                            provider="yolo", model=model, source="yolo",
                            metadata={"kind_raw": r.kind_raw,
                                      "pixel_frame": {"width": width, "height": height}})
             for r in regions]
    return OCRGeometryResult(text="", provider="yolo", model=model, boxes=boxes, source="yolo",
                             metadata={"pixel_frame": {"width": width, "height": height}})


def find_regions(db: Any, documents: list[str], run_id: str, model: str,
                 stop: Callable[[], bool] | None = None) -> dict[str, int]:
    """Each page image's regions found and saved; the account: `pages` read, `regions` found, `no_image`
    (a PDF's page or a text file: nothing to look at). `stop` is asked before each page."""
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
        found = detect_regions(doc.path, model)
        asyncio.run(save_artifact(
            document_id=doc.id, file_path=doc.path, content="", data=None, library_path=library,
            llm_config=LLMConfig(provider="yolo", model=model), task_id=run_id, tool_config=TOOL_CONFIG,
            ocr_geometry=geometry(found, width, height, model=model)))
        account["pages"] += 1
        account["regions"] += len(found)
    return account
