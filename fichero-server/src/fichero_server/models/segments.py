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
import uuid
from enum import Enum
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from fichero_server.core.timeutil import utc_now
from fichero_server.media.ocr_geometry import (
    OCRGeometryBox,
    OCRGeometryResult,
    reading_order,
)
from fichero_server.models.anchors import SourceAnchor, shapes_bound
from fichero_server.models.knowledge import ProvenanceKind

logger = logging.getLogger(__name__)


def _new_id() -> str:
    """Same minting as every other model (``uuid4().hex``) -- kept as a
    thin local wrapper so this module does not import the whole
    ``fichero_server.models`` package (see the module docstring: this file
    sits BELOW that package)."""
    return uuid.uuid4().hex

#: Prefix marking an id read out of today's blob storage rather than a real
#: ``Segment``/``Pass`` row. `source.seam.provisional-ids-refused`: a
#: provisional id must never be accepted back on a write.
LEGACY_ID_PREFIX = "legacy:"

#: The same rule for a reading that still lives in an ``Artifact`` row
#: (source-model slice 8, #4934). A separate prefix rather than a longer
#: ``legacy:`` id because the two name different things -- a box's POSITION in
#: a geometry blob, and a whole artifact's TEXT -- and a caller that mixed
#: them up should get a refusal naming the right one.
LEGACY_READING_ID_PREFIX = "legacy-reading:"

#: Every prefix ``assert_not_provisional`` refuses. One tuple so adding a
#: third seam cannot forget to teach the refusal about it.
PROVISIONAL_ID_PREFIXES = (LEGACY_ID_PREFIX, LEGACY_READING_ID_PREFIX)


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
    if id_value is not None and id_value.startswith(PROVISIONAL_ID_PREFIXES):
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


def _short_validation_reason(exc: ValidationError) -> str:
    """Each error's own message, first line only (#4955: pydantic's ``str()``
    echoes the WHOLE rejected input dict plus a help URL per error -- 700 to
    2,200 characters for one box -- and a page with a few thousand degenerate
    boxes would carry that in every segment's ``metadata``)."""
    return "; ".join(err["msg"].splitlines()[0] for err in exc.errors())


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
            reasons.append(f"{label} attempt failed: {_short_validation_reason(exc)}")
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
    elif (bound := shapes_bound(anchor.shapes)) is not None:
        # Slice 7 (#4925): a lone point, or a level path, has a real place and
        # no extent, so the anchor leaves `rect` unset -- `rect` promises a
        # drawable rectangle. `bbox_*` is engine-written and makes no such
        # promise, so it takes the zero-size box AT the point, which is what
        # lets a point be found by an area read like anything else.
        x, y, w, h = bound
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


def words_for_row(
    source_block: OCRGeometryResult | None, metadata: dict[str, Any]
) -> str | None:
    """The words a converted row shows, from the kept block.

    Two shapes. An ordinary converted box has one `box_index` and shows
    that box's text. A COMBINED one has `member_box_indexes` -- every box
    it absorbed -- and shows their texts joined in reading order, exactly
    as today's combine joins them, using the one `reading_order` rule they
    both share. Computed at read; nothing new is stored, which is what
    keeps the block the single home of the words until slice 8.

    Combining an already combined segment joins the union of both lists,
    because the merge carries the members forward.
    """
    if source_block is None:
        return None
    members = metadata.get("member_box_indexes")
    if isinstance(members, list) and members:
        pairs = []
        for index in members:
            box = _box_at(source_block, index)
            if box is not None:
                pairs.append((index, box))
        if not pairs:
            return None
        # Newline-joined, as today: regions read as passages, and a newline
        # keeps two lines' worth of text from running together.
        return "\n".join(box.text for _, box in reading_order(pairs) if box.text) or None
    box = _box_at(source_block, metadata.get("box_index"))
    return (box.text or None) if box is not None else None


def _box_at(source_block: OCRGeometryResult | None, box_index: Any) -> OCRGeometryBox | None:
    """The box a converted row came from, or ``None``.

    Tolerant on purpose: a row's `metadata["box_index"]` is data that has
    been through a database, and the block may be gone entirely (an
    artifact is hard-deleted -- `Artifact` has no soft-delete field). Every
    caller must read "no box" as "no text", never as an error: a page must
    not stop rendering because one row lost its source."""
    if source_block is None or not isinstance(box_index, int) or isinstance(box_index, bool):
        return None
    if 0 <= box_index < len(source_block.boxes):
        return source_block.boxes[box_index]
    return None


