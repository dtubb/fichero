"""A recipe's `find-regions` step, run by Kraken's built-in segmenter (the default, `prep.regions.open-default`,
#5668) or a YOLO layout model (`prep.yolo.regions-card`, #5525).

Each page image's regions are saved the way every region detector's are: one `regions` artifact per page, its
boxes the shared geometry, stamped with the model that found them (`provider="kraken"` or `"yolo"`), so the page
model makes them a machine's pass (never a person's) and the Layers list names who found them.
"""

from __future__ import annotations

import asyncio
import tempfile
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



def page_crop(path: str, box: list[float] | None, out_dir: str) -> tuple[str, tuple[int, int], tuple[int, int]] | None:
    """The page's crop for the finder when the document has a `page_box` (`prep.page.detected-before-lines`, #6189): the
    upright image cut to the box (fractions `[x, y, w, h]` of the whole upright image), saved in `out_dir`. Returns
    `(crop path, (left, top) in pixels, (whole width, whole height))`, or None for no box, a box that is the whole image,
    or one too small to hold a page: the finder then sees the whole image, as before."""
    if not box or len(box) != 4:
        return None
    from PIL import Image

    from fichero_server.media.upright import upright

    x, y, w, h = (float(v) for v in box)
    if not (0 <= x and 0 <= y and w > 0.05 and h > 0.05 and x + w <= 1.000001 and y + h <= 1.000001) or w * h > 0.97:
        return None
    with Image.open(path) as opened:
        image = upright(opened)
        full = image.size
        left, top = round(x * full[0]), round(y * full[1])
        crop = image.crop((left, top, min(full[0], left + max(1, round(w * full[0]))),
                           min(full[1], top + max(1, round(h * full[1])))))
        out = str(Path(out_dir) / "page_crop.png")
        crop.save(out)
    return out, (left, top), full


def shift_payload(payload: dict[str, Any], left: int, top: int, width: int, height: int) -> dict[str, Any]:
    """Kraken's raw answer about a crop, put back in the whole upright image's pixels: every outline and baseline moved by
    the crop's corner, the frame the whole image's size."""
    def move(points: Any) -> list[list[float]]:
        return [[float(px) + left, float(py) + top] for px, py in points or []]

    return {**payload, "width": width, "height": height,
            "regions": [{**r, "polygon": move(r.get("polygon"))} for r in payload.get("regions") or []],
            "lines": [{**ln, "polygon": move(ln.get("polygon")), "baseline": move(ln.get("baseline"))}
                      for ln in payload.get("lines") or []]}


def find_regions(db: Any, documents: list[str], run_id: str, model: str,
                 stop: Callable[[], bool] | None = None, provider: str = "yolo",
                 say: Callable[[str], None] | None = None, person: bool | None = None,
                 created: list[str] | None = None, progress: bool = True) -> dict[str, int]:
    """Each page image's regions found and saved, by Kraken's segmenter (`provider="kraken"`) or a YOLO model; the
    account: `pages` read, `regions` found, `no_image` (a PDF's page or a text file: nothing to look at). `stop` is
    asked before each page. Before each page, while the throttle holds background work, it waits, and `say` is told
    why; between pages `say` is told the pages done and the time left (#5685, #5689, `activity.throttle.power-heat-memory`).
    A page cut from a PDF is rendered through the shared page-render seam and found on that image (#4892); the ids of the
    artifacts saved are appended to `created`, for a caller that tells the run which artifacts it made (#4890).
    `progress=False`: `say` hears only the throttle (a hold's words cleared when it lifts), never the pages done: a
    workflow's node runs this one page at a time, under a stage that is not Find Regions (Find Lines), and its count
    of 1 page said "Finding regions: 0 of 1 pages" there (dogfood 2026-10-27)."""
    from fichero_server.execution import jobs, throttle

    from PIL import Image

    from fichero_server.llm import LLMConfig
    from fichero_server.media.upright import upright_size
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
        held = False
        while (decision := throttle.decide(person)).action == "hold" and not (stop is not None and stop()):
            if say is not None:
                say(decision.reason)
            held = True
            time.sleep(WAIT_POLL_SECONDS)
        if held and say is not None and not progress:
            say("")
        if decision.action == "slow" and not (stop is not None and stop()):
            if say is not None:
                say(decision.words)
            time.sleep(SLOWER_YIELD_SECONDS)
        if stop is not None and stop():
            break
        if say is not None and progress:
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
        if doc is not None and rendered is None and "page_box" not in (doc.metadata or {}):
            doc = _find_the_page(db, doc, run_id)  # the paper first, so the finder reads only it (#6189)
        try:  # the rendered temp file goes whatever happens to the page from here on
            try:
                with Image.open(path) as image:
                    width, height = upright_size(image)  # both finders see the upright page (cv2 applies EXIF; Kraken is given it)
            except (AttributeError, TypeError, OSError):
                account["no_image"] += 1
                continue
            page_started = time.monotonic()
            with tempfile.TemporaryDirectory() as scratch:
                cut = page_crop(path, (doc.metadata or {}).get("page_box") if page_index is None else None, scratch)
                found_geometry, regions_here = _find_on(db, doc, cut[0] if cut else path, width, height, provider, model,
                                                        run_id, library, page_index, cut)
            if cut:  # said only when a page was cut to its paper: how many, the share of the image not read, the seconds
                box = doc.metadata["page_box"]
                account["cropped"] = account.get("cropped", 0) + 1
                account["area_saved"] = account.get("area_saved", 0.0) + 1 - float(box[2]) * float(box[3])
                account["seconds"] = account.get("seconds", 0.0) + time.monotonic() - page_started
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
    if say is not None and progress and documents and not (stop is not None and stop()):
        say(f"Finding regions: {len(documents)} of {len(documents)} pages")
    return account


