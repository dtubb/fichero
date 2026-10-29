"""Page crop: find the paper on each page's image and record it (`image.enhance.page-crop-writes-page-box`, #6188, #6198).

Writes two things and changes no pixel of the original: the document's `page_box` and `page_region` metadata (the outline, its method and confidence) (`[x, y, w, h]`, fractions of
the UPRIGHT image: the box Leave Out and Find Regions read) and a `crop` rendition of the paper with its `transform`, so
the person can see it, switch to it, and move the box. A box a person drew or moved (`page_box_by: "person"`) is never
replaced by a finder's. The finder is `media.find_page` (no model); a page it is not sure of keeps the whole frame.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

#: A finder box is written only when its paper fill is at least this (a ragged guess keeps the whole frame).
MIN_CONFIDENCE = 0.8
#: ...and covers at least this share of the image (a sliver is a stamp or a card, not the page).
MIN_SHARE = 0.15
PRODUCER = "page-crop"


def crop_pages(db: Any, documents: list[str], run_id: str, stop: Callable[[], bool] | None = None) -> dict[str, int]:
    """Each page image's paper found and recorded; the account: `pages` looked at, `cropped` (a box written),
    `whole` (nothing to cut away, or not sure), `kept` (a person's box left alone), `no_image`."""
    from PIL import Image

    from fichero_server.actions.registry import ActionContext, registry
    import fichero_server.api.routes.document.documents  # noqa: F401  (registers document.update)
    from fichero_server.importers.ingest import _copy_to_library
    from fichero_server.media.find_page import find_page
    from fichero_server.media.upright import upright
    from fichero_server.models import Document, NodeRegion, Rendition
    from fichero_server.models.anchors import RegionConfidence
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    import tempfile

    library = Path(db.path).parent
    ctx = ActionContext(actor="page-crop", run_id=run_id, library_path=str(library), is_bootstrap=True)
    account = {"pages": 0, "cropped": 0, "whole": 0, "kept": 0, "no_image": 0}
    for doc_id in documents:
        if stop is not None and stop():
            break
        doc = db.get(Document, doc_id)
        meta = dict(doc.metadata or {}) if doc is not None else {}
        if doc is None:
            continue
        if meta.get("page_box_by") == "person":
            account["kept"] += 1
            continue
        path = _resolve_abs_path(doc, str(library))
        try:
            with Image.open(path) as opened:
                image = upright(opened)
        except (OSError, AttributeError, TypeError):
            account["no_image"] += 1
            continue
        account["pages"] += 1
        found = find_page(image)
        # The contour finder's confidence is its paper fill; Vision's was gated by the finder (0.5), so only the contour's is tested here.
        unsure = found is not None and found.method == "contour" and found.confidence < MIN_CONFIDENCE
        if found is None or unsure or found.box[2] * found.box[3] < MIN_SHARE:
            account["whole"] += 1
            continue
        box = [round(v, 5) for v in found.box]
        registry.invoke(db, "document.update", {"doc_id": doc.id, "update": {"metadata": {
            "page_box": box, "page_box_by": found.method, "page_box_confidence": found.confidence,
            "page_furniture": list(found.furniture),
            # The attribute of `segments-and-geometry.md`: the outline, how it was found, the frame it is measured in.
            "page_region": {"quad": [list(p) for p in found.quad], "box": box, "method": found.method,
                            "confidence": found.confidence, "frame": "upright",
                            "settings": {"min_confidence": MIN_CONFIDENCE, "min_share": MIN_SHARE}}}}}, ctx)
        left, top, right, bottom = found.pixels(*image.size)
        with tempfile.TemporaryDirectory() as scratch:
            crop_file = Path(scratch) / f"{Path(path).stem}_page.png"
            image.crop((left, top, right, bottom)).save(crop_file)
            stored = _copy_to_library(crop_file, library)
        for old in db.query(Rendition, document_id=doc.id):
            if old.role == "crop" and old.producer_tool == PRODUCER:  # a re-run replaces its own crop, never another's
                db.delete(old)
        db.save(Rendition(document_id=doc.id, role="crop", path=str(stored), is_primary=False,
                          pixel_width=right - left, pixel_height=bottom - top, producer_tool=PRODUCER,
                          producer_run_id=run_id, note=f"the page found by the {found.method} finder",
                          transform=NodeRegion(rect=box, confidence=RegionConfidence.measured, method=found.method)))
        account["cropped"] += 1
    return account