def segment_read_from_row(
    row: Segment,
    *,
    box_index: int | None = None,
    source_block: OCRGeometryResult | None = None,
    source_artifact_id: str | None = None,
) -> SegmentRead:
    """The real-row twin of `segment_from_box` -- same `SegmentRead` shape,
    `provisional=False`. The seam (`api/routes/document/segments.py`) is the
    ONE place that resolves either this or the blob path, never both for the
    same pass.

    `box_index` (test-audit B2, 2026-09-20): a real row carries none of its
    own -- it is the caller's position for this row within the pass's
    RESOLVED read order (`_segment_row_sort_key`: `metadata["box_index"]`
    when a converted box recorded one, else `created_at` then `id`), so the
    app's "boxIndex must be exactly 0..count" rule has something dense to
    read. A caller with no such order (a single-segment lookup, not a page
    read) passes nothing and gets `None`, same as before.

    `source_artifact_id` (#4924 review): the artifact this row's PASS was
    converted from. Passed in because a `Segment` does not store one -- a
    segment belongs to a pass, and the pass names the artifact. Without it
    a converted segment read `None` where the provisional one named its
    artifact, which is a difference the master test was hiding by popping
    the field.

    `source_block` (slice 6, #4924): until readings hang on segments
    (slice 8) a box's WORDS have one home -- the kept `ocr_geometry` block
    of the artifact this row was converted from. A row that recorded
    `metadata["box_index"]` reads its text back from that block's box;
    `page_index` comes from `metadata` (STORED at conversion, not read
    back), so a multi-page PDF's rows still filter by page even after the
    artifact is gone. Passing nothing keeps the old answer, `text=None`.

    A MERGED segment's text -- joined from `metadata["member_box_indexes"]`
    -- is deliberately NOT here yet: nothing writes that key until the
    merge internals learn it, and a read path with no writer cannot be
    tested (#4924 step 5)."""
    words = words_for_row(source_block, row.metadata)
    stored_page_index = row.metadata.get("page_index")
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
        # Readings of their own arrive in slice 8; until then a converted
        # row's words come from the box or boxes it was made from.
        text=words,
        confidence=row.confidence,
        # The artifact this row's PASS was converted from, when the caller
        # knows it (#4924 review). A segment made from scratch has none and
        # still reads `None`; a converted one reports the same artifact the
        # provisional read reported, so conversion does not silently drop a
        # field the app can see.
        source_artifact_id=source_artifact_id,
        box_index=box_index,
        page_index=(
            stored_page_index
            if isinstance(stored_page_index, int) and not isinstance(stored_page_index, bool)
            else None
        ),
        metadata=dict(row.metadata),
    )


# ---------------------------------------------------------------------------
# Slice 4 -- matches, forwarding notes, a citable reference (#4922)
#
# An id NEVER MOVES. "This new line is that old line" is a separate MATCH
# record, never an id reassignment. Merge, split and delete leave
# FORWARDING notes (append-only) so an old reference can always be
# followed. `resolve_segment` is the one function everything that follows
# an id uses.
# ---------------------------------------------------------------------------


class SegmentMatch(BaseModel):
    """"This new segment is that old one" -- a record of its own, never an
    id reassignment (`source.segment.match-record`). Many to many is
    allowed (one old line became two)."""

    id: str = Field(default_factory=_new_id)
    document_id: str
    from_segment_id: str  # the older
    to_segment_id: str  # the newer
    state: str = "proposed"  # proposed | accepted | rejected
    proposed_by_kind: ProvenanceKind
    proposed_by: str | None = None
    accepted_by: str | None = None
    accepted_at: datetime | None = None
    certainty: float | None = None
    #: A short reason -- NEVER source text (`source.segment.match-record`'s
    #: audit-payload rule: an action's payload carries ids, kinds and
    #: versions, never a reading's typed text).
    note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class SegmentForwarding(BaseModel):
    """Append-only forwarding note left by a merge, split, delete or
    restore (`source.segment.forwarding-notes`). No action ever updates or
    deletes a row here; undoing a merge writes a NEW `restored` row beside
    the original."""

    id: str = Field(default_factory=_new_id)
    document_id: str
    old_segment_id: str
    kind: str  # merged | split | deleted | restored
    #: Empty for `deleted`. For `split`, includes the id that "stays on one
    #: part" (`resolve_segment` treats a self-reference here as live, never
    #: as a hop to follow -- see its docstring).
    new_segment_ids: list[str] = Field(default_factory=list)
    actor: str | None = None
    #: The action invocation that wrote this row -- resolves to a real
    #: `ActionAudit.id`. Minted by the writing action itself (`uuid.uuid4()`)
    #: BEFORE the generic `ActionAudit` row exists (the registry only
    #: constructs it AFTER `execute()` returns), so the action passes the
    #: SAME id back out via `ChangeSpec.audit_id`, which `ActionRegistry.
    #: invoke` uses as `ActionAudit.id` instead of minting its own (#4955:
    #: before this, the two ids never matched -- every row here was an
    #: orphan). Every forwarding row one action call produces shares the
    #: same `audit_id`, which is enough to group them.
    audit_id: str
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    #: Append order (#4922 third look): two notes for one id written in the
    #: same microsecond have no defined order by `created_at` alone. Every
    #: writer sets this from `Database.next_forwarding_sequence()`
    #: (a native DuckDB sequence -- monotonic, persists across restarts);
    #: `_forwarding_walk`'s "newest wins" now orders by this, not by
    #: timestamp. `None` for a row written before this column existed (an
    #: `ALTER TABLE ADD COLUMN` with no backfill) -- treated as older than
    #: any real sequence number, never as newer (`_sequence_key` below).
    sequence: int | None = None