def _find_the_page(db: Any, doc: Any, run_id: str) -> Any:
    """Record the page's box when the document has none and the classical finder is sure (`recipes.page_crop`); the document
    as it is now. A page that cannot be looked at, or that fills its frame, is read whole, as before."""
    from fichero_server.models import Document
    from fichero_server.recipes.page_crop import crop_pages

    try:
        crop_pages(db, [doc.id], run_id)
    except Exception:  # noqa: BLE001  (finding the page is an aid: its failure never fails Find Regions)
        return doc
    return db.get(Document, doc.id) or doc


def _find_on(db: Any, doc: Any, path: str, width: int, height: int, provider: str, model: str, run_id: str,
             library: str, page_index: int | None, cut: tuple[str, tuple[int, int], tuple[int, int]] | None = None
             ) -> tuple[Any, int]:
    """One page image's geometry and how many regions it found: Kraken's segmenter (regions and lines in one pass, through the
    model lane) or a YOLO model. A page rendered from a PDF names its render in the geometry: the page and the resolution (#4892)."""
    from PIL import Image

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
        if cut:  # the finder saw only the page's crop: its answer is put back in the whole image's pixels
            segmented = shift_payload(segmented, *cut[1], *cut[2])
        found_geometry = geometry_from_segmentation(segmented, source_name=doc.name, direction=direction.get("direction"))
        regions_here = sum(1 for b in found_geometry.boxes if b.level is OCRGeometryLevel.REGION)
    else:
        from fichero_server.workflows.tools.vision_base import page_direction

        found = detect_regions(path, model)
        if cut:  # the crop's fractions are put back as fractions of the whole image
            from dataclasses import replace

            (left, top), (full_w, full_h) = cut[1], cut[2]
            with Image.open(path) as crop:
                cw, ch = crop.size
            found = [replace(r, rect=((left + r.rect[0] * cw) / full_w, (top + r.rect[1] * ch) / full_h,
                                      r.rect[2] * cw / full_w, r.rect[3] * ch / full_h)) for r in found]
        found_geometry = geometry(found, width, height, model=model, provider=provider,
                                  direction=page_direction(library, doc.id).get("direction"))
        # YOLO reads the file through OpenCV, which applies the EXIF orientation: its boxes are on the upright page.
        from fichero_server.media.upright import FRAME_UPRIGHT, mark

        mark(found_geometry.boxes)
        found_geometry.metadata["frame"] = FRAME_UPRIGHT
        regions_here = len(found)
    if page_index is not None:
        from fichero_server.workflows.tools.vision_base import _KRAKEN_PDF_RENDER_DPI

        found_geometry = found_geometry.model_copy(update={
            "metadata": {**found_geometry.metadata, "pdf_page_render": {"page_index": page_index, "dpi": _KRAKEN_PDF_RENDER_DPI}},
            "boxes": [box.model_copy(update={"page_index": page_index}) for box in found_geometry.boxes]})
    return found_geometry, regions_here
