"""A segment's picture, cut to its SHAPE (slice 7, #4925).

Spec: `build-notes-shapes-and-anchor.md`, "A segment's picture, cut to its
shape"; behaviour `source.segment.picture-by-shape`, and the pictures part of
`source.derived.recomputable`.

WHY A SHAPE AND NOT A RECTANGLE. A line of handwriting on a slanted page is a
parallelogram, and the rectangle around it holds two neighbours' descenders.
Hand that rectangle to a recogniser and it reads three lines at once. Cut to
the polygon and level along the baseline and the same picture is one line, flat
-- which is what a recogniser was trained on.

WHAT IT IS NOT. A picture is a WORKED-OUT thing, never a record: recomputable
from the segment and the image at any time, cached only so the same request
twice is not the same work twice, and thrown away the moment the segment
changes. It carries no meaning that the segment does not already carry.

IT EXTENDS `region_crops`, it does not duplicate it. That module renders a
NODE's band of its parent and persists it as a `Rendition`; this renders a
SEGMENT's shape and persists it the same way, reuses `_copy_to_library` for
storage, and reuses `RegionCropUnavailable` for "cannot be made honestly" --
because a second cropper is exactly how two answers to "where is this line"
come about.
"""

from __future__ import annotations

import hashlib
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fichero_server.db.storage import resolve_source
from fichero_server.media.region_crops import RegionCropUnavailable
from fichero_server.models import Document, Rendition
from fichero_server.models.anchors import (
    AnchorShapeKind,
    AnchorSpace,
    SourceAnchor,
    shapes_bound,
)
from fichero_server.models.segments import Segment, primary_live_segment_id, resolve_segment

logger = logging.getLogger(__name__)

#: Role for a rendition that is a segment's picture. Distinct from
#: `REGION_CROP_ROLE`: a region crop is a NODE's own pixels and is the thing a
#: tool is run on; this is a derived view of one segment and may be deleted at
#: any time without losing anything.
SEGMENT_PICTURE_ROLE = "segment-picture"

#: The largest edge a picture is rendered at, when `size` is not given. A line
#: strip for a recogniser is a few hundred pixels tall at most, and an
#: unbounded `size` on a request is an unbounded amount of work per call.
#: ponytail: one number, not a policy object — raise it if a model wants more.
DEFAULT_MAX_EDGE = 2048

#: The largest a caller may ask for. Beyond this a picture is not a view of a
#: line, it is a denial of service with an image attached.
SIZE_LIMIT = 8192


@dataclass(frozen=True, kw_only=True)
class SegmentPictureOptions:
    """The four options a picture is keyed by, validated once.

    A type rather than four parameters threaded through five functions, for one
    reason: the CACHE KEY is exactly this tuple, and it must be built in one
    place or a picture made with one set of options gets served for another.

    A frozen dataclass and not a hand-written class -- equality, repr and
    immutability come free, and there is no `__init__` to keep in step with
    the field list.
    """

    size: int | None = None
    margin: float = 0.0
    straighten: bool = False
    mask: bool = False

    def __post_init__(self) -> None:
        if self.size is not None and not 0 < self.size <= SIZE_LIMIT:
            raise ValueError(f"size must be in 1..{SIZE_LIMIT}, got {self.size}")
        if not 0.0 <= self.margin <= 1.0:
            raise ValueError(f"margin must be a fraction in 0..1, got {self.margin}")

    @property
    def key_part(self) -> str:
        return f"s{self.size or DEFAULT_MAX_EDGE}m{self.margin:g}t{int(self.straighten)}k{int(self.mask)}"