class SegmentCarry(BaseModel):
    """One record copied across an accepted match
    (`source.segment.carry-across-a-match`). What makes a carry undoable:
    the copies it lists are exactly what the inverse removes. The original
    stays where it was -- a carry copies, it never moves. NEVER a claim
    (#4922 review): a statement is carried by giving the SAME claim one
    more place it rests on, in the statements step (slice 8) -- copying a
    claim would say the same statement twice in the graph."""

    id: str = Field(default_factory=_new_id)
    match_id: str
    carried_kind: str  # reading | annotation
    original_id: str
    copy_id: str
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Slice 5 -- versions for each segment, and refusing a stale edit (#4923)
# ---------------------------------------------------------------------------


class SegmentVersion(BaseModel):
    """Append-only: a full copy of one segment's own fields AT ONE OF ITS
    versions (`source.segment.versioned-alone`), so undo restores from
    ORDINARY DATA, never from the audit chain. Written as a PREIMAGE --
    the row's state right BEFORE the change that bumped `Segment.version`
    past the number this row carries -- by every action that changes a
    segment (`segment.update`/`.delete`/`.undelete`/`.restore_version`,
    and slice 4's `segment.merge`/`.split`): `segment.update`'s own
    `before: {segment_id, version}` names exactly the version number a
    version row was written under, so `segment.restore_version(version=N)`
    finds it directly. No row is written at creation (version 1 has none
    until the segment's first change)."""

    id: str = Field(default_factory=_new_id)
    segment_id: str
    version: int
    document_id: str
    pass_id: str
    parent_segment_id: str | None = None
    kind: str
    kind_raw: str | None = None
    anchor: SourceAnchor
    baseline: list[list[float]] | None = None
    is_furniture: bool = False
    #: True when this snapshot is the state a delete (or a merge's
    #: soft-delete of an absorbed segment) acted on -- "writes a deleted
    #: version" -- never on an ordinary update's snapshot.
    deleted: bool = False
    actor: str | None = None
    provenance_kind: ProvenanceKind
    #: The action invocation that wrote this row -- resolves to a real
    #: `ActionAudit.id`, same minted-locally-then-handed-back-via-
    #: `ChangeSpec.audit_id` convention as `SegmentForwarding.audit_id`
    #: (#4955).
    audit_id: str
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class SegmentStale(ValueError):
    """`segment.update`/`.delete`/`.restore_version`'s compare-and-set
    failed: the caller's `expected_version` no longer matches the live
    row. Carries enough for a caller to re-read and retry
    (`source.edit.stale-is-refused`). `changed` is computed from the
    `SegmentVersion` row tagged with `expected_version` (every bump past
    it writes exactly one, as a preimage); when `expected_version` was
    never actually superseded -- a client sending a version number that
    never existed for this segment -- no such row exists and `changed` is
    simply `[]` (there is nothing recorded to diff against, not "nothing
    changed")."""

    def __init__(self, segment_id: str, expected_version: int, current_version: int, changed: list[str]) -> None:
        self.segment_id = segment_id
        self.expected_version = expected_version
        self.current_version = current_version
        self.changed = changed
        super().__init__(
            f"segment {segment_id!r} is at version {current_version}, not the "
            f"expected {expected_version} (changed: {', '.join(changed) or 'unknown'})"
        )


class SegmentDeleted(ValueError):
    """The segment named is already deleted (or merged away, which sets
    the same `deleted_at`) -- it cannot be updated."""

    def __init__(self, segment_id: str) -> None:
        self.segment_id = segment_id
        super().__init__(f"segment {segment_id!r} is deleted and cannot be updated")


#: Fields compared to fill `SegmentStale.changed` -- geometry and
#: placement only, never text (nothing here ever holds a reading).
_VERSIONED_FIELDS = ("anchor", "baseline", "kind", "kind_raw", "parent_segment_id", "is_furniture")


def changed_fields(before: "SegmentVersion", after: "Segment") -> list[str]:
    """The field names that differ between a historical snapshot and the
    current row -- `SegmentStale.changed` (#4923)."""
    return [f for f in _VERSIONED_FIELDS if getattr(before, f) != getattr(after, f)]


def snapshot_segment_version(
    db: Any, row: "Segment", *, deleted: bool, actor: str | None, audit_id: str, reason: str | None = None,
) -> "SegmentVersion":
    """Write ROW's CURRENT fields as a `SegmentVersion` tagged with its
    CURRENT `version` number (a preimage), then bump `row.version` in
    place -- the one place every segment-changing action does this, so
    `segment.update`, `.delete`, and slice 4's `.merge`/`.split` cannot
    drift from each other. The caller applies its OWN field changes to
    `row` AFTER calling this (the snapshot must capture the OLD values),
    and is responsible for `db.save(row)` once it is done."""
    version = SegmentVersion(
        segment_id=row.id, version=row.version, document_id=row.document_id,
        pass_id=row.pass_id, parent_segment_id=row.parent_segment_id,
        kind=row.kind, kind_raw=row.kind_raw, anchor=row.anchor, baseline=row.baseline,
        is_furniture=row.is_furniture, deleted=deleted, actor=actor,
        provenance_kind=row.provenance_kind, audit_id=audit_id, reason=reason,
    )
    db.save(version)
    row.version += 1
    return version


#: Past this many hops, `resolve_segment` raises rather than keep walking
#: (`source.segment.forwarding-notes`): a loop-free graph should never need
#: this many, so it is a safety net, not a normal path.
FORWARDING_DEPTH_CAP = 64


class SegmentForwardingTooDeep(RuntimeError):
    """A forwarding chain exceeded `FORWARDING_DEPTH_CAP` hops without
    resolving. Never a partial answer -- the caller gets this instead."""

    def __init__(self, segment_id: str, depth: int) -> None:
        self.segment_id = segment_id
        self.depth = depth
        super().__init__(
            f"forwarding chain for {segment_id!r} exceeded {depth} hops "
            "without resolving; this should be unreachable if merges are "
            "refused correctly -- treat as a data problem"
        )


class SegmentForwardingLoop(RuntimeError):
    """A forwarding chain revisited an id -- a cycle exists. Should be
    unreachable (the merge refusal below prevents loops at write time);
    this is the safety net."""

    def __init__(self, segment_id: str) -> None:
        self.segment_id = segment_id
        super().__init__(
            f"forwarding chain revisited {segment_id!r} -- a cycle exists "
            "in the forwarding graph, which should be unreachable"
        )


class ResolvedSegment(BaseModel):
    """What following an id all the way through returns. `live_segment_ids`
    is empty exactly when every branch ended in a delete
    (`ended_in_delete=True`); a MIXED result (some branches deleted, some
    live) is not "ended in delete" -- `trail` carries the deleted branch's
    own forwarding row (kind, actor, created_at) for a caller that wants
    to say which of several ids was lost along the way."""

    requested_id: str
    live_segment_ids: list[str] = Field(default_factory=list)
    trail: list[SegmentForwarding] = Field(default_factory=list)
    ended_in_delete: bool = False
    deleted_by: str | None = None
    deleted_at: datetime | None = None


def _sequence_key(row: SegmentForwarding) -> tuple[int, int]:
    """Sortable append order: `(1, sequence)` for a row that has one,
    `(0, 0)` for a row written before the column existed -- a `None`
    sequence always sorts OLDER than any real one, never newer (#4922
    second look), and rows without one fall back to a stable, if
    arbitrary, relative order among themselves."""
    return (1, row.sequence) if row.sequence is not None else (0, 0)


def _newest(rows: list[SegmentForwarding]) -> SegmentForwarding:
    """The most recently APPENDED of several rows about one id -- ordered
    by `sequence`, not `created_at` alone (#4922 third look: two notes
    written in the same microsecond have no defined order by timestamp)."""
    return max(rows, key=_sequence_key)


def _forwarding_walk(
    db: Any, segment_id: str,
) -> tuple[list[str], list[SegmentForwarding], set[str]]:
    """The one iterative walk `resolve_segment` is built on:
    `(live_ids, trail, every_id_visited)`.

    Two kinds of forwarding note about one id are kept SEPARATE, never
    collapsed by a single "newest row wins" rule -- a split's kept id can
    be split off in one row and later deleted in another, and the second
    must not erase the first's sibling (a bug caught by
    `test_merge_split_delete_chain_resolves_in_one_call`, where the split
    and the delete both file under the same `old_segment_id`):

    - **Liveness rows** (`merged`, `deleted`, `restored`) each say whether
      THIS id's own identity is still live. Only the NEWEST of these
      matters (a later `restored` overrides an older `merged`/`deleted` --
      `test_undo_of_merge_leaves_old_row_beside_a_restored_row`). `merged`
      also names where to keep looking (`new_segment_ids`); `deleted` is
      terminal; `restored` means "live again", nothing further to follow
      from a liveness row alone.
    - **`split` rows** are independent of the above and never superseded:
      they name SIBLINGS to explore (`new_segment_ids`, minus a
      self-reference for "its id stays on one part") regardless of what
      later happens to this id's own liveness.

    **A DIAMOND IS NOT A LOOP** (#4922 third look): splitting a line and
    later merging the parts back together, or splitting into two and
    merging both into a third, reaches one id by more than one path. An id
    reached again is SKIPPED, not an error -- each live id is still
    collected exactly once, and the walk still ends (the depth cap still
    guards a genuinely long chain). A cycle of undone MERGES is a
    different, real problem, refused at WRITE time by `forwards_to`
    (below), on merged edges only -- never detected here.
    """
    visited: set[str] = set()
    trail: list[SegmentForwarding] = []
    live: list[str] = []
    frontier = [segment_id]
    depth = 0
    while frontier:
        depth += 1
        if depth > FORWARDING_DEPTH_CAP:
            raise SegmentForwardingTooDeep(segment_id, FORWARDING_DEPTH_CAP)
        next_frontier: list[str] = []
        for current_id in frontier:
            if current_id in visited:
                continue  # a diamond, not a loop -- already resolved once
            visited.add(current_id)
            rows = db.query(SegmentForwarding, old_segment_id=current_id)
            liveness_rows = [r for r in rows if r.kind in ("merged", "deleted", "restored")]
            split_rows = [r for r in rows if r.kind == "split"]

            is_live = True
            if liveness_rows:
                newest = _newest(liveness_rows)
                trail.append(newest)
                is_live = newest.kind == "restored"
                if newest.kind == "merged":
                    next_frontier.extend(newest.new_segment_ids)

            # Deterministic order (#4922 second look): when an id has more
            # than one split row (rare -- a part split again later), the
            # EARLIEST split's siblings come first, by `sequence`; within
            # one row, the order its parts were listed in stays as given.
            # This is what makes `primary_live_segment_id`'s "first part
            # listed when the split was made" an actual, reproducible
            # order rather than an accident of dict/set iteration.
            for row in sorted(split_rows, key=_sequence_key):
                trail.append(row)
                next_frontier.extend(t for t in row.new_segment_ids if t != current_id)

            if is_live:
                live.append(current_id)
        frontier = next_frontier
    return live, trail, visited


def resolve_segment(db: Any, segment_id: str) -> ResolvedSegment:
    """Follow `segment_id` through every merge/split/delete/restore note
    (`source.segment.forwarding-notes`), used by everything that follows an
    id: the citable reference, and (later slices) any reader handed a
    possibly-stale id. One call, however many hops. After a split,
    `live_segment_ids` names EVERY live part, in the order the parts were
    listed when the split was made (earliest split first when an id was
    split more than once; a row's own listed order within each split) --
    never quietly picks one (#4922 third look)."""
    live, trail, _visited = _forwarding_walk(db, segment_id)
    ended_in_delete = not live
    deleted_row = None
    if ended_in_delete:
        deleted_rows = [row for row in trail if row.kind == "deleted"]
        if deleted_rows:
            deleted_row = _newest(deleted_rows)
    return ResolvedSegment(
        requested_id=segment_id,
        live_segment_ids=live,
        trail=trail,
        ended_in_delete=ended_in_delete,
        deleted_by=deleted_row.actor if deleted_row else None,
        deleted_at=deleted_row.created_at if deleted_row else None,
    )


def primary_live_segment_id(resolved: ResolvedSegment) -> str | None:
    """Which of `resolved.live_segment_ids` is "the" answer, for a caller
    that wants exactly one (#4922 second look): the part that kept the
    REQUESTED id, when it is still live, else the first part listed when
    the split was made (`_forwarding_walk` orders `live_segment_ids` by
    each split note's `sequence`, then by position within it -- a stated,
    reproducible order, never mere discovery order). `None` when nothing
    is live."""
    if not resolved.live_segment_ids:
        return None
    if resolved.requested_id in resolved.live_segment_ids:
        return resolved.requested_id
    return resolved.live_segment_ids[0]


def segment_liveness_reason(db: Any, segment_id: str) -> str | None:
    """`None` when `segment_id` is live; otherwise why it is not
    (`"deleted"`, or `"merged into <id>"`) -- used to refuse a not-live
    participant in a merge, split or carry (#4922 second look: otherwise a
    soft-deleted segment could be "merged", writing a `merged` note NEWER
    than its `deleted` one and quietly turning a delete into a merge).
    Looks at the newest LIVENESS row only (`merged`/`deleted`/`restored`,
    by `sequence`) -- exactly what `_forwarding_walk` itself uses to
    decide "is this id live", so this can never disagree with a resolve.
    """
    rows = db.query(SegmentForwarding, old_segment_id=segment_id)
    liveness_rows = [r for r in rows if r.kind in ("merged", "deleted", "restored")]
    if not liveness_rows:
        return None
    newest = _newest(liveness_rows)
    if newest.kind == "restored":
        return None
    if newest.kind == "deleted":
        return "deleted"
    target = newest.new_segment_ids[0] if newest.new_segment_ids else "an unknown id"
    return f"merged into {target!r}"


def _merged_chain_target(db: Any, current_id: str) -> str | None:
    """The single id `current_id` currently forwards to via an UNDONE
    merge, or `None` when it is live or was later `restored`. One hop of
    the narrow, merged-only walk `forwards_to` uses."""
    rows = db.query(SegmentForwarding, old_segment_id=current_id)
    liveness_rows = [r for r in rows if r.kind in ("merged", "deleted", "restored")]
    if not liveness_rows:
        return None
    newest = _newest(liveness_rows)
    if newest.kind != "merged":
        return None
    return newest.new_segment_ids[0] if newest.new_segment_ids else None


def forwards_to(db: Any, from_id: str, target_id: str) -> bool:
    """True when adding a new `merged` edge `target_id -> from_id` would
    CLOSE A CYCLE -- i.e. `from_id` already reaches `target_id` by
    following only MERGED liveness edges among ids that are not live
    (#4922 third look: the earlier version walked the WHOLE graph,
    including `split`'s siblings, and called an ordinary diamond a loop;
    a real loop is a cycle of undone merges only). Raises
    `SegmentForwardingLoop` if this narrow walk itself revisits an id --
    defensive: should be unreachable, since this same check refuses the
    write that would create one."""
    if from_id == target_id:
        return True
    seen: set[str] = set()
    current: str | None = from_id
    depth = 0
    while current is not None:
        depth += 1
        if depth > FORWARDING_DEPTH_CAP:
            raise SegmentForwardingTooDeep(from_id, FORWARDING_DEPTH_CAP)
        if current == target_id:
            return True
        if current in seen:
            raise SegmentForwardingLoop(current)
        seen.add(current)
        current = _merged_chain_target(db, current)
    return False


def pass_read_from_row(
    row: SegmentPass,
    *,
    artifact_type: str | None = None,
    source_block: OCRGeometryResult | None = None,
) -> PassRead:
    """The real-row twin of the pass half of `segments_from_result`.

    `artifact_type` (test-audit B2, 2026-09-20): App slice A stage 2's notes
    say "a pass made from an artifact carries that artifact's type" -- so a
    pass with a `source_artifact_id` reports that artifact's `artifact_type`
    here (the caller looks it up; this function has no `db`), never a
    guess. A from-scratch pass (no `source_artifact_id`) has nothing to
    carry and stays `None` -- the notes say nothing about that case, so
    nothing is invented for it.

    `source_block` (slice 6, #4924): `PassRead.text` is the RESULT's own
    text, and a box's `char_start`/`char_end` index into exactly that
    string (see `PassRead.text`'s own note: never rebuild it by joining
    box texts). `SegmentPass` has no text column, so a converted pass
    reads it back from the block it was converted from. Without this,
    conversion would silently leave every char span on the page indexing
    into nothing. Passing nothing keeps the old answer, `None`."""
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
        artifact_type=artifact_type,
        # Readings of their own arrive in slice 8; until then a converted
        # pass's text is the block's own (`source_block`).
        text=(source_block.text or None) if source_block is not None else None,
    )


