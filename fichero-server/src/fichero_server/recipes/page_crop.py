"""Page crop: find the paper on each page's image and record it (`image.enhance.page-crop-writes-page-box`, #6188, #6198).

Writes two things and changes no pixel of the original: the document's `page_box` and `page_region` metadata (the outline, its method and confidence) (`[x, y, w, h]`, fractions of
the UPRIGHT image: the box Leave Out and Find Regions read) and a `crop` rendition of the paper with its `transform`, so
the person can see it, switch to it, and move the box. A box a person drew or moved (`page_box_by: "person"`) is never
replaced by a finder's. The finder is `media.find_page` (no model), reached only through `media.enhance.page_crop.run`; a page it is not sure of keeps the whole frame.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

#: A finder box is written only when its paper fill is at least this (a ragged guess keeps the whole frame).
MIN_CONFIDENCE = 0.8
#: ...and covers at least this share of the image (a sliver is a stamp or a card, not the page).
MIN_SHARE = 0.15
PRODUCER = "page-crop"
#: Bumped when the finders, the blank rule or the operations change what a page comes out as, so a stamp from the older rules
#: no longer lets a re-run skip the page (`_stamp`).
PREP_VERSION = 3


def crop_pages(db: Any, documents: list[str], run_id: str, stop: Callable[[], bool] | None = None, *,
               prepare: bool = False, reuse: bool = False, signature: dict[str, Any] | None = None,
               operations: list[str] | None = None) -> dict[str, Any]:
    """Each page image's paper found and recorded (and, with `prepare`, squared, flattened, turned and straightened: the
    Set Up step's operations, each a rendition; Find Regions asks only for the box); the account: `pages` looked at, `cropped` (a box written),
    `whole` (nothing to cut away, or not sure), `kept` (a person's box left alone), `blank` (no ink: hidden, with `prepare`), `no_image`.
    With `prepare` and `reuse`, a page this step already prepared from the same file under the same rules (`_stamp`) is
    counted as `unchanged` and not found, turned or read again: a run that starts again costs only the pages that changed.
    `signature` is what changes THESE operations' output (`operations`: the page operations chosen; never the paper answer or Clarity,
    which change neither): it is part of the stamp, so a page prepared with other operations is prepared again
    (`wide.prepare.rerun-follows-the-answers`), and one prepared the same way is not, so its image signature stays and Read does not
    read it again. `operations` are the
    page operations to run (`crop`: find the paper, square, flatten, mark blanks; `straighten`: turn by the text, straighten),
    all of them when None; without `crop` the page itself is the base and no paper is looked for."""
    from PIL import Image

    from fichero_server.actions.registry import ActionContext, registry
    import fichero_server.api.routes.document.documents  # noqa: F401  (registers document.update)
    import fichero_server.api.routes.ingest.image_editing  # noqa: F401  (registers image.mark_blank)
    from fichero_server.media.blank_page import blank_verdict
    from fichero_server.media.enhance import page_crop as page_crop_step
    from fichero_server.media.upright import upright
    from fichero_server.models import Document
    from fichero_server.workflows.tools.sources import _resolve_abs_path

    library = Path(db.path).parent
    ctx = ActionContext(actor="page-crop", run_id=run_id, library_path=str(library), is_bootstrap=True)
    crop, straighten = (operations is None or "crop" in operations), (operations is None or "straighten" in operations)
    account = {"pages": 0, "cropped": 0, "whole": 0, "kept": 0, "no_image": 0, "blank": 0, "unchanged": 0}
    for doc_id in documents:
        if stop is not None and stop():
            break
        try:
            doc = db.get(Document, doc_id)
            meta = dict(doc.metadata or {}) if doc is not None else {}
            if doc is None:
                continue
            if meta.get("page_box_by") == "person":
                account["kept"] += 1
                continue
            path = _resolve_abs_path(doc, str(library))
            if prepare and reuse and _stamp_holds(meta, path, signature):
                account["unchanged"] += 1
                continue
            try:
                with Image.open(path) as opened:
                    image = upright(opened)
            except (OSError, AttributeError, TypeError):
                account["no_image"] += 1
                continue
            account["pages"] += 1
            # The one page-crop function (`media.enhance.page_crop`) finds the paper and says if it is sure; no crop: the page
            # itself is the base, no outline is looked for.
            decided = page_crop_step.run(image, page_crop_step.Params(min_confidence=MIN_CONFIDENCE, min_share=MIN_SHARE))[1] if crop else None
            found = decided["found"] if decided else None
            unsure = bool(decided and decided["unsure"])
            if prepare:  # below its confidence the finder proposes (`prep.unsure-becomes-a-proposal`); sure again, the proposal goes
                _propose(db, doc.id, "page_box", _page_box_proposal(found, run_id) if unsure else None, ctx)
            trusted = bool(decided and decided["trusted"])
            if prepare and crop and meta.get("blank") is None:
                # Hidden only when sure (`prep.blank-pages-marked`); unsure keeps the page and stores a proposal. The ink is a
                # share of the paper found (not the mount around it); a text read is the last word, asked only when the ink
                # alone would hide the page, because lines do not exist yet on a first run (Find Lines comes after).
                verdict = blank_verdict(image, lambda: _has_text(db, doc.id, image),
                                        list(found.box) if trusted else None)
                if verdict == "blank":
                    # Through the action layer: audited, and Undo restores the page (`image.mark_blank`).
                    registry.invoke(db, "image.mark_blank", {"document_id": doc.id, "blank": True, "who": f"run {run_id}",
                                                            "reason": "no ink beyond its ruling"}, ctx)
                    account["blank"] += 1
                    continue
                if verdict == "unsure" and not meta.get("prep_proposals", {}).get("blank"):
                    _merge_metadata(db, doc.id, lambda now: {"prep_proposals": {
                        **(now.get("prep_proposals") or {}),
                        "blank": {"reason": "very little ink beyond its ruling, or text lines found: kept, not hidden",
                                  "by": f"run {run_id}"}}}, ctx)
                    account["blank_proposed"] = account.get("blank_proposed", 0) + 1
            if not trusted:
                if prepare:
                    # A page already read, with no rendition of this step to read from, is not turned or straightened (a later whole-page read would pay again; Clarity can still change the image): turning it now
                    # would change the image its readings were made from and the next read would pay again (same input, same model).
                    from fichero_server.models import Rendition
                    from fichero_server.recipes.done import pages_with_readings
                    kept_as_read = doc.id in pages_with_readings(db, [doc.id]) and not any(
                        r.producer_tool == PRODUCER for r in db.query(Rendition, document_id=doc.id))
                    _clear(db, doc.id, everything=True)
                    # The page itself is the base: no crop, square or flatten (no paper was found), but turn and straighten
                    # still run, each a rendition only when it changed something (`wide.prepare.operations-run-on-every-page`).
                    if straighten and not kept_as_read:
                        _turn_and_straighten(db, doc, image, [0.0, 0.0, 1.0, 1.0], None, run_id, library, ctx)
                account["whole"] += 1
                _write_stamp(db, doc.id, path, prepare, ctx, signature)
                continue
            box = [round(v, 5) for v in found.box]
            _merge_metadata(db, doc.id, lambda now: {
                "page_box": box, "page_box_by": found.method, "page_box_confidence": found.confidence,
                "page_furniture": list(found.furniture),
                # The attribute of `segments-and-geometry.md`: the outline, how it was found, the frame it is measured in.
                "page_region": {"quad": [list(p) for p in found.quad], "box": box, "method": found.method,
                                "confidence": found.confidence, "frame": "upright",
                                "settings": {"min_confidence": MIN_CONFIDENCE, "min_share": MIN_SHARE}}}, ctx)
            left, top, right, bottom = found.pixels(*image.size)
            _clear(db, doc.id, everything=prepare)  # a re-run replaces every rendition of its own, so none is left stale
            crop_id = _write(db, doc, "crop", image.crop((left, top, right, bottom)), run_id, library,
                             f"the page found by the {found.method} finder", box, None, method=found.method)
            account["cropped"] += 1
            if prepare:
                _prepare(db, doc, image, found, run_id, library, crop_id, ctx, straighten=straighten)
            _write_stamp(db, doc.id, path, prepare, ctx, signature)
        except Exception as exc:  # noqa: BLE001 -- one page that fails is skipped and said; the others still go on
            logger.warning("page prep: %s skipped: %s", doc_id, exc)
            account["failed"] = account.get("failed", 0) + 1
            account.setdefault("failures", []).append({"page_id": doc_id, "why": str(exc)})
    return account


def _stamp_holds(meta: dict[str, Any], path: Any, signature: dict[str, Any] | None) -> bool:
    """The page's stored stamp still describes this preparation. A stamp from version 2 (no operations) holds for a page it cut,
    which this build would cut the same, when the operations asked for are the two it always ran; it does not hold for a page it
    left whole, which this build now turns and straightens (`wide.prepare.operations-run-on-every-page`)."""
    stored, now = meta.get("page_prep_stamp") or {}, _stamp(path, signature)
    if not stored or not now:
        return False
    if stored == now:
        return True
    legacy = stored.get("version") == 2 and "operations" not in stored
    return (legacy and meta.get("page_box") is not None and sorted((signature or {}).get("operations") or []) == ["crop", "straighten"]
            and (stored.get("size"), stored.get("mtime_ns")) == (now["size"], now["mtime_ns"]))


def _stamp(path: Any, signature: dict[str, Any] | None = None) -> dict[str, Any]:
    """What a finished preparation of a page was made from: the file's size and modified time, the rules' version and the page
    operations it ran (`signature`). A changed file, changed rules or other operations give another stamp, so the page is
    prepared again."""
    try:
        info = Path(path).stat()
    except OSError:
        return {}
    return {"size": info.st_size, "mtime_ns": info.st_mtime_ns, "version": PREP_VERSION, **(signature or {})}


def _write_stamp(db: Any, doc_id: str, path: Any, prepare: bool, ctx: Any, signature: dict[str, Any] | None = None) -> None:
    """Remember a page prepared to its end (a blank hide stops early and is never stamped: unhiding must prepare it)."""
    stamp = _stamp(path, signature)
    if prepare and stamp:
        _merge_metadata(db, doc_id, lambda now: {"page_prep_stamp": stamp}, ctx)


def _page_box_proposal(found: Any, run_id: str) -> dict[str, Any]:
    """The contour finder's unsure outline, kept on the page to be drawn as four dashed corners and listed in words."""
    share = found.box[2] * found.box[3]
    return {"quad": [list(p) for p in found.quad], "box": [round(v, 5) for v in found.box],
            "confidence": round(float(found.confidence), 3), "by": f"run {run_id}",
            "words": [f"the page edge is faint: {found.confidence:.0%} of the box is paper", f"the box found covers {share:.0%} of the picture"]}