def picture_cache_key(segment: Segment, options: SegmentPictureOptions) -> str:
    """Segment id, segment VERSION, rendition id and the four options.

    The version is what makes "made again when the segment changes" automatic
    rather than a cache-invalidation chore: an edited segment has a new
    version, so it has a new key, so the old picture is simply never asked for
    again. Nothing has to remember to delete it.
    """
    raw = "|".join(
        [
            segment.id,
            str(segment.version),
            segment.anchor.rendition_id or "",
            options.key_part,
        ]
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def existing_picture(db: Any, document_id: str, cache_key: str) -> Rendition | None:
    """The picture already made for exactly this key, if any.

    Keyed on the note rather than the filename for the reason
    `existing_region_crop` gives: `_copy_to_library` renames on collision, so
    a path-keyed check never matches and every call stacks another copy.

    ponytail: a linear scan of one document's renditions, as
    `existing_region_crop` already does. The ceiling is real and worth naming:
    a page of 2,000 lines, pictured at two option sets, is 4,000 rows scanned
    per request. Index `(document_id, role, note)` when a training export
    actually asks for that many -- not before, because the scan is over ONE
    document and today a page has a handful of renditions.
    """
    for rendition in db.query(Rendition, document_id=document_id):
        if rendition.role == SEGMENT_PICTURE_ROLE and rendition.note == cache_key:
            return rendition
    return None


def _live_segment(db: Any, segment_id: str) -> Segment:
    """The segment this id means NOW, through slice 4's one resolver.

    A picture asked of a stale id is answered, because a read is exactly what
    forwarding is for -- but a picture of a segment whose every branch ended in
    a delete cannot be cut, because there is no shape left to cut to.
    """
    resolved = resolve_segment(db, segment_id)
    live_id = primary_live_segment_id(resolved)
    if live_id is None:
        raise RegionCropUnavailable(
            f"segment {segment_id} is deleted, so it has no shape to cut a picture to"
        )
    segment = db.get(Segment, live_id)
    if segment is None:
        raise RegionCropUnavailable(f"segment {live_id} has no row to read a shape from")
    return segment


def _source_image(db: Any, segment: Segment) -> Path:
    """The image the segment's anchor was measured ON -- never another one.

    This is the refusal `materialize_region_crop` already makes, for the same
    reason: cutting the original at fractions taken from a rotated or deskewed
    frame yields a plausible picture of the WRONG part of the page, and the
    transform that would resolve it is not recorded yet.
    """
    document = db.get(Document, segment.document_id)
    if document is None:
        raise RegionCropUnavailable(f"segment {segment.id}'s document is gone")

    named = segment.anchor.rendition_id
    if named:
        rendition = db.get(Rendition, named)
        if rendition is None or not rendition.path:
            raise RegionCropUnavailable(
                f"segment {segment.id} was measured on rendition {named}, which has "
                "no image here. Cutting the page instead would give a picture of "
                "the wrong place."
            )
        path = Path(rendition.path)
        if not path.is_file():
            raise RegionCropUnavailable(f"rendition image missing on disk: {path}")
        return path

    path = resolve_source(document, library_root=db.path.parent)
    if path is None or not path.is_file():
        raise RegionCropUnavailable(f"no source image for document {document.id}")
    return path


def _mask_polygon(segment: Segment) -> list[list[float]] | None:
    """The outline to keep, if the segment has one.

    Either the anchor's own `polygon` (how Kraken's outline is stored today,
    slice 6) or a polygon among its `shapes` (slice 7). One function so
    "does this segment have an outline" has a single answer.
    """
    anchor = segment.anchor
    if anchor.polygon:
        return anchor.polygon
    for shape in anchor.shapes or ():
        if shape.kind is AnchorShapeKind.polygon and shape.points:
            return shape.points
    return None


def _picture_box(anchor: SourceAnchor) -> list[float]:
    """The derived box: the shapes' bound when there are shapes, else the rect.

    Raises when there is neither. A time-only anchor has no box at all, and a
    picture of a stretch of a recording is not an image.
    """
    bound = shapes_bound(anchor.shapes)
    box = bound if bound is not None else anchor.rect
    if box is None:
        raise RegionCropUnavailable(
            "this segment names no area on any image, so it has no picture"
        )
    if box[2] <= 0 or box[3] <= 0:
        raise RegionCropUnavailable(
            f"this segment's area is empty ({box}), so there is nothing to cut"
        )
    return box


def _straightened(image, baseline: list[list[float]], page_width: int, page_height: int):
    """Rotate so the baseline is level (`source.segment.curved-baseline`).

    A straight rotation by the angle between the baseline's END POINTS, which
    is what makes the test assertable: after it, the ink runs along one row.
    A genuinely CURVED baseline needs resampling along its whole length, which
    is a recogniser-grade job and its own piece of work.
    ponytail: end-to-end angle; resample per-segment when a model needs it.

    The angle is worked out in the PAGE's pixels, not the crop's, because the
    baseline's numbers are fractions of the page. Using the crop's size here
    was wrong by the crop's aspect ratio -- a 26 degree tilt came out as 18 --
    and cropping is a translation, so the angle is the same in both frames.
    """
    (x0, y0), (xn, yn) = baseline[0], baseline[-1]
    import math

    degrees = math.degrees(math.atan2((yn - y0) * page_height, (xn - x0) * page_width))
    if abs(degrees) < 1e-9:
        return image
    # `expand` so the corners are not cut off, and a transparent fill so the
    # new corners are honestly empty rather than black pixels a model would
    # read as ink.
    return image.rotate(degrees, resample=3, expand=True, fillcolor=(0, 0, 0, 0))


def segment_picture(
    db: Any,
    segment_id: str,
    *,
    options: SegmentPictureOptions | None = None,
    library_path: str | Path | None = None,
) -> Rendition:
    """The segment's picture, cut to its shape, as a stored `Rendition`.

    Returns the EXISTING rendition when one was already made for this exact
    key. Raises `RegionCropUnavailable` when a picture is wanted and cannot be
    made honestly -- never a picture of the wrong place, and never a blank one.
    """
    options = options or SegmentPictureOptions()
    segment = _live_segment(db, segment_id)
    if segment.anchor.space is not AnchorSpace.normalized:
        raise RegionCropUnavailable(
            f"segment {segment.id}'s anchor is in {segment.anchor.space.value} space; "
            "a picture is cut from fractions of a named frame"
        )
    box = _picture_box(segment.anchor)

    cache_key = picture_cache_key(segment, options)
    cached = existing_picture(db, segment.document_id, cache_key)
    if cached is not None:
        return cached

    source = _source_image(db, segment)
    try:
        from PIL import Image, ImageDraw
    except ImportError as exc:  # pragma: no cover - environment
        raise RegionCropUnavailable(f"Pillow unavailable: {exc}") from exc

    polygon = _mask_polygon(segment) if options.mask else None
    baseline = segment.baseline if options.straighten else None

    try:
        with Image.open(source) as opened:
            image = opened.convert("RGBA")
            width, height = image.size

            if polygon:
                # Mask BEFORE cropping, in the page's own pixels, so the
                # outline's fractions mean what they were measured against.
                keep = Image.new("L", (width, height), 0)
                ImageDraw.Draw(keep).polygon(
                    [(point[0] * width, point[1] * height) for point in polygon], fill=255
                )
                image.putalpha(keep)

            x, y, w, h = box
            pad_x, pad_y = options.margin * w, options.margin * h
            left = max(0, int(round((x - pad_x) * width)))
            top = max(0, int(round((y - pad_y) * height)))
            right = min(width, int(round((x + w + pad_x) * width)))
            bottom = min(height, int(round((y + h + pad_y) * height)))
            if right <= left or bottom <= top:
                raise RegionCropUnavailable(
                    f"segment {segment.id}'s area is empty at the image's size "
                    f"({width}x{height}): {box}"
                )
            cropped = image.crop((left, top, right, bottom))

            if baseline and len(baseline) >= 2:
                cropped = _straightened(cropped, baseline, width, height)

            limit = options.size or DEFAULT_MAX_EDGE
            if max(cropped.size) > limit:
                cropped.thumbnail((limit, limit))
            picture_width, picture_height = cropped.size

            with tempfile.TemporaryDirectory() as staging:
                # Always PNG: a mask means transparency, and JPEG has none.
                staged = Path(staging) / f"{segment.id}_{cache_key}.png"
                cropped.save(staged)

                from fichero_server.importers.ingest import _copy_to_library

                package = Path(library_path) if library_path else db.path.parent
                stored = _copy_to_library(staged, Path(package) if package else None)
    except RegionCropUnavailable:
        raise
    except Exception as exc:
        raise RegionCropUnavailable(
            f"could not cut a picture of segment {segment.id}: {exc}"
        ) from exc

    rendition = Rendition(
        document_id=segment.document_id,
        role=SEGMENT_PICTURE_ROLE,
        path=str(stored),
        produced_from=str(source),
        # The frame this picture IS, recorded rather than implied — the same
        # rule `materialize_region_crop` follows, and the reason anything
        # measured on this picture can be brought back to the page.
        pixel_width=picture_width,
        pixel_height=picture_height,
        # Never primary: a derived view must not become what the reader opens.
        is_primary=False,
        # The cache key. `note` rather than a new column, because a derived
        # picture must not cost every library a migration.
        note=cache_key,
    )
    db.save(rendition)
    logger.info(
        "cut segment picture for %s: %sx%s from %s",
        segment.id, picture_width, picture_height, source.name,
    )
    return rendition