# ---------------------------------------------------------------------------
# Slice 6 -- first-edit conversion (#4924)
#
# Conversion stores EXACTLY what the seam already returns: `segments_from_result`
# is still the one mapping from a block of boxes to reads, and `rows_from_reads`
# below is the whole translation from those reads to rows. There is no second
# mapping and nothing here reads `Artifact.ocr_geometry` itself.
#
# Ids are REPEATABLE (name-based uuid5, not uuid4), which is what makes a lazy
# conversion and an eager one produce byte-identical rows, keeps the audit
# payload to counts and ids, and lets redo land on the same row every lap.
# ---------------------------------------------------------------------------

#: The one namespace converted ids are minted under. NEVER CHANGED: every
#: converted segment's identity is `uuid5(this, f"{artifact_id}:{box_index}")`,
#: so changing it would silently re-identify every already-converted box in
#: every library. Itself a uuid5 of the fixed name below under the standard
#: DNS namespace, so it is reproducible from this file alone rather than a
#: magic literal someone might "tidy".
#: Written as a LITERAL, not computed, so it cannot drift: it is
#: `uuid5(NAMESPACE_DNS, "segments.conversion.fichero")`, and
#: `test_the_conversion_namespace_never_changes` pins both the value and
#: that derivation.
SEGMENT_CONVERSION_NAMESPACE = uuid.UUID("6fd743f7-2111-514c-89f6-dfd308363dd5")


