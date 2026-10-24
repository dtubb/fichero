"""A recipe's `find-regions` step, run by Kraken's built-in segmenter (the default, `prep.regions.open-default`,
#5668) or a YOLO layout model (`prep.yolo.regions-card`, #5525).

Each page image's regions are saved the way every region detector's are: one `regions` artifact per page, its
boxes the shared geometry, stamped with the model that found them (`provider="kraken"` or `"yolo"`), so the page
model makes them a machine's pass (never a person's) and the Layers list names who found them.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Callable

#: How often a page waiting on the throttle looks again (#5685).
WAIT_POLL_SECONDS = 5.0
#: What a run waits between pages while the person uses the Mac or a build runs: slower, not stopped.
SLOWER_YIELD_SECONDS = 1.0


def geometry(regions: list[Any], width: int, height: int, *, model: str, provider: str = "yolo",
             direction: str | None = None) -> Any:
    """Regions as the shared geometry: one REGION box each, the model's own label kept as its `kind_raw`."""
    from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryLevel, OCRGeometryResult

    # In reading order from position, as Kraken's regions are (`source.order.from-position`); a detector lists by score.
    from fichero_server.media.layout_order import reading_order

    rects = [list(r.rect) for r in regions]   # x, y, w, h as fractions of the page
    order = reading_order([(x, y, x + w, y + h) for x, y, w, h in rects], direction=direction,
                          kinds=[r.kind_raw for r in regions])
    regions = [regions[i] for i in order]
    boxes = [OCRGeometryBox(text="", bbox=list(r.rect), level=OCRGeometryLevel.REGION, confidence=r.confidence,
                            provider=provider, model=model, source=provider,
                            metadata={"kind_raw": r.kind_raw,
                                      "pixel_frame": {"width": width, "height": height}})
             for r in regions]
    return OCRGeometryResult(text="", provider=provider, model=model, boxes=boxes, source=provider,
                             metadata={"pixel_frame": {"width": width, "height": height}})


def progress_words(done: int, total: int, *, elapsed: float = 0.0, seconds_left: float | None = None) -> str:
    """How far a step is, for the run's line (#5689, #5685): "23 of 92 pages, about 12 min left", from the time it
    has taken so far or the time its own account says is left."""
    import math

    said = f"{done} of {total} pages"
    if seconds_left is None and 0 < done < total and elapsed > 0:
        seconds_left = elapsed / done * (total - done)
    if seconds_left and 0 < done < total:
        said += f", about {max(1, math.ceil(seconds_left / 60))} min left"
    return said



