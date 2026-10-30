"""The page's current image: the ONE answer every step reads (#6296).

A page has its photograph (never changed) and what has been done to it: the edit chain a person built in Preview (crop,
straighten, split, enhance; `ImageEditChain`) and the renditions a run made (Prepare Images: crop, squared, rotated, deskewed,
prepared; `Rendition`). Every step that sends a page to a model (line read, whole-page read, review, Find Regions, Find Lines,
YOLO) reads `current_page_image`, in this order and no other:

1. the edit chain, applied to the photograph (a person's edit is the last word; Undo in Preview removes it and the next step
   reads what is under it);
2. else the newest rendition whose place on the photograph is known (a rendition whose frame cannot be worked out is passed over,
   never guessed);
3. else the photograph.

Geometry is stored as fractions of the page's UPRIGHT photograph (`media/upright.py`), whatever image a step read. So a step that
CUTS from the page (line crops, re-asks) carries its lines onto the image it reads (`WorkingLines.carried`), and a step that FINDS
on it (Kraken, YOLO, Apple Vision) carries what it found back (`PageImage.geometry_to_photograph`): `media/frame_map.py` has the
maths. A PDF page, a page by reference over IIIF, and a node with no file of its own have no current image here: the callers keep
the way they had of getting theirs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fichero_server.media.frame_map import (
    FrameMap,
    Unmappable,
    box_map,
    chain_map,
    exif_map,
    homography_map,
    turn_map,
)
from fichero_server.media.upright import FRAME_UPRIGHT

logger = logging.getLogger(__name__)

ORIGINAL, EDITED, RENDITION = "original", "edited", "rendition"

#: Roles that are some other picture (a thumbnail, a PDF page, a part cut for a region or a segment), never the page's own.
_NOT_THE_PAGE = frozenset({"original", "thumbnail", "pdf_page_render", "region-crop", "segment-picture"})
#: Roles written for a turn, whose angle is on the row.
_TURN_ROLES = frozenset({"rotated", "deskewed"})


@dataclass(frozen=True)
class PageImage:
    """The image to send for one page, and where the page's geometry lands on it."""

    path: str
    kind: str
    #: The photograph's own file: what a page with no edit sends, and what `to_image` is measured from.
    photograph: str
    #: Pixel map from the upright photograph to this image. None: this IS the photograph's pixels (and orientation tag), so a
    #: line's frame is read the old way (`open_in_frame`) and nothing is carried.
    to_image: FrameMap | None = None
    #: Why it is this image, in words, for a log line or a run's note.
    why: str = ""

    @property
    def is_original(self) -> bool:
        return self.kind == ORIGINAL

    def photograph_map(self) -> FrameMap | None:
        """This image's pixels back to the upright photograph's; None when they are the same."""
        return self.to_image.inverse() if self.to_image is not None else None

    def lines_map(self, lines_frame: str | None) -> FrameMap | None:
        """The map that carries lines measured on `lines_frame` (`media/upright.py`: upright, or None for the file's raw
        pixels) onto this image; None when they already fit."""
        if self.to_image is None:
            return None
        if lines_frame == FRAME_UPRIGHT:
            return self.to_image
        from PIL import Image

        with Image.open(self.photograph) as opened:
            raw = (float(opened.width), float(opened.height))
            orientation = int(opened.getexif().get(0x0112, 1) or 1)
        return exif_map(orientation, raw).then(self.to_image)

    def carry_lines(self, lines: list[dict[str, Any]], lines_frame: str | None) -> tuple[list[dict[str, Any]], str | None]:
        """Lines as a reader takes them (`{"id", "polygon", "baseline"}` in the pixels of the photograph in `lines_frame`,
        `WorkingLines.page_size`) carried onto this image, and the frame to open this image in (None: its pixels as they are)."""
        fmap = self.lines_map(lines_frame)
        if fmap is None:
            return lines, lines_frame
        return [{**ln, **{key: fmap.carry_pixels(ln[key]) for key in ("polygon", "baseline") if ln.get(key)}} for ln in lines], None

    def geometry_on_image(self, result: Any, lines_frame: str | None) -> Any:
        """The lines geometry a line reader reads (`working_lines.as_geometry`, pixels of the photograph) carried onto this
        image: outlines, baselines, boxes and the frame it says. As it came when the lines already fit this image."""
        fmap = self.lines_map(lines_frame)
        if fmap is None:
            return result
        boxes = []
        for box in result.boxes:
            meta = {k: v for k, v in box.metadata.items() if k != "frame"}
            for key in ("polygon_px", "baseline_px"):
                if meta.get(key):
                    meta[key] = fmap.carry_pixels(meta[key])
            meta["pixel_frame"] = {"width": fmap.dst[0], "height": fmap.dst[1]}
            boxes.append(box.model_copy(update={"bbox": _clamp_rect(fmap.carry_rect(box.bbox)), "metadata": meta}))
        meta = {k: v for k, v in result.metadata.items() if k != "frame"}
        meta["pixel_frame"] = {"width": fmap.dst[0], "height": fmap.dst[1]}
        return result.model_copy(update={"boxes": boxes, "metadata": meta})

    def geometry_to_photograph(self, result: Any) -> Any:
        """Boxes a finder measured on this image, as fractions of the upright photograph (`frame: "upright"`), the polygon and
        baseline in its pixels. The result is returned as it came when this image is the photograph's own."""
        back = self.photograph_map()
        if back is None or result is None or not getattr(result, "boxes", None):
            return result
        boxes = [_box_to_photograph(box, back) for box in result.boxes]
        meta = {**result.metadata, "pixel_frame": {"width": back.dst[0], "height": back.dst[1]}, "frame": FRAME_UPRIGHT}
        return result.model_copy(update={"boxes": boxes, "metadata": meta})

    def payload_to_photograph(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Kraken's raw answer (`segment_lines`) about this image, in the upright photograph's pixels."""
        back = self.photograph_map()
        if back is None:
            return payload
        return {**payload, "width": back.dst[0], "height": back.dst[1],
                "regions": [{**r, "polygon": back.carry_pixels(r.get("polygon") or [])} for r in payload.get("regions") or []],
                "lines": [{**ln, "polygon": back.carry_pixels(ln.get("polygon") or []),
                           "baseline": back.carry_pixels(ln.get("baseline") or [])} for ln in payload.get("lines") or []]}

    def rects_to_photograph(self, rects: list[Any], key: Any = lambda r: r.rect) -> list[list[float]]:
        """A layout model's fractional [x, y, w, h] boxes on this image as fractions of the upright photograph."""
        back = self.photograph_map()
        return [list(key(r)) if back is None else _clamp_rect(back.carry_rect(key(r))) for r in rects]


def _clamp_rect(rect: list[float]) -> list[float]:
    x0, y0 = max(0.0, min(1.0, rect[0])), max(0.0, min(1.0, rect[1]))
    x1, y1 = max(0.0, min(1.0, rect[0] + rect[2])), max(0.0, min(1.0, rect[1] + rect[3]))
    return [x0, y0, x1 - x0, y1 - y0]


def _box_to_photograph(box: Any, back: FrameMap) -> Any:
    meta = dict(box.metadata)
    polygon, baseline = meta.get("polygon_px"), meta.get("baseline_px")
    if polygon:
        meta["polygon_px"] = back.carry_pixels(polygon)
        xs, ys = [p[0] for p in meta["polygon_px"]], [p[1] for p in meta["polygon_px"]]
        rect = _clamp_rect([min(xs) / back.dst[0], min(ys) / back.dst[1],
                            (max(xs) - min(xs)) / back.dst[0], (max(ys) - min(ys)) / back.dst[1]])
    else:
        rect = _clamp_rect(back.carry_rect(box.bbox))
    if baseline:
        meta["baseline_px"] = back.carry_pixels(baseline)
    meta["pixel_frame"] = {"width": back.dst[0], "height": back.dst[1]}
    meta["frame"] = FRAME_UPRIGHT
    return box.model_copy(update={"bbox": rect, "metadata": meta})


def _size_of(path: Path) -> tuple[float, float]:
    from PIL import Image

    with Image.open(path) as image:
        return float(image.width), float(image.height)


def _upright_size_of(path: Path) -> tuple[float, float]:
    from PIL import Image

    from fichero_server.media.upright import upright_size

    with Image.open(path) as image:
        width, height = upright_size(image)
    return float(width), float(height)


def _absolute(library_root: Path, stored: str) -> Path:
    candidate = Path(stored)
    return candidate if candidate.is_absolute() else library_root / candidate


def _rendition_map(db: Any, rendition: Any, photograph: Path, photo_size: tuple[float, float], library_root: Path, _depth: int = 0) -> FrameMap | None:
    """The upright photograph's pixels to this rendition's; None when it is the photograph's own frame. Raises `Unmappable`
    for a rendition whose place on the page is not recorded (a flattened page, a turn with no angle, a missing parent)."""
    from fichero_server.models import Rendition

    if _depth > 8:
        raise Unmappable("renditions chain too deep to follow")
    region = rendition.transform
    path = _absolute(library_root, rendition.path)
    if region is None:
        return _same_frame_map(rendition, path, photograph, photo_size)
    own = ((float(rendition.pixel_width), float(rendition.pixel_height))
           if rendition.pixel_width and rendition.pixel_height else _size_of(path))
    extra = getattr(region, "model_extra", None) or {}

    def parent() -> FrameMap:
        from fichero_server.media.frame_map import identity

        parent_id = rendition.derived_from_rendition_id or region.rendition_id
        if not parent_id:
            return identity(photo_size)  # made from the photograph itself (`recipes/page_crop._write`: parent None)
        row = db.get(Rendition, parent_id)
        if row is None:
            raise Unmappable(f"{rendition.role} was made from a rendition that is not in the library")
        found = _rendition_map(db, row, photograph, photo_size, library_root, _depth + 1)
        return found if found is not None else identity(photo_size)

    role = rendition.role
    if role == "flattened":
        raise Unmappable("a flattened page's displacement is not a map the lines can follow")
    if role == "squared":
        return homography_map(photo_size, extra["homography"], own)
    if role in _TURN_ROLES:
        try:
            angle = float(extra["angle"])
        except (KeyError, TypeError, ValueError) as exc:
            raise Unmappable(f"{role} records no angle") from exc
        return parent().then(turn_map(parent().dst, angle, True)).with_size(own)
    if str(getattr(region.space, "value", region.space)) != "normalized":
        raise Unmappable(f"{role}'s place on the page is recorded in pixels of a size not known here")
    if region.rendition_id:
        raise Unmappable(f"{role} is cut from another rendition ({region.rendition_id})")
    return box_map(photo_size, region.rect, own)


#: A rendition that says it is the page's own frame but whose shape disagrees with the photograph's by more than this share was
#: re-framed by a tool that did not record it (a turn written with no transform): it is not followed.
_SAME_SHAPE = 0.01


def _same_frame_map(rendition: Any, path: Path, photograph: Path, photo_size: tuple[float, float]) -> FrameMap | None:
    """A rendition with no `transform` is the photograph's frame (`models.Rendition`): checked against its shape, since a
    workflow tool writes `rotated` or `enhanced` pictures with no transform at all. None when its pixels fit the photograph's
    as they are (same orientation tag); the identity on the upright page when it was saved upright (no tag, a photograph that
    has one); `Unmappable` for any other shape or tag."""
    from PIL import Image

    from fichero_server.media.frame_map import identity
    from fichero_server.media.upright import upright_size

    if rendition.frame_status == "unknown":
        raise Unmappable("the rendition's frame is marked unknown")
    with Image.open(path) as opened:
        own = upright_size(opened)
        own_tag = int(opened.getexif().get(0x0112, 1) or 1)
    with Image.open(photograph) as photo:
        photo_tag = int(photo.getexif().get(0x0112, 1) or 1)
    shape = photo_size[0] / photo_size[1]
    if abs(own[0] / own[1] - shape) > _SAME_SHAPE * shape:
        raise Unmappable(f"{rendition.role} has another shape than the photograph and records no transform")
    if own_tag == photo_tag:
        return None
    if own_tag == 1:
        return identity(photo_size).with_size((float(own[0]), float(own[1])))
    raise Unmappable(f"{rendition.role} carries another orientation than the photograph")


def _newest_rendition(db: Any, doc: Any, photograph: Path, library_root: Path) -> tuple[Any, FrameMap | None] | None:
    from fichero_server.models import Rendition

    rows = [r for r in db.query(Rendition, document_id=doc.id)
            if r.role not in _NOT_THE_PAGE and r.materialized and _absolute(library_root, r.path).is_file()]
    if not rows:
        return None
    photo_size = _upright_size_of(photograph)
    for row in sorted(rows, key=lambda r: (r.created_at, r.id), reverse=True):
        try:
            return row, _rendition_map(db, row, photograph, photo_size, library_root)
        except Unmappable as why:
            logger.info("page image: rendition %s (%s) of %s passed over: %s", row.id, row.role, doc.id, why)
    return None


def current_page_image(db: Any, doc: Any, *, library_root: Path | str | None = None) -> PageImage | None:
    """The page's current image (see the module doc), or None when the node has no image file of its own here."""
    from fichero_server.db.storage import edit_chain_operations, resolve_edited_source, resolve_source

    root = Path(library_root) if library_root is not None else Path(db.path).parent
    photograph = resolve_source(doc, library_root=root)
    if photograph is None:
        return None
    if photograph.suffix.lower() == ".pdf":
        return None  # a PDF page is rendered by the step that reads it, edits and all (`db/storage._generate_pdf_image`)

    operations, _version = edit_chain_operations(doc, db, page=1)
    if operations:
        edited = resolve_edited_source(doc, db, page=1)
        if edited is not None and edited != photograph:
            try:
                size = _upright_size_of(photograph)
                made = chain_map(size, operations, lambda: _upright_image(photograph)).with_size(_size_of(edited))
            except Unmappable as why:
                logger.warning("page image: the edits on %s have no known frame (%s): lines are read on the photograph", doc.id, why)
                return PageImage(str(photograph), ORIGINAL, str(photograph), why=f"edits not followed: {why}")
            return PageImage(str(edited), EDITED, str(photograph), made, why=f"{len(operations)} edit(s) applied")

    newest = _newest_rendition(db, doc, photograph, root)
    if newest is not None:
        row, made = newest
        return PageImage(str(_absolute(root, row.path)), RENDITION, str(photograph), made, why=f"the newest rendition ({row.role})")
    return PageImage(str(photograph), ORIGINAL, str(photograph), why="no edit, no rendition")


def _upright_image(path: Path) -> Any:
    from fichero_server.media.upright import open_in_frame

    return open_in_frame(path, FRAME_UPRIGHT)