def converted_segment_id(artifact_id: str, box_index: int) -> str:
    """The lasting id box `box_index` of `artifact_id` takes at conversion.

    `source.store.conversion-ids-repeatable`. The id belongs to THAT box of
    THAT result forever: an id is never handed to another segment, and a
    second conversion of the same artifact (which cannot happen, but the
    guard is free) writes the same row rather than a duplicate."""
    return uuid.uuid5(SEGMENT_CONVERSION_NAMESPACE, f"{artifact_id}:{box_index}").hex


def converted_pass_id(artifact_id: str) -> str:
    """The lasting id the pass converted from `artifact_id` takes.

    Prefixed `pass:` so a pass and box 0 of the same artifact can never
    collide."""
    return uuid.uuid5(SEGMENT_CONVERSION_NAMESPACE, f"pass:{artifact_id}").hex


def real_id_for_provisional(provisional_id: str) -> str | None:
    """The lasting id a provisional (``legacy:``) id becomes at conversion,
    or ``None`` when the id is not a provisional one.

    NO FORWARDING ROWS ARE WRITTEN AT CONVERSION, and this function is why.
    A forwarding note records that one LASTING id gave way to another; a
    provisional id was never lasting -- it names a position in a blob. Twenty
    thousand notes for a dense page would be twenty thousand rows saying what
    this function says in a line.

    Says NOTHING about whether the row exists: a caller that wants to answer
    "this provisional id is now that segment" must look the row up and only
    then claim it (`source.seam.provisional-ids-refused` still holds on every
    write path -- this is for READS).

    Both shapes round-trip their minting function:
    `legacy_segment_id(a, n)` -> `converted_segment_id(a, n)`,
    `legacy_pass_id(a)` -> `converted_pass_id(a)`.
    """
    if not provisional_id.startswith(LEGACY_ID_PREFIX):
        return None
    body = provisional_id[len(LEGACY_ID_PREFIX):]
    if not body:
        return None
    # An artifact id is a bare uuid hex with no colon of its own, so the LAST
    # colon (if any) separates the box index -- `rsplit`, never `split`.
    artifact_id, _, tail = body.rpartition(":")
    if not artifact_id:
        # No colon: the whole body is the artifact id, so this is a PASS id.
        return converted_pass_id(body)
    try:
        box_index = int(tail)
    except ValueError:
        return None
    if box_index < 0 or tail != str(box_index):
        # Refuse "-0", "007", " 3" and friends: a provisional id is minted by
        # `legacy_segment_id`, which always renders the plain decimal, so
        # anything else did not come from us and must not be mapped.
        return None
    return converted_segment_id(artifact_id, box_index)