def _propose(db: Any, doc_id: str, kind: str, proposal: dict[str, Any] | None, ctx: Any) -> None:
    """Store (or, with None, withdraw) the run's proposal of `kind` on the page (`metadata.prep_proposals.<kind>`); a kind a
    person has answered (`prep_answered`) is never proposed again."""
    from fichero_server.models import Document

    doc = db.get(Document, doc_id)
    meta = dict(doc.metadata or {}) if doc is not None else {}
    proposals = dict(meta.get("prep_proposals") or {})
    if proposal is not None and (meta.get("prep_answered") or {}).get(kind):
        return
    if proposal is None and kind not in proposals:
        return
    if proposal is None:
        proposals.pop(kind)
    else:
        proposals[kind] = proposal
    _merge_metadata(db, doc_id, lambda now: {"prep_proposals": proposals}, ctx)


def _merge_metadata(db: Any, doc_id: str, patch: Callable[[dict[str, Any]], dict[str, Any]], ctx: Any) -> None:
    """Write `patch(current metadata)` over the page's metadata, the rest kept: `document.update` replaces the whole object,
    so a bare write would drop `split_source_id`, `blank`, `prep_answered` and every other key (review 2026-10-30)."""
    from fichero_server.actions.registry import registry
    from fichero_server.models import Document

    doc = db.get(Document, doc_id)
    now = dict(doc.metadata or {}) if doc is not None else {}
    registry.invoke(db, "document.update", {"doc_id": doc_id, "update": {"metadata": {**now, **patch(now)}}}, ctx)