def find_regions(db: Any, documents: list[str], run_id: str, model: str,
                 stop: Callable[[], bool] | None = None, provider: str = "yolo",
                 say: Callable[[str], None] | None = None, person: bool | None = None,
                 created: list[str] | None = None) -> dict[str, int]:
    """Each page image's regions found and saved, by Kraken's segmenter (`provider="kraken"`) or a YOLO model; the
    account: `pages` read, `regions` found, `no_image` (a PDF's page or a text file: nothing to look at). `stop` is
    asked before each page. Before each page, while the throttle holds background work, it waits, and `say` is told
    why; between pages `say` is told the pages done and the time left (#5685, #5689, `activity.throttle.power-heat-memory`).
    A page cut from a PDF is rendered through the shared page-render seam and found on that image (#4892); the ids of the
    artifacts saved are appended to `created`, for a caller that tells the run which artifacts it made (#4890)."""
    from fichero_server.execution import jobs, throttle

    from PIL import Image

    from fichero_server.llm import LLMConfig
    from fichero_server.models import Document
    from fichero_server.workflows.tools.detect_regions import TOOL_CONFIG
    from fichero_server.workflows.tools.llm_base import save_artifact
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    library = str(Path(db.path).parent)
    account = {"pages": 0, "regions": 0, "no_image": 0}
    started = time.monotonic()
    if person is None:  # a try runs on a scratch copy that holds no row of the run: its caller says a person watches
        person = jobs.person_waits_on(db, run_id)
    for number, doc_id in enumerate(documents):
        # The throttle's one decision (#5819): memory and heat hold (and battery, for background work); a person's run
        # on battery, and background work under a build or while the Mac is used, goes on slower and says so.
        while (decision := throttle.decide(person)).action == "hold" and not (stop is not None and stop()):
            if say is not None:
                say(decision.reason)
            time.sleep(WAIT_POLL_SECONDS)
        if decision.action == "slow" and not (stop is not None and stop()):
            if say is not None:
                say(decision.words)
            time.sleep(SLOWER_YIELD_SECONDS)
        if stop is not None and stop():
            break
        if say is not None:
            # How far it is, with the time left once a page is done (#5689).
            say(f"Finding regions: {progress_words(number, len(documents), elapsed=time.monotonic() - started)}")
        doc = db.get(Document, doc_id)
        # The page's image as every step finds it: a copied page's stored path is inside the package (#5668).
        path = _resolve_abs_path(doc, library) if doc is not None else ""
        rendered, page_index = None, None
        if doc is not None and getattr(doc, "parent_id", None) and not doc.path:  # a page cut from a PDF has the PDF's path, not its own
            parent = db.get(Document, doc.parent_id)
            parent_path = _resolve_abs_path(parent, library) if parent is not None else ""
            if parent_path.lower().endswith(".pdf"):
                path = parent_path
        if path.lower().endswith(".pdf") and doc is not None and getattr(doc, "parent_id", None) and getattr(doc, "sequence", None):
            from fichero_server.workflows.tools.vision_base import _render_pdf_page_to_temp_png

            page_index = int(doc.sequence) - 1
            try:
                rendered = path = _render_pdf_page_to_temp_png(path, page_index)
            except (ValueError, OSError):  # the page is not in the file, or the render failed: nothing to look at
                account["no_image"] += 1
                continue
        try:  # the rendered temp file goes whatever happens to the page from here on
            try:
                with Image.open(path) as image:
                    width, height = image.size  # YOLO sees the file's raw pixels; Kraken's geometry says it is upright itself
            except (AttributeError, TypeError, OSError):
                account["no_image"] += 1
                continue
            found_geometry, regions_here = _find_on(db, doc, path, width, height, provider, model, run_id, library, page_index)
        finally:
            if rendered is not None:
                Path(rendered).unlink(missing_ok=True)
        artifact_id = asyncio.run(save_artifact(
            document_id=doc.id, file_path=doc.path, content="", data=None, library_path=library,
            llm_config=LLMConfig(provider=provider, model=model), task_id=run_id, tool_config=TOOL_CONFIG,
            ocr_geometry=found_geometry))
        if created is not None and isinstance(artifact_id, str):
            created.append(artifact_id)
        account["pages"] += 1
        account["regions"] += regions_here
    if say is not None and documents and not (stop is not None and stop()):
        say(f"Finding regions: {len(documents)} of {len(documents)} pages")
    return account


def _find_on(db: Any, doc: Any, path: str, width: int, height: int, provider: str, model: str, run_id: str,
             library: str, page_index: int | None) -> tuple[Any, int]:
    """One page image's geometry and how many regions it found: Kraken's segmenter (regions and lines in one pass, through the
    model lane) or a YOLO model. A page rendered from a PDF names its render in the geometry: the page and the resolution (#4892)."""
    from fichero_server.execution import jobs
    from fichero_server.llm.yolo_runtime import detect_regions

    if provider == "kraken":
        # Kraken's segmenter finds the regions and the lines in one pass: both are kept, so Find Lines and Read
        # read these lines instead of segmenting the page again (#5689).
        from fichero_server.llm.kraken_runtime import geometry_from_segmentation, segment_lines
        from fichero_server.media.ocr_geometry import OCRGeometryLevel

        from fichero_server.workflows.tools.vision_base import page_direction

        direction = page_direction(library, doc.id)
        # THROUGH the model lane, as every Kraken page is (Fable review #5): the lane sees the segmenter, counts it
        # for its one-heavy-model rule and its memory check, and an embed cannot load beside it unseen.
        segmented = jobs.run_on_lane_blocking(
            library, "find-regions", doc.id, model="kraken:blla", parent_id=run_id, run_id=run_id,
            fn=lambda path=path, direction=direction: segment_lines(path, **direction))
        found_geometry = geometry_from_segmentation(segmented, source_name=doc.name, direction=direction.get("direction"))
        regions_here = sum(1 for b in found_geometry.boxes if b.level is OCRGeometryLevel.REGION)
    else:
        from fichero_server.workflows.tools.vision_base import page_direction

        found = detect_regions(path, model)
        found_geometry = geometry(found, width, height, model=model, provider=provider,
                                  direction=page_direction(library, doc.id).get("direction"))
        regions_here = len(found)
    if page_index is not None:
        from fichero_server.workflows.tools.vision_base import _KRAKEN_PDF_RENDER_DPI

        found_geometry = found_geometry.model_copy(update={
            "metadata": {**found_geometry.metadata, "pdf_page_render": {"page_index": page_index, "dpi": _KRAKEN_PDF_RENDER_DPI}},
            "boxes": [box.model_copy(update={"page_index": page_index}) for box in found_geometry.boxes]})
    return found_geometry, regions_here