class BoxIndexesNotContiguous(ValueError):
    """`rows_from_reads` was handed reads whose box indexes are not exactly
    ``0..n-1``.

    Cannot arise from `segments_from_result` (the index IS the list
    position), so this is a guard against a future caller, not a case in the
    wild -- and it REFUSES THE WHOLE PASS rather than convert part of a page,
    because the app addresses a box by its position and a gap would silently
    shift every box after it."""

    def __init__(self, artifact_id: str, indexes: list[int | None]) -> None:
        self.artifact_id = artifact_id
        self.indexes = indexes
        super().__init__(
            f"artifact {artifact_id!r} gave box indexes {indexes!r}, which are "
            "not exactly 0..n-1; refusing to convert a page whose positions would shift"
        )


def _converted_box_columns(read: SegmentRead) -> tuple[float, float, float, float, str]:
    """The bbox columns for ONE converted box, tolerating a box whose shape
    the anchor could not hold.

    `bbox_and_tile_from_anchor` RAISES for an anchor with neither rect nor
    polygon, and it is right to: `segment.create` only ever accepts an
    anchor that has one, so there a missing shape is a bug. CONVERSION IS
    DIFFERENT. A real page can carry a degenerate box (`_build_anchor`
    drops a zero-size rect and records the reason in
    `metadata["geometry_problem"]`), and such a box MUST still become a
    row: the app draws a zero-size placeholder for it, and if it vanished
    every later box would shift up by one position -- silently moving
    somebody's regions. So the columns go to zero and the row keeps its
    place.

    Consequence worth knowing: a zero box files under tile `x0y0`, so a
    read by area over the top-left corner will return it. It has to be
    filed somewhere, and `metadata["geometry_problem"]` says why it is
    there.
    """
    try:
        return bbox_and_tile_from_anchor(read.anchor)
    except ValueError:
        logger.debug(
            "converted box %s has no drawable shape (%s); storing zero columns",
            read.box_index, read.metadata.get("geometry_problem"),
        )
        return 0.0, 0.0, 0.0, 0.0, _tile_key(0.0, 0.0, 0.0, 0.0)