def _has_text(db: Any, doc_id: str, image: Any) -> bool:
    """Whether the page has a text line: one Find Lines already found, or one Apple Vision reads now (Vision absent: none)."""
    from fichero_server.media.turn_by_text import read_lines
    from fichero_server.models import Segment

    if any(s.deleted_at is None for s in db.query(Segment, document_id=doc_id)):
        return True
    return bool(read_lines(image, str(db.path)))


def _clear(db: Any, doc_id: str, *, everything: bool) -> None:
    """Delete this step's own renditions of a page, rows and files (another step's are never touched): all of them when the
    step re-prepares the page, else only the crop. A file still named by another row is kept."""
    from fichero_server.models import Rendition

    rows = db.query(Rendition, document_id=doc_id)
    mine = [r for r in rows if r.producer_tool == PRODUCER and (everything or r.role == "crop")]
    keep = {r.path for r in rows if r not in mine}
    for old in mine:
        db.delete(old)
        if old.path not in keep:
            Path(old.path).unlink(missing_ok=True)


def _write(db: Any, doc: Any, role: str, picture: Any, run_id: str, library: Path, note: str, box: list[float],
           parent_id: str | None, **transform: Any) -> str:
    """One more rendition of the page: the id of the rendition. `parent_id` is the rendition it was made from (None: the
    photograph), on the row and on its transform, so every shape traces back to the photograph through the chain."""
    import hashlib
    import io

    from fichero_server.models import NodeRegion, Rendition
    from fichero_server.models.anchors import RegionConfidence

    # Named by its bytes: the same pixels re-prepared give the same file name, so the image signature (the file name,
    # `media/current_image.PageImage.signature`) holds and Read does not read the page again (same input, same model: reuse).
    buffer = io.BytesIO()
    picture.save(buffer, format="PNG")
    data = buffer.getvalue()
    stored = library / "files" / doc.id[:2].lower() / f"{doc.id}_{role}_{hashlib.sha256(data).hexdigest()[:16]}.png"
    stored.parent.mkdir(parents=True, exist_ok=True)
    if not stored.exists() or stored.stat().st_size != len(data):
        partial = stored.with_suffix(".part")  # written whole or not at all: an interrupt leaves no half picture under the name
        partial.write_bytes(data)
        partial.replace(stored)
    row = Rendition(document_id=doc.id, role=role, path=str(stored), is_primary=False, pixel_width=picture.width,
                    pixel_height=picture.height, producer_tool=PRODUCER, producer_run_id=run_id, note=note,
                    derived_from_rendition_id=parent_id,
                    transform=NodeRegion(rect=box, rendition_id=parent_id, confidence=RegionConfidence.measured, **transform))
    db.save(row)
    return row.id


