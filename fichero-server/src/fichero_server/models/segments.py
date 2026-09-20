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

from pydantic import BaseModel, ValidationError

from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind

logger = logging.getLogger(__name__)

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
    provider: str | None = None
    model: str | None = None
    run_id: str | None = None
    created_at: datetime | None = None
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
    )
    return pass_read, segments