def rows_from_reads(
    pass_read: PassRead, segment_reads: list[SegmentRead]
) -> tuple[SegmentPass, list[Segment]]:
    """The WHOLE translation from what the seam returns to what is stored.

    `source.store.conversion-changes-nothing-seen`: every field here is
    copied from the read, never re-derived, so a converted page comes back
    through `pass_read_from_row`/`segment_read_from_row` equal to the
    provisional page it replaced but for `id`, `pass_id` and `provisional`.

    Three fields are set from the READ rather than from "now", and each is
    load-bearing:

    * ``SegmentPass.created_at`` is the ARTIFACT's `created_at`, not
      `utc_now()`. The seam sorts passes by `(created_at, id)`, so a pass
      stamped at conversion time would reorder a page that has two results
      -- a difference a person can see, which the master test forbids.
    * ``SegmentPass.actor`` is ALWAYS ``None``. Nothing here is the
      converting person's work; only the edit that triggered the conversion
      is theirs, and that edit is recorded on its own segment's version.
    * ``created_by`` is the artifact's provider (or ``None``), NEVER
      ``ctx.actor`` -- `source.store.converted-boxes-keep-their-maker`. A
      box a person hand-drew into a machine result keeps
      ``provenance_kind=human`` but gets ``created_by=None``: the block
      records THAT a person drew it, never WHICH person, and inventing the
      converting actor there would credit one historian with another's work.

    No `SegmentVersion` rows are written. Version rows are PREIMAGES (see
    `SegmentVersion`'s docstring: "no row is written at creation"), and
    `snapshot_segment_version` bumps `version` in place, so writing one here
    would leave every converted row at version 2 with a snapshot of a state
    nothing ever superseded.
    """
    artifact_id = pass_read.source_artifact_id
    if not artifact_id:
        raise ValueError(
            "rows_from_reads needs a pass that names its source artifact; "
            f"got pass {pass_read.id!r} with source_artifact_id=None"
        )

    indexes = [read.box_index for read in segment_reads]
    if indexes != list(range(len(segment_reads))):
        raise BoxIndexesNotContiguous(artifact_id, indexes)

    pass_row = SegmentPass(
        id=converted_pass_id(artifact_id),
        document_id=pass_read.document_id,
        name=pass_read.name,
        provenance_kind=pass_read.provenance_kind,
        actor=None,
        provider=pass_read.provider,
        model=pass_read.model,
        run_id=pass_read.run_id,
        source_artifact_id=artifact_id,
        created_at=pass_read.created_at or utc_now(),
    )

    rows: list[Segment] = []
    for read in segment_reads:
        bbox_x, bbox_y, bbox_w, bbox_h, tile = _converted_box_columns(read)
        metadata = dict(read.metadata)
        # The sort key the seam already reads (`_segment_row_sort_key`), so a
        # converted page keeps the order the app was last given, and the
        # source of a row's words (`segment_read_from_row`'s `source_block`).
        metadata["box_index"] = read.box_index
        if read.page_index is not None:
            # STORED, not read back: it must survive the artifact being gone.
            metadata["page_index"] = read.page_index
        rows.append(
            Segment(
                id=converted_segment_id(artifact_id, read.box_index),
                document_id=read.document_id,
                pass_id=pass_row.id,
                kind=read.kind,
                kind_raw=read.kind_raw,
                anchor=read.anchor,
                baseline=read.baseline,
                bbox_x=bbox_x,
                bbox_y=bbox_y,
                bbox_w=bbox_w,
                bbox_h=bbox_h,
                tile=tile,
                doc_kind=f"{read.document_id}:{read.kind}",
                confidence=read.confidence,
                provenance_kind=read.provenance_kind,
                created_by=(
                    None
                    if read.provenance_kind is ProvenanceKind.human
                    else pass_read.provider
                ),
                created_at=pass_read.created_at or utc_now(),
                updated_at=pass_read.created_at or utc_now(),
                metadata=metadata,
            )
        )
    return pass_row, rows