def _prepare(db: Any, doc: Any, image: Any, found: Any, run_id: str, library: Path, crop_id: str, ctx: Any, *,
             straighten: bool = True) -> None:
    """The operations in order, each fed by the one before and each writing a rendition only when it changed something:
    square (`prep.square.*`, the homography on its row), flatten (`prep.flatten.*`, the control points), turn by the text
    (`prep.turn-by-the-text`, the quarter turn and its reason), straighten (`prep.straighten-and-flatten`, the angle)."""
    from fichero_server.media.flatten_curve import flatten_curve
    from fichero_server.media.square_page import quad_is_rectangular, square_page
    box = [round(v, 5) for v in found.box]
    base = image.crop(found.pixels(*image.size))
    parent: str | None = crop_id  # the rendition `base` is: each operation's row names the one before it
    if found.quad and not quad_is_rectangular(found.quad, image.size):
        base, homography = square_page(image, found.quad)
        parent = _write(db, doc, "squared", base, run_id, library, "the page squared from its four corners", box, None,
                        method="square", homography=homography, quad=[list(p) for p in found.quad])
    flat = flatten_curve(base)
    if flat is not None:
        base = flat[0]
        parent = _write(db, doc, "flattened", base, run_id, library, "the page flattened toward its gutter", box, parent,
                        method="flatten", control_points=flat[1])
    if straighten:
        _turn_and_straighten(db, doc, base, box, parent, run_id, library, ctx)


def _turn_and_straighten(db: Any, doc: Any, base: Any, box: list[float], parent: str | None, run_id: str, library: Path,
                         ctx: Any) -> None:
    """Turn by the text, then straighten, on `base` (the page cut out, or the whole picture when no paper was found: `parent`
    None, the photograph's own frame). Each writes a rendition only when it changed something."""
    from fichero_server.media.image_ops import apply_operation, auto_straighten_angle
    from fichero_server.media.turn_by_text import turn_by_text
    turn = turn_by_text(base, db_path=str(db.path))
    disagree = turn["reason"].startswith("the lines do not agree")  # no turn is written, the page is listed to be looked at
    _propose(db, doc.id, "turn", {"reason": turn["reason"], "lines": turn["lines"], "by": f"run {run_id}",
                                  "words": [turn["reason"]]} if disagree else None, ctx)
    if turn["angle"]:
        base = apply_operation(base, {"op": "rotate", "params": {"angle": turn["angle"]}})  # the editor's own turn
        parent = _write(db, doc, "rotated", base, run_id, library, turn["reason"], box, parent, method="turn", angle=turn["angle"])
    angle = auto_straighten_angle(base)
    if angle:
        base = apply_operation(base, {"op": "straighten", "params": {"angle": angle, "expand": True}})
        _write(db, doc, "deskewed", base, run_id, library, f"straightened {angle:.2f} degrees", box, parent,
               method="straighten", angle=angle)
