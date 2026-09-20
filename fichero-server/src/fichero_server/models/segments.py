"""Source-model slice 1 — read-only segment shapes (spec: source-model.md,
"Slice 1 — one way to read a source's segments").

This module holds READ SHAPES ONLY: nothing here is ever saved. A segment
today lives inside an ``Artifact.ocr_geometry`` blob (one ``OCRGeometryBox``
per line/word/region, no id of its own); this module is the ONE place that
turns that blob into `source.one-store`'s promise — one shape, whether the
caller ends up reading the blob or, once slice 3 lands, real ``Segment``
rows. The route (``api/routes/document/segments.py``), the MCP tool and the
generated CLI command all resolve through the single mapping function below,
so nothing else ever re-derives a segment's id, anchor or pass.

Sits below ``fichero_server.models`` (imports it, is imported BY it) the
same way ``anchors.py`` does, and below ``media.ocr_geometry`` (imports
from it) -- ``media.ocr_geometry`` itself stays free of a `models` import
(see ``media/transcript_alignment_service.py``'s note on why), so the boxes
themselves know nothing about segments.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from fichero_server.core.timeutil import utc_now
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind

logger = logging.getLogger(__name__)


def _new_id() -> str:
    """Same minting as every other model (``uuid4().hex``) -- kept as a
    thin local wrapper so this module does not import the whole
    ``fichero_server.models`` package (see the module docstring: this file
    sits BELOW that package)."""
    import uuid

    return uuid.uuid4().hex

#: Prefix marking an id read out of today's blob storage rather than a real
#: ``Segment``/``Pass`` row. `source.seam.provisional-ids-refused`: a
#: provisional id must never be accepted back on a write.
LEGACY_ID_PREFIX = "legacy:"


class ProvisionalSegmentIdError(ValueError):
    """Raised when a write path is handed a provisional (``legacy:``) id.

    A provisional id names a POSITION in today's blob, not a lasting
    record -- accepting one into a claim, a mark or a reading would point at
    something that moves the moment the page is re-run. Typed so a caller
    can distinguish this from an ordinary "not found".
    """

    def __init__(self, id_value: str, *, what: str = "id") -> None:
        self.id_value = id_value
        self.what = what
        super().__init__(
            f"{what} {id_value!r} is provisional (read from today's stored "
            "geometry, not a real record) and cannot be written"
        )


def assert_not_provisional(id_value: str | None, *, what: str = "id") -> None:
    """Refuse a ``legacy:``-prefixed id on any write path.

    `source.seam.provisional-ids-refused`. Call this wherever a caller-
    supplied id could plausibly be one this seam minted -- today that means
    the ``artifact_id`` path parameter of the regions-edit route, which a
    caller could reach by (mistakenly) forwarding a ``PassRead.id`` instead
    of the real ``Artifact.id`` it is prefixed from.
    """
    if id_value is not None and id_value.startswith(LEGACY_ID_PREFIX):
        raise ProvisionalSegmentIdError(id_value, what=what)


def legacy_pass_id(artifact_id: str) -> str:
    return f"{LEGACY_ID_PREFIX}{artifact_id}"


def legacy_segment_id(artifact_id: str, box_index: int) -> str:
    return f"{LEGACY_ID_PREFIX}{artifact_id}:{box_index}"


class SegmentRead(BaseModel):
    """One segment, read either from today's blob or (later) a real row.

    The caller cannot tell which store it came from -- `source.one-store`.
    """

    id: str
    provisional: bool
    document_id: str
    pass_id: str
    #: The anchor's granularity word (region, line, word, ...).
    kind: str
    #: The producing model/tool's own label for this kind, if it differs
    #: from the tidied ``kind`` above (`source.segment.open-kinds`). ``None``
    #: until a tool records its own label -- slice 3 stores this as a
    #: column; nothing writes it yet, so it always reads ``None`` today.
    kind_raw: str | None = None
    #: Who made THIS segment -- set by the engine, never client-supplied,
    #: never defaulting to human. `human` when the BOX ITSELF proves a
    #: person drew it (see `_box_is_hand_drawn`); otherwise the owning
    #: pass's `provenance_kind`. The common case a hand-curated edit
    #: produces: one hand-added box inside an otherwise machine artifact,
    #: which `PassRead.provenance_kind` alone cannot see.
    provenance_kind: ProvenanceKind
    anchor: SourceAnchor
    #: Normalized ``[[x, y], ...]`` on the same image as ``anchor.rect``,
    #: only when the source box actually carried one (never invented).
    baseline: list[list[float]] | None = None
    text: str | None = None
    confidence: float | None = None
    source_artifact_id: str | None = None
    #: Position inside the owning artifact's ``ocr_geometry.boxes`` -- only
    #: meaningful (and only ever set) for a provisional segment.
    box_index: int | None = None
    #: Copied from ``OCRGeometryBox.page_index`` (slice 1b, #4919). The PDF
    #: page view filters boxes by it (``PDFPageWithToolbar.boxesForDisplayedPage``);
    #: without it every page of a multi-page PDF would show every page's boxes.
    page_index: int | None = None
    #: Anything that does not belong ON the anchor (which slices 3 and 6
    #: STORE, so it must stay clean): raw pixel values from a tool
    #: (``raw_polygon_px``, ``raw_baseline_px``, ``raw_pixel_frame``), and
    #: ``geometry_problem`` when the anchor could not hold this box's shape.
    metadata: dict[str, Any] = {}


class PassRead(BaseModel):
    """One pass, read either from today's blob (one per artifact) or
    (later) a real ``Pass`` row."""

    id: str
    provisional: bool
    document_id: str
    name: str
    provenance_kind: ProvenanceKind
    #: The ARTIFACT's provider (slice 1b, #4919) -- the app's
    #: `OCRGeometry.provider` is filled from this, never from ``name``
    #: (which holds the artifact's TYPE, a display name, not a provider).
    provider: str | None = None
    model: str | None = None
    run_id: str | None = None
    created_at: datetime | None = None
    #: The result's OWN text (``OCRGeometryResult.text``, slice 1b, #4919).
    #: A box's ``char_start``/``char_end`` index into THIS text -- never
    #: rebuild it by joining box texts, which is not the same string when a
    #: box was skipped, reordered, or the source had inter-box whitespace.
    text: str | None = None
    #: The app ranks passes by these without looking the artifact up
    #: (additive; slice 3's ``SegmentPass`` already has ``source_artifact_id``).
    source_artifact_id: str | None = None
    artifact_type: str | None = None


class SegmentListResponse(BaseModel):
    document_id: str
    passes: list[PassRead]
    segments: list[SegmentRead]


def _derive_pass_provenance_kind(*, provider: str | None, model: str | None) -> ProvenanceKind:
    """Legacy-row derivation, same shape as
    ``knowledge/_common.py::resolve_claim_provenance_kind`` (#4869): an
    ``Artifact`` has no ``provenance_kind`` field of its own to read, so this
    is the honest best-supported answer from what the row already carries,
    never a trusting default.
    """
    if provider == "user":
        return ProvenanceKind.human
    if provider or model:
        return ProvenanceKind.workflow
    return ProvenanceKind.unknown


def _box_is_hand_drawn(box: OCRGeometryBox) -> bool:
    """Exactly the app's own rule for the common hand-curation signal:
    ``promoteMarquees`` writes hand-drawn boxes INTO whatever machine
    artifact is showing, one box at a time, so the ARTIFACT's provider
    alone (`_derive_pass_provenance_kind`) cannot see it.

    Mirrors ``OCRGeometry.swift::OCRGeometryBox.isHandDrawn`` (``provider?
    .lowercased() == "user" || source?.lowercased() == "manual"``) and the
    engine's own write of that shape, ``artifacts.py::_edit_regions_impl``'s
    ADD branch (``_validated_box(..., provider="user", source="manual")``).
    Same OR, same two fields, on purpose: this is a read of what the write
    path already commits to, not a new rule.
    """
    provider = (box.provider or "").lower()
    source = (box.source or "").lower()
    return provider == "user" or source == "manual"


#: Tolerance for "on the edge of the normalized image", matching
#: `anchors.py::_EDGE_TOLERANCE`'s reasoning (float drift only).
_COORD_TOLERANCE = 1e-6


def _points_rejection_reason(points: list[list[float]], *, minimum: int) -> str | None:
    """Why these normalized points are not usable, or ``None`` if they are:
    finite, inside the image (with edge tolerance), at least ``minimum`` of
    them. Used for the baseline, which -- unlike the polygon -- has no
    validator downstream to catch a bad one."""
    if len(points) < minimum:
        return f"needs at least {minimum} points, got {len(points)}"
    for point in points:
        if len(point) != 2:
            return f"point must be [x, y], got {point!r}"
        for value in point:
            if value != value or value in (float("inf"), float("-inf")):  # NaN != NaN
                return f"non-finite coordinate {value!r}"
            if not (-_COORD_TOLERANCE <= value <= 1 + _COORD_TOLERANCE):
                return f"coordinate {value!r} outside the normalized image"
    return None


def _normalize_points(points: Any, *, width: float, height: float) -> list[list[float]] | None:
    try:
        return [[float(x) / width, float(y) / height] for x, y in points]
    except (TypeError, ValueError):
        return None


def _normalized_polygon(
    box: OCRGeometryBox,
) -> tuple[list[list[float]] | None, list[list[float]] | None, list[str]]:
    """``(polygon, baseline, problems)`` normalized to the box's own image,
    from a Kraken-style ``metadata["polygon_px"/"baseline_px"/"pixel_frame"]``.

    A box with no polygon returns ``(None, None, [])`` -- never a polygon
    invented from its rectangle (spec: "Kraken's polygon and baseline").
    But a polygon or baseline that IS present and cannot be used --
    ``pixel_frame`` missing/zero/malformed, or non-numeric points -- is
    dropped WITH a reason in ``problems``, never silently: "present but
    unusable" is reported, the same as a shape the anchor itself refuses.
    The polygon's own point-count/off-frame checks stay `_build_anchor`'s
    job (the anchor already validates them); the baseline has no such
    downstream check, so it is validated here with `_points_rejection_reason`.
    """
    polygon_px = box.metadata.get("polygon_px")
    baseline_px = box.metadata.get("baseline_px")
    if not polygon_px and not baseline_px:
        return None, None, []

    problems: list[str] = []
    frame = box.metadata.get("pixel_frame")
    width = frame.get("width") if isinstance(frame, dict) else None
    height = frame.get("height") if isinstance(frame, dict) else None
    if not width or not height:
        problems.append(f"pixel_frame missing or invalid: {frame!r}")
        return None, None, problems

    polygon = None
    if polygon_px:
        polygon = _normalize_points(polygon_px, width=width, height=height)
        if polygon is None:
            problems.append(f"polygon_px could not be normalized: {polygon_px!r}")

    baseline = None
    if baseline_px:
        normalized = _normalize_points(baseline_px, width=width, height=height)
        if normalized is None:
            problems.append(f"baseline_px could not be normalized: {baseline_px!r}")
        else:
            reason = _points_rejection_reason(normalized, minimum=2)
            if reason is not None:
                problems.append(f"baseline rejected: {reason}")
            else:
                baseline = normalized

    return polygon, baseline, problems


#: One ordered list of anchor-build attempts, most-complete first. Each
#: entry names exactly what it drops relative to the box's own fields, so
#: a report says precisely what was given up -- never just "shape
#: rejected". The character span is dropped before either shape (a bad
#: `char_end < char_start` must not also swallow a good rect or polygon),
#: then the polygon, then the rect, each alone and then together, down to
#: the bare anchor.
#:
#: This fixed order is only provably correct while dropping MORE never
#: makes a `SourceAnchor` LESS valid -- i.e. every field validates alone
#: (no cross-field rule can reject the full set while accepting a subset
#: that still includes the very field it complained about). True today:
#: `SourceAnchor._check_rect` validates `rect`, `polygon` and the char
#: span independently, nothing checks them against each other. If
#: `anchors.py` ever gains a cross-field rule (e.g. "the polygon must
#: contain the rect"), this list must be re-checked -- a later, more
#: complete attempt could then wrongly succeed before an earlier,
#: differently-broken one that a cross-field rule alone would catch.
_ANCHOR_ATTEMPTS: list[tuple[str, dict[str, Any]]] = [
    ("full", {}),
    ("character span dropped", {"char_start": None, "char_end": None}),
    ("polygon dropped", {"polygon": None}),
    ("polygon and character span dropped", {"polygon": None, "char_start": None, "char_end": None}),
    ("rect dropped", {"rect": None}),
    ("rect and character span dropped", {"rect": None, "char_start": None, "char_end": None}),
    ("rect and polygon dropped", {"rect": None, "polygon": None}),
    (
        "rect, polygon and character span dropped",
        {"rect": None, "polygon": None, "char_start": None, "char_end": None},
    ),
]


def _build_anchor(
    *,
    document_id: str,
    rendition_id: str | None,
    rect: list[float] | None,
    polygon: list[list[float]] | None,
    char_start: int | None,
    char_end: int | None,
    granularity: str,
) -> tuple[SourceAnchor, str | None]:
    """Build the segment's anchor, never letting one bad box fail the page.

    A box the anchor cannot hold (zero width/height; a polygon off its
    frame or with too few points; a character span with the end before the
    start) is still returned as a segment -- whatever the anchor cannot
    hold is left unset and the reason travels in the return value, never
    clamped or invented. One ordered list of attempts
    (`_ANCHOR_ATTEMPTS`), one reasons list: the first attempt that
    validates wins, and the reasons already collected say exactly what an
    earlier, more-complete attempt could not keep.
    """
    full = dict(
        document_id=document_id,
        rendition_id=rendition_id,
        rect=rect,
        polygon=polygon,
        char_start=char_start,
        char_end=char_end,
        granularity=granularity,
    )
    reasons: list[str] = []
    for label, drop in _ANCHOR_ATTEMPTS:
        try:
            anchor = SourceAnchor(**{**full, **drop})
        except ValidationError as exc:
            reasons.append(f"{label} attempt failed: {exc}")
            continue
        if not reasons:
            return anchor, None
        return anchor, f"kept only what validated ({label}): " + "; ".join(reasons)
    # Unreachable in practice: the bare anchor (document_id + rendition_id
    # only) has nothing left for a box's own fields to invalidate.
    return SourceAnchor(document_id=document_id, rendition_id=rendition_id), "; ".join(reasons)


def segment_from_box(
    *,
    document_id: str,
    artifact_id: str,
    box_index: int,
    box: OCRGeometryBox,
    rendition_id: str | None,
    pass_provenance_kind: ProvenanceKind,
) -> SegmentRead:
    """The one place an ``OCRGeometryBox`` becomes a ``SegmentRead``."""
    polygon, baseline, polygon_problems = _normalized_polygon(box)
    anchor, anchor_problem = _build_anchor(
        document_id=document_id,
        rendition_id=rendition_id,
        rect=list(box.bbox),
        polygon=polygon,
        char_start=box.char_start,
        char_end=box.char_end,
        granularity=str(box.level),
    )
    all_problems = polygon_problems + ([anchor_problem] if anchor_problem else [])

    metadata: dict[str, Any] = {}
    if "polygon_px" in box.metadata:
        metadata["raw_polygon_px"] = box.metadata.get("polygon_px")
    if "baseline_px" in box.metadata:
        metadata["raw_baseline_px"] = box.metadata.get("baseline_px")
    if "pixel_frame" in box.metadata:
        metadata["raw_pixel_frame"] = box.metadata.get("pixel_frame")
    if all_problems:
        geometry_problem = "; ".join(all_problems)
        metadata["geometry_problem"] = geometry_problem
        logger.debug(
            "segment %s box %d could not fill its geometry: %s",
            artifact_id, box_index, geometry_problem,
        )
    return SegmentRead(
        id=legacy_segment_id(artifact_id, box_index),
        provisional=True,
        document_id=document_id,
        pass_id=legacy_pass_id(artifact_id),
        kind=str(box.level),
        kind_raw=box.metadata.get("kind_raw"),
        provenance_kind=(
            ProvenanceKind.human if _box_is_hand_drawn(box) else pass_provenance_kind
        ),
        anchor=anchor,
        baseline=baseline,
        text=box.text or None,
        confidence=box.confidence,
        source_artifact_id=artifact_id,
        box_index=box_index,
        page_index=box.page_index,
        metadata=metadata,
    )


def segments_from_result(
    *,
    document_id: str,
    artifact_id: str,
    result: OCRGeometryResult,
    provider: str | None,
    model: str | None,
    run_id: str | None,
    created_at: datetime | None,
    artifact_type: str,
) -> tuple[PassRead, list[SegmentRead]]:
    """The ONE pure mapping function from an artifact's ``ocr_geometry``
    blob to a provisional pass and its segments. Every caller -- the route,
    the MCP tool (through the generated client) and the generated CLI
    command -- resolves through this function or the route that calls it,
    so none of them can drift from another (the hard-gate test pins this).
    """
    pass_provenance_kind = _derive_pass_provenance_kind(provider=provider, model=model)
    segments = [
        segment_from_box(
            document_id=document_id,
            artifact_id=artifact_id,
            box_index=index,
            box=box,
            rendition_id=result.rendition_id,
            pass_provenance_kind=pass_provenance_kind,
        )
        for index, box in enumerate(result.boxes)
    ]
    pass_read = PassRead(
        id=legacy_pass_id(artifact_id),
        provisional=True,
        document_id=document_id,
        name=artifact_type,
        provenance_kind=pass_provenance_kind,
        provider=provider,
        model=model,
        run_id=run_id,
        created_at=created_at,
        source_artifact_id=artifact_id,
        artifact_type=artifact_type,
        text=result.text or None,
    )
    return pass_read, segments


# ---------------------------------------------------------------------------
# Slice 3 -- Segment and SegmentPass records (#4921)
#
# Real, persisted rows: a pydantic model saved through Database.save() gets
# its table on first save (models ARE the schema). Additive only: no old
# table changes, nothing converts the ocr_geometry blob (slice 6's job).
# ---------------------------------------------------------------------------


class SegmentPass(BaseModel):
    """One named, authored pass over a source (`source.pass.named-authored`).

    Table name is set to ``segment_passes`` in ``Database._table_name``
    (the bare ``_ensure_table`` rule would give ``segmentpasss``, which
    reads badly -- same override CanvasLayout already gets).
    """

    id: str = Field(default_factory=_new_id)
    document_id: str
    #: Defaults to the run's or the tool's name; a display name, never a
    #: provider (`provider` below is that).
    name: str
    provenance_kind: ProvenanceKind
    actor: str | None = None
    provider: str | None = None
    model: str | None = None
    run_id: str | None = None
    source_artifact_id: str | None = None
    import_file: str | None = None
    import_checksum: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    #: Soft delete -- a pass is never removed (`segment.pass_delete`'s
    #: inverse, `segment.pass_restore`, clears this).
    deleted_at: datetime | None = None


class Segment(BaseModel):
    """One segment: a lasting id whose place is an anchor
    (`source.segment.lasting-id`, `source.builds-on-the-anchor`).

    ``bbox_x/y/w/h`` and ``tile`` are engine-derived from ``anchor`` and
    ``anchor`` alone is authoritative -- no params model accepts them
    (`source.segment.box-is-derived`).
    """

    id: str = Field(default_factory=_new_id)
    document_id: str
    #: Exactly one pass (`source.pass.never-overwrites`): a segment does not
    #: move between passes; a re-segmentation is a new pass, new segments.
    pass_id: str
    #: The ladder; membership only, no order (order is a named reading
    #: order, a later slice).
    parent_segment_id: str | None = None
    #: Open list (`source.segment.open-kinds`): the anchor's granularity
    #: words plus the non-text kinds; a project can add its own.
    kind: str
    #: A model's own label, kept beside the tidy `kind` above. None until a
    #: tool records one (mirrors `SegmentRead.kind_raw`'s note).
    kind_raw: str | None = None
    #: The place. Authoritative -- bbox_* below is derived FROM this, never
    #: the reverse.
    anchor: SourceAnchor
    #: Normalized to the anchor's image; None when the tool gave none.
    baseline: list[list[float]] | None = None
    #: Engine-written only, worked out from `anchor` in `_bbox_and_tile`.
    #: Range-query columns (`source.store.bounded-reads`): DuckDB's ART
    #: indexes are single-column, so "segments in this rectangle" is a
    #: `document_id` + `tile` lookup, not a JSON-anchor scan.
    bbox_x: float
    bbox_y: float
    bbox_w: float
    bbox_h: float
    #: Coarse 8x8 tile key over the image (`"x3y5"`); a segment crossing
    #: tiles takes the tile of its centre. Serves reads by area.
    tile: str
    #: Composite key `"<document_id>:<kind>"`, engine-written -- the
    #: single-column-index fallback the notes name for "one page's segments
    #: at one level": DuckDB's ART indexes are single-column, so a filter on
    #: BOTH `document_id` and `kind` cannot use one index for both at once.
    doc_kind: str
    #: Machine confidence of the SHAPE (not a reading), if the tool gave one.
    confidence: float | None = None
    is_furniture: bool = False
    provenance_kind: ProvenanceKind
    created_by: str | None = None
    #: Starts at 1; compare-and-set and stale-edit refusal arrive in slice 5.
    version: int = 1
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    #: Soft delete -- the row is never removed.
    deleted_at: datetime | None = None
    deleted_by: str | None = None
    #: Whatever an import or a tool gave that has no field here yet.
    metadata: dict[str, Any] = Field(default_factory=dict)


#: 8x8 grid over the normalized [0, 1] image -- coarse enough that a page's
#: segments land in a handful of tiles (cheap index), fine enough that "the
#: segments in this region" is not a full per-document scan.
_TILE_GRID = 8


def _tile_key(x: float, y: float, w: float, h: float) -> str:
    """The tile of a rect's CENTRE, clamped into the grid (a rect flush with
    the 1.0 edge would otherwise compute an out-of-range tile index)."""
    cx, cy = x + w / 2, y + h / 2
    tile_x = min(_TILE_GRID - 1, max(0, int(cx * _TILE_GRID)))
    tile_y = min(_TILE_GRID - 1, max(0, int(cy * _TILE_GRID)))
    return f"x{tile_x}y{tile_y}"


def bbox_and_tile_from_anchor(anchor: SourceAnchor) -> tuple[float, float, float, float, str]:
    """``(bbox_x, bbox_y, bbox_w, bbox_h, tile)`` derived from an anchor's
    rect, or its polygon's bounds when there is no rect
    (`source.segment.box-is-derived`). Raises when the anchor has neither --
    every accepted `segment.create`/`segment.create_many` anchor has at
    least one, so this is a defensive backstop, not a normal path."""
    if anchor.rect is not None:
        x, y, w, h = anchor.rect
    elif anchor.polygon:
        xs = [point[0] for point in anchor.polygon]
        ys = [point[1] for point in anchor.polygon]
        x, y = min(xs), min(ys)
        w, h = max(xs) - x, max(ys) - y
    else:
        raise ValueError("a segment's anchor needs a rect or a polygon to derive its box from")
    return x, y, w, h, _tile_key(x, y, w, h)


#: The size of one tile edge -- a segment bigger than this on either axis
#: cannot be reliably found by tile membership alone (see `tiles_for_rect`).
TILE_SIZE = 1.0 / _TILE_GRID


def tiles_for_rect(x: float, y: float, w: float, h: float) -> list[str]:
    """Every tile key a query rectangle overlaps (its own bounding box in
    tile-grid coordinates, inclusive) -- the engine detail behind "by area"
    (#4921 review: the public parameter is a rectangle, never a grid key)."""
    x0 = min(_TILE_GRID - 1, max(0, int(x * _TILE_GRID)))
    y0 = min(_TILE_GRID - 1, max(0, int(y * _TILE_GRID)))
    x1 = min(_TILE_GRID - 1, max(0, int((x + w) * _TILE_GRID)))
    y1 = min(_TILE_GRID - 1, max(0, int((y + h) * _TILE_GRID)))
    return [f"x{tx}y{ty}" for tx in range(x0, x1 + 1) for ty in range(y0, y1 + 1)]


def grow_rect_by_half_tile(x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
    """A query rectangle grown by half a tile on every side, clamped to the
    image (#4921 third look). A segment is filed under the tile of its
    CENTRE only, so one no larger than a tile can straddle a tile edge --
    its box reaching into the rectangle while its centre, and so its tile,
    sits just outside every tile the bare rectangle touches. Any such
    segment's centre is within half a tile of the rectangle on each axis,
    so its tile is one `tiles_for_rect` finds on the GROWN rectangle;
    anything bigger than a tile is already caught by the oversize clause
    in the candidate query, and `rects_intersect` removes the extras this
    growth admits."""
    half = TILE_SIZE / 2
    gx = max(0.0, x - half)
    gy = max(0.0, y - half)
    gx2 = min(1.0, x + w + half)
    gy2 = min(1.0, y + h + half)
    return gx, gy, gx2 - gx, gy2 - gy


def rects_intersect(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    """Standard axis-aligned-rectangle intersection test, ``(x, y, w, h)``
    each. "By area" means every segment whose BOX intersects the queried
    rectangle (#4921 review), not merely one that shares its tile."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def segment_read_from_row(row: Segment) -> SegmentRead:
    """The real-row twin of `segment_from_box` -- same `SegmentRead` shape,
    `provisional=False`. The seam (`api/routes/document/segments.py`) is the
    ONE place that resolves either this or the blob path, never both for the
    same pass."""
    return SegmentRead(
        id=row.id,
        provisional=False,
        document_id=row.document_id,
        pass_id=row.pass_id,
        kind=row.kind,
        kind_raw=row.kind_raw,
        provenance_kind=row.provenance_kind,
        anchor=row.anchor,
        baseline=row.baseline,
        text=None,  # readings on segments arrive in a later slice
        confidence=row.confidence,
        source_artifact_id=None,  # a real segment is not backed by one artifact
        box_index=None,
        page_index=None,  # not stored on Segment until its own slice
        metadata=dict(row.metadata),
    )


def pass_read_from_row(row: SegmentPass) -> PassRead:
    """The real-row twin of the pass half of `segments_from_result`."""
    return PassRead(
        id=row.id,
        provisional=False,
        document_id=row.document_id,
        name=row.name,
        provenance_kind=row.provenance_kind,
        provider=row.provider,
        model=row.model,
        run_id=row.run_id,
        created_at=row.created_at,
        source_artifact_id=row.source_artifact_id,
        artifact_type=None,
        text=None,  # readings on passes arrive in a later slice
    )