# ---------------------------------------------------------------------------
# Slice 6b (#4990) -- the READ SHAPES for "where does this anchor point now".
#
# They live HERE, beside the segment they resolve to, rather than with the
# resolver in `api/routes/document/segment_conversion.py`, for one reason:
# `models/__init__.py` has to name `ResolvedAnchor` to type the claim read,
# and a model cannot import a route module. Typed rather than left loose --
# an untyped field generates a loose container in every client, which is the
# same defect the annotation list's own schema test exists to prevent.
#
# The RESOLVER stays with the conversion, because that is what it knows about.
# ---------------------------------------------------------------------------

class AnchorBasis(str, Enum):
    """How a resolved anchor got its place."""

    #: Nothing resolved it: no rectangle, no converted result on this page,
    #: or no block box with that rectangle. The stored place is the answer,
    #: and it is the RIGHT answer -- a mark somebody drew free was about a
    #: place, not about a line.
    stored = "stored"
    #: It matched a box, and that box's segment is live. The answer is where
    #: the segment is NOW.
    segment = "segment"
    #: It matched a box whose segment has been deleted. The stored place is
    #: the answer, and the caller is told the line is gone rather than being
    #: shown a rectangle with nothing behind it.
    segment_deleted = "segment-deleted"


class ResolvedAnchor(BaseModel):
    """Where a stored anchor points NOW.

    THE PROBLEM THIS SOLVES, which is older than the source model: a mark a
    person makes on a line is stored with the rectangle that line had at
    that moment. Move the line and the mark stays where the box used to be.
    Every rectangle a mark draws comes from that stored rectangle, and
    nothing on that path ever asked where the box went.

    THE WAY BACK, and it needs nothing stored: the KEPT BLOCK never
    changes, so it is a permanent table from "the rectangle a box had" to
    "that box's position", and a position plus the artifact gives the
    repeatable segment id (`converted_segment_id`). So the link from a
    remembered rectangle to a line can be recovered at ANY later time,
    however often the line has moved since.

    The stored anchor is NEVER rewritten. This rides beside it.
    """

    anchor: SourceAnchor
    basis: AnchorBasis
    segment_id: str | None = None



class SegmentPassChoice(BaseModel):
    """"This is the pass I am working on" -- a person's choice, recorded.

    Table `segmentpasschoices`. Slice 6 (#4924) only WRITES these: the edit
    that converted a page says which result the Source view was showing,
    and that is a fact worth keeping, because a page accumulates passes (a
    machine run after conversion adds another) and "which one am I looking
    at" is otherwise guessed from dates.

    Rows are NEVER DELETED. A later choice supersedes an earlier one by
    stamping `superseded_at` on it, so the history of what somebody was
    working on stays readable -- the same shape `ReadingChoice` takes in
    the readings slice, deliberately, since the two are read together.

    The RANKING that decides which pass is shown when there is no live
    choice (`resolve_working_pass`) belongs to the readings-and-cascade
    slice, not here. This record is its first input, not its replacement.
    """

    id: str = Field(default_factory=_new_id)
    document_id: str
    pass_id: str
    #: Who chose it. A choice is always a person's -- a machine does not
    #: decide which pass a historian is working on.
    chosen_by: str | None = None
    chosen_at: datetime = Field(default_factory=utc_now)
    #: Set when a later choice replaces this one. Never deleted.
    superseded_at: datetime | None = None
