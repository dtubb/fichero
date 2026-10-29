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


def crop_pages(db: Any, documents: list[str], run_id: str, stop: Callable[[], bool] | None = None, *,
               prepare: bool = False) -> dict[str, int]:
    """Each page image's paper found and recorded (and, with `prepare`, squared, flattened, turned and straightened: the
    Set Up step's operations, each a rendition; Find Regions asks only for the box); the account: `pages` looked at, `cropped` (a box written),
    `whole` (nothing to cut away, or not sure), `kept` (a person's box left alone), `blank` (no ink: hidden, with `prepare`), `no_image`."""
    from PIL import Image

    from fichero_server.actions.registry import ActionContext, registry
    import fichero_server.api.routes.document.documents  # noqa: F401  (registers document.update)
    import fichero_server.api.routes.ingest.image_editing  # noqa: F401  (registers image.mark_blank)
    from fichero_server.importers.ingest import _copy_to_library
    from fichero_server.media.blank_page import blank_verdict
    from fichero_server.media.find_page import find_page
    from fichero_server.media.upright import upright
    from fichero_server.models import Document, NodeRegion, Rendition, Segment
    from fichero_server.models.anchors import RegionConfidence
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    import tempfile

    library = Path(db.path).parent
    ctx = ActionContext(actor="page-crop", run_id=run_id, library_path=str(library), is_bootstrap=True)
    account = {"pages": 0, "cropped": 0, "whole": 0, "kept": 0, "no_image": 0, "blank": 0}
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
        if prepare and meta.get("blank") is None:
            # Hidden only when sure (`prep.blank-pages-marked`); unsure keeps the page and stores a proposal.
            has_lines = any(s.deleted_at is None for s in db.query(Segment, document_id=doc.id))
            verdict = blank_verdict(image, has_lines)
            if verdict == "blank":
                # Through the action layer: audited, and Undo restores the page (`image.mark_blank`).
                registry.invoke(db, "image.mark_blank", {"document_id": doc.id, "blank": True, "who": f"run {run_id}",
                                                        "reason": "no ink beyond its ruling"}, ctx)
                account["blank"] += 1
                continue
            if verdict == "unsure" and not meta.get("prep_proposals", {}).get("blank"):
                registry.invoke(db, "document.update", {"doc_id": doc.id, "update": {"metadata": {"prep_proposals": {
                    **meta.get("prep_proposals", {}),
                    "blank": {"reason": "very little ink beyond its ruling, or text lines found: kept, not hidden",
                              "by": f"run {run_id}"}}}}}, ctx)
                account["blank_proposed"] = account.get("blank_proposed", 0) + 1
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
        if prepare:
            _prepare(db, doc, image, found, run_id, library)
    return account


def _write(db: Any, doc: Any, role: str, picture: Any, run_id: str, library: Path, note: str, box: list[float],
           **transform: Any) -> None:
    """One more rendition of the page, replacing this step's own earlier one of the role, never another's."""
    import tempfile

    from fichero_server.importers.ingest import _copy_to_library
    from fichero_server.models import NodeRegion, Rendition
    from fichero_server.models.anchors import RegionConfidence

    with tempfile.TemporaryDirectory() as scratch:
        made = Path(scratch) / f"{doc.id}_{role}.png"
        picture.save(made)
        stored = _copy_to_library(made, library)
    for old in db.query(Rendition, document_id=doc.id):
        if old.role == role and old.producer_tool == PRODUCER:
            db.delete(old)
    db.save(Rendition(document_id=doc.id, role=role, path=str(stored), is_primary=False, pixel_width=picture.width,
                      pixel_height=picture.height, producer_tool=PRODUCER, producer_run_id=run_id, note=note,
                      transform=NodeRegion(rect=box, confidence=RegionConfidence.measured, **transform)))


def _prepare(db: Any, doc: Any, image: Any, found: Any, run_id: str, library: Path) -> None:
    """The operations in order, each fed by the one before and each writing a rendition only when it changed something:
    square (`prep.square.*`, the homography on its row), flatten (`prep.flatten.*`, the control points), turn by the text
    (`prep.turn-by-the-text`, the quarter turn and its reason), straighten (`prep.straighten-and-flatten`, the angle)."""
    from fichero_server.media.flatten_curve import flatten_curve
    from fichero_server.media.image_ops import apply_operation, auto_straighten_angle
    from fichero_server.media.square_page import quad_is_rectangular, square_page
    from fichero_server.media.turn_by_text import turn_by_text
    box = [round(v, 5) for v in found.box]
    base = image.crop(found.pixels(*image.size))
    if found.quad and not quad_is_rectangular(found.quad, image.size):
        base, homography = square_page(image, found.quad)
        _write(db, doc, "squared", base, run_id, library, "the page squared from its four corners", box,
               method="square", homography=homography, quad=[list(p) for p in found.quad])
    flat = flatten_curve(base)
    if flat is not None:
        base = flat[0]
        _write(db, doc, "flattened", base, run_id, library, "the page flattened toward its gutter", box,
               method="flatten", control_points=flat[1])
    turn = turn_by_text(base, db_path=str(db.path))
    if turn["angle"]:
        base = apply_operation(base, {"op": "rotate", "params": {"angle": turn["angle"]}})  # the editor's own turn
        _write(db, doc, "rotated", base, run_id, library, turn["reason"], box, method="turn", angle=turn["angle"])
    angle = auto_straighten_angle(base)
    if angle:
        base = apply_operation(base, {"op": "straighten", "params": {"angle": angle, "expand": True}})
        _write(db, doc, "deskewed", base, run_id, library, f"straightened {angle:.2f} degrees", box,
               method="straighten", angle=angle)
