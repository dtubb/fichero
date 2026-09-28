"""Georeferencing: control points' world ends, a pass's transformation type, and the worked-out
transform (slice 15, #4933; `maps-and-georeference.md`).

Writes are audited, undoable actions: ``georef.place`` (a control point's world end; placing it again
supersedes, and ⌘Z brings the earlier one back), ``georef.withdraw_place``, ``georef.set_type``.
Moving a control point's pixel end, or withdrawing the point itself, are ``segment.update`` /
``segment.delete``: a control point is a segment. Reads: a pass's control points with their residuals
(``GET /api/georef/pass/{id}``) and any segment's worked-out place in the world
(``GET /api/georef/segment/{id}/world``). Nothing worked out is stored.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.api.main import get_library_database
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.georef.transform import DEFAULT_TYPE, NEEDED, TooFew, georeference, inside
from fichero_server.models import Rendition, Segment
from fichero_server.models.georeference import GCP_KIND, MASK_KIND, ControlPointPlace, GeoreferencingSettings
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import SegmentPass, SegmentPassChoice, assert_not_provisional

router = APIRouter(prefix="/georef")

#: The CRSs converted today. Both ARE WGS 84, so "converting" them is naming the axis order. Any other
#: needs PROJ, which ships at build time or not at all (`source.geo.proj-at-build`).
_WGS84 = {"EPSG:4326", "OGC:CRS84"}
UNKNOWN_CRS = "unknown"


def _live_segment(db: Database, segment_id: str) -> Segment:
    assert_not_provisional(segment_id, what="segment_id")
    segment = db.get(Segment, segment_id)
    if segment is None or segment.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
    return segment


class GeorefPlaceParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    x: float
    y: float
    #: An EPSG code ("EPSG:4326"), "OGC:CRS84", or "unknown". Never defaulted (`source.geo.crs-explicit`).
    crs: str = Field(min_length=1, max_length=4000)
    #: How x and y are meant. Required for EPSG:4326, whose own order is lat,lon but which most
    #: software writes lon,lat: which one the person meant is recorded, not guessed.
    axis_order: Optional[Literal["lon,lat", "lat,lon"]] = None
    precision_m: Optional[float] = Field(default=None, gt=0)
    mask_segment_id: Optional[str] = None


def _place_from(params: GeorefPlaceParams) -> dict[str, Any]:
    """The stored fields for one typed place: WGS 84 lon/lat, or held unconverted when unknown."""
    crs = params.crs.strip()
    if crs.lower() == UNKNOWN_CRS:
        return {"source_crs": UNKNOWN_CRS, "axis_order": params.axis_order or "unknown",
                "lon": None, "lat": None, "conversion": None}
    crs = crs.upper()
    if crs not in _WGS84:
        raise HTTPException(status_code=422, detail=(
            f"converting from {crs} to WGS 84 needs PROJ, which this engine does not ship yet "
            "(#4933, source.geo.proj-at-build); type it in EPSG:4326, or as 'unknown' to hold it unconverted"))
    if crs == "OGC:CRS84":
        if params.axis_order not in (None, "lon,lat"):
            raise HTTPException(status_code=422, detail="OGC:CRS84 is lon,lat by definition")
        order = "lon,lat"
    elif params.axis_order is None:
        raise HTTPException(status_code=422, detail=(
            "EPSG:4326 needs axis_order: its own order is lat,lon but most software writes lon,lat"))
    else:
        order = params.axis_order
    lon, lat = (params.x, params.y) if order == "lon,lat" else (params.y, params.x)
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise HTTPException(status_code=422, detail=f"not a place on the earth: lon {lon}, lat {lat}")
    return {"source_crs": crs, "axis_order": order, "lon": lon, "lat": lat, "conversion": "none (already WGS 84)"}


def _place_spec(db: Database, place: ControlPointPlace, after: dict, emit: str) -> ChangeSpec:
    segment = db.get(Segment, place.segment_id)
    return ChangeSpec(
        domains=["georef", "segment"], target_ids=[place.id, place.segment_id], before=None, after=after,
        emit_type=emit, document_ids=[segment.document_id] if segment else [], segment_ids=[place.segment_id],
    )


def _invert_place(before, after, ctx: ActionContext):
    """Undo a placing: withdraw it and bring back the one it superseded, if any."""
    place_id = (after or {}).get("place_id")
    if not place_id:
        return None
    return ("georef.withdraw_place", {"place_id": place_id, "restore_id": (after or {}).get("superseded_id")})


@action("georef.place", GeorefPlaceParams, domains=["georef", "segment"], undoable=True, invert=_invert_place)
def _action_place(db: Database, params: GeorefPlaceParams, ctx: ActionContext):
    """Say where on the earth a control point is. Placing it again supersedes the earlier place."""
    segment = _live_segment(db, params.segment_id)
    if segment.kind != GCP_KIND:
        raise HTTPException(status_code=422, detail=f"a place in the world goes on a {GCP_KIND} segment, not a {segment.kind}")
    if params.mask_segment_id:
        mask = _live_segment(db, params.mask_segment_id)
        if mask.kind != MASK_KIND or mask.pass_id != segment.pass_id:
            raise HTTPException(status_code=422, detail="the mask must be a mask segment in the control point's pass")
    fields = _place_from(params)
    live = [p for p in db.query(ControlPointPlace, segment_id=segment.id) if p.withdrawn_at is None]
    for earlier in live:
        earlier.withdrawn_at = utc_now()
        db.save(earlier)
    place = ControlPointPlace(
        segment_id=segment.id, source_x=params.x, source_y=params.y, precision_m=params.precision_m,
        mask_segment_id=params.mask_segment_id, provenance_kind=provenance_kind_from_ctx(ctx),
        created_by=ctx.actor or None, **fields,
    )
    db.save(place)
    after = {"place_id": place.id, "superseded_id": live[-1].id if live else None}
    return after, _place_spec(db, place, after, "georef.placed")


class GeorefWithdrawParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place_id: str
    #: Bring this earlier place of the same point back in the same step (the undo of a re-placing).
    restore_id: Optional[str] = None


def _invert_withdraw(before, after, ctx: ActionContext):
    """Symmetric, so ⇧⌘Z works."""
    if not after:
        return None
    if after.get("restored_id"):
        return ("georef.withdraw_place", {"place_id": after["restored_id"], "restore_id": after["place_id"]})
    return ("georef.restore_place", {"place_id": after["place_id"]})


def _set_withdrawn(db: Database, place_id: str, withdrawn: bool) -> ControlPointPlace:
    place = db.get(ControlPointPlace, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail=f"Place not found: {place_id}")
    place.withdrawn_at = utc_now() if withdrawn else None
    db.save(place)
    return place


@action("georef.withdraw_place", GeorefWithdrawParams, domains=["georef", "segment"], undoable=True,
        invert=_invert_withdraw)
def _action_withdraw(db: Database, params: GeorefWithdrawParams, ctx: ActionContext):
    place = _set_withdrawn(db, params.place_id, True)
    restored_id = None
    if params.restore_id:
        earlier = db.get(ControlPointPlace, params.restore_id)
        if earlier is not None and earlier.segment_id == place.segment_id:
            earlier.withdrawn_at = None
            db.save(earlier)
            restored_id = earlier.id
    after = {"place_id": place.id, "restored_id": restored_id}
    return after, _place_spec(db, place, after, "georef.withdrawn")


class GeorefPlaceIdParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place_id: str


@action("georef.restore_place", GeorefPlaceIdParams, domains=["georef", "segment"], undoable=False)
def _action_restore(db: Database, params: GeorefPlaceIdParams, ctx: ActionContext):
    place = _set_withdrawn(db, params.place_id, False)
    after = {"place_id": place.id}
    return after, _place_spec(db, place, after, "georef.restored")


class GeorefSetTypeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_id: str
    transformation_type: Literal[tuple(NEEDED)]  # type: ignore[valid-type]


@action("georef.set_type", GeorefSetTypeParams, domains=["georef"], undoable=True,
        invert=lambda before, after, ctx: ("georef.set_type", {
            "pass_id": after["pass_id"], "transformation_type": before["transformation_type"]}) if after else None)
def _action_set_type(db: Database, params: GeorefSetTypeParams, ctx: ActionContext):
    """Choose the pass's transformation type (`source.geo.transformation-type`); ⌘Z puts back the last."""
    assert_not_provisional(params.pass_id, what="pass_id")
    pass_row = db.get(SegmentPass, params.pass_id)
    if pass_row is None or pass_row.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Pass not found: {params.pass_id}")
    settings = db.get(GeoreferencingSettings, pass_row.id)
    before = {"transformation_type": settings.transformation_type if settings else DEFAULT_TYPE}
    db.save(GeoreferencingSettings(id=pass_row.id, transformation_type=params.transformation_type,
                                   set_by=ctx.actor or None))
    after = {"pass_id": pass_row.id, "transformation_type": params.transformation_type}
    return after, ChangeSpec(domains=["georef"], target_ids=[pass_row.id], before=before, after=after,
                             emit_type="georef.type_set", document_ids=[pass_row.document_id])


# ---------------------------------------------------------------------------
# Reads: worked out on every call, never stored
# ---------------------------------------------------------------------------


def _image_point(segment: Segment) -> list[float]:
    """A control point's pixel end: its point shape, or the middle of its box."""
    for shape in segment.anchor.shapes or []:
        if shape.kind.value == "point" and shape.points:
            return list(shape.points[0])
    x, y, w, h = segment.anchor.rect
    return [x + w / 2, y + h / 2]


def _outline(segment: Segment) -> list[list[float]]:
    """A segment's shape as image points: its outline, its shapes' points, or its box's corners."""
    if segment.anchor.polygon:
        return [list(p) for p in segment.anchor.polygon]
    points = [list(p) for shape in segment.anchor.shapes or [] for p in (shape.points or [])]
    if points:
        return points
    x, y, w, h = segment.anchor.rect
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _image_size(db: Database, segment: Segment) -> tuple[int, int] | None:
    """The image's pixel size, to give residuals in pixels; None when no rendition records it."""
    renditions = ([db.get(Rendition, segment.anchor.rendition_id)] if segment.anchor.rendition_id
                  else list(db.query(Rendition, document_id=segment.document_id)))
    for rendition in renditions:
        if rendition is not None and rendition.pixel_width and rendition.pixel_height:
            return rendition.pixel_width, rendition.pixel_height
    return None


def _gcps(db: Database, pass_id: str) -> list[tuple[Segment, ControlPointPlace | None]]:
    segments = [s for s in db.query(Segment, pass_id=pass_id) if s.kind == GCP_KIND and s.deleted_at is None]
    out = []
    for segment in sorted(segments, key=lambda s: s.id):
        live = [p for p in db.query(ControlPointPlace, segment_id=segment.id) if p.withdrawn_at is None]
        out.append((segment, live[-1] if live else None))
    return out


def _masks(db: Database, pass_id: str) -> list[Segment]:
    return sorted((s for s in db.query(Segment, pass_id=pass_id) if s.kind == MASK_KIND and s.deleted_at is None),
                  key=lambda s: s.id)


def _transformation_type(db: Database, pass_id: str) -> str:
    settings = db.get(GeoreferencingSettings, pass_id)
    return settings.transformation_type if settings else DEFAULT_TYPE


def _version(kind: str, gcps: list[tuple[Segment, ControlPointPlace | None]]) -> str:
    """The GCP set's version: changes when any point's pixel or world end, or the type, changes. Every
    worked-out answer names it (`source.geo.transform-is-derived`)."""
    material = [kind] + [[s.id, s.version, p.id if p else None] for s, p in gcps]
    return hashlib.sha256(json.dumps(material).encode()).hexdigest()[:16]


def _chosen(db: Database, pass_row: SegmentPass) -> bool:
    """A machine's control points are unchosen until a person chooses its pass (`machine-gcps-unchosen`)."""
    if pass_row.provenance_kind != ProvenanceKind.workflow:
        return True
    return any(c.pass_id == pass_row.id and c.superseded_at is None
               for c in db.query(SegmentPassChoice, document_id=pass_row.document_id))


class ControlPointRead(BaseModel):
    segment_id: str
    place_id: Optional[str] = None
    image_point: list[float]
    lon: Optional[float] = None
    lat: Optional[float] = None
    source_crs: Optional[str] = None
    source_x: Optional[float] = None
    source_y: Optional[float] = None
    axis_order: Optional[str] = None
    conversion: Optional[str] = None
    precision_m: Optional[float] = None
    mask_segment_id: Optional[str] = None
    provenance_kind: Optional[str] = None
    created_by: Optional[str] = None
    #: How far the fitted transform misses this point: metres on the earth, and in the image (as a
    #: fraction of it, and in pixels when the image's size is known). None when it was not fitted.
    residual_m: Optional[float] = None
    residual_image: Optional[float] = None
    residual_px: Optional[float] = None


class GeorefPassRead(BaseModel):
    pass_id: str
    document_id: str
    transformation_type: str
    needed: int
    gcp_set_version: str
    chosen: bool
    masks: list[str]
    control_points: list[ControlPointRead]
    #: Points whose CRS is unknown: shown, never fitted.
    unknown_crs: int
    #: Why no transform could be worked out ("polynomial2 needs 6 ..."), or None.
    refused: Optional[str] = None
    rms_m: Optional[float] = None


def _fit_group(kind: str, rows: list[tuple[Segment, ControlPointPlace | None]]):
    placed = [(s, p) for s, p in rows if p is not None and p.lon is not None]
    return placed, georeference(kind, [_image_point(s) for s, _ in placed], [(p.lon, p.lat) for _, p in placed])


def _pass_read(db: Database, pass_row: SegmentPass) -> GeorefPassRead:
    kind = _transformation_type(db, pass_row.id)
    rows = _gcps(db, pass_row.id)
    masks = _masks(db, pass_row.id)
    reads = {s.id: ControlPointRead(segment_id=s.id, image_point=_image_point(s)) for s, _ in rows}
    for s, p in rows:
        if p is not None:
            reads[s.id] = reads[s.id].model_copy(update={
                **p.model_dump(include={"lon", "lat", "source_crs", "source_x", "source_y", "axis_order",
                                        "conversion", "precision_m", "mask_segment_id", "created_by"}),
                "place_id": p.id, "provenance_kind": p.provenance_kind.value})
    refused, residuals = None, []
    # One fit per mask: a sheet with two maps has two sets of control points (`source.geo.mask`).
    groups: dict[str | None, list] = {}
    for s, p in rows:
        if p is not None and p.lon is not None:
            groups.setdefault(p.mask_segment_id if len(masks) > 1 else None, []).append((s, p))
    if not groups:
        groups[None] = []
    for group in groups.values():
        try:
            placed, fitted = _fit_group(kind, group)
        except TooFew as exc:
            refused = str(exc)
            continue
        size = _image_size(db, placed[0][0]) if placed else None
        for (s, _), metres, (dx, dy) in zip(placed, fitted.residuals_m, fitted.residuals_image):
            px = math.hypot(dx * size[0], dy * size[1]) if size else None
            reads[s.id] = reads[s.id].model_copy(update={
                "residual_m": metres, "residual_image": math.hypot(dx, dy), "residual_px": px})
            residuals.append(metres)
    return GeorefPassRead(
        pass_id=pass_row.id, document_id=pass_row.document_id, transformation_type=kind, needed=NEEDED[kind],
        gcp_set_version=_version(kind, rows), chosen=_chosen(db, pass_row), masks=[m.id for m in masks],
        control_points=list(reads.values()),
        unknown_crs=sum(1 for _, p in rows if p is not None and p.lon is None),
        refused=refused, rms_m=(sum(r * r for r in residuals) / len(residuals)) ** 0.5 if residuals else None,
    )


def _live_pass(db: Database, pass_id: str) -> SegmentPass:
    assert_not_provisional(pass_id, what="pass_id")
    pass_row = db.get(SegmentPass, pass_id)
    if pass_row is None or pass_row.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Pass not found: {pass_id}")
    return pass_row


@router.get("/pass/{pass_id}", response_model=GeorefPassRead)
async def georef_pass(pass_id: str, db: Database = Depends(get_library_database)) -> GeorefPassRead:
    """A georeferencing pass: its control points with their residuals, masks and type."""
    return _pass_read(db, _live_pass(db, pass_id))


class WorldShapeRead(BaseModel):
    segment_id: str
    #: "placed", or "outside_the_map" (never extrapolated, `source.geo.outside-the-mask`).
    status: str
    #: GeoJSON (RFC 7946: lon,lat in WGS 84) -- a Point for one point, else a Polygon.
    geometry: Optional[dict[str, Any]] = None
    crs: str = "EPSG:4326"
    axis_order: str = "lon,lat"
    pass_id: str
    transformation_type: str
    gcp_set_version: str
    mask_segment_id: Optional[str] = None
    #: The error estimate: the root-mean-square residual of the control points used, in metres. None
    #: for a thin-plate spline, which meets every control point exactly and so estimates nothing.
    error_m: Optional[float] = None
    control_points_used: int = 0


def _georef_pass_for(db: Database, segment: Segment, pass_id: str | None) -> SegmentPass:
    """The georeferencing pass that places this page: the one named, else the only one, else the one a
    person chose (the working-pass rule). Several and none chosen is said, never picked."""
    if pass_id:
        pass_row = _live_pass(db, pass_id)
        if pass_row.document_id != segment.document_id:
            raise HTTPException(status_code=422, detail="that georeferencing pass is of another page")
        return pass_row
    passes = {s.pass_id for s in db.query(Segment, document_id=segment.document_id)
              if s.kind == GCP_KIND and s.deleted_at is None}
    rows = [p for p in (db.get(SegmentPass, i) for i in sorted(passes)) if p is not None and p.deleted_at is None]
    if not rows:
        raise HTTPException(status_code=422, detail="this page is not georeferenced: it has no control points")
    if len(rows) == 1:
        return rows[0]
    chosen = [c for c in db.query(SegmentPassChoice, document_id=segment.document_id)
              if c.superseded_at is None and c.pass_id in passes]
    if chosen:
        return db.get(SegmentPass, max(chosen, key=lambda c: c.chosen_at).pass_id)
    raise HTTPException(status_code=409, detail=(
        f"this page has {len(rows)} georeferencings and none is chosen; name one with pass_id"))


def _mask_ring(mask: Segment) -> list[list[float]]:
    return _outline(mask)


@router.get("/segment/{segment_id}/world", response_model=WorldShapeRead)
async def segment_world(
    segment_id: str,
    pass_id: Optional[str] = Query(default=None),
    db: Database = Depends(get_library_database),
) -> WorldShapeRead:
    """Any segment's place in the world, worked out through the georeferencing pass
    (`source.geo.world-shape`). Never stored: a corrected control point changes every answer."""
    segment = _live_segment(db, segment_id)
    pass_row = _georef_pass_for(db, segment, pass_id)
    kind = _transformation_type(db, pass_row.id)
    rows = _gcps(db, pass_row.id)
    base = {"segment_id": segment.id, "pass_id": pass_row.id, "transformation_type": kind,
            "gcp_set_version": _version(kind, rows)}
    # GCPs measured on one image say nothing about another without a recorded alignment
    # (`source.geo.gcp-other-image`); none is used here, so a different image is refused by name.
    images = {s.anchor.rendition_id for s, _ in rows}
    if images and segment.anchor.rendition_id not in images:
        raise HTTPException(status_code=422, detail=(
            "the control points were measured on another image of this page, and no alignment between "
            "the two is used; place control points on this image"))
    outline = _outline(segment)
    masks = _masks(db, pass_row.id)
    mask = None
    if masks:
        mask = next((m for m in masks if all(inside(p, _mask_ring(m)) for p in outline)), None)
        if mask is None:
            return WorldShapeRead(status="outside_the_map", **base)
    if len(masks) > 1:
        rows = [(s, p) for s, p in rows if p is not None and p.mask_segment_id == mask.id]
    try:
        placed, fitted = _fit_group(kind, rows)
    except TooFew as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    world = [list(p) for p in fitted.to_world(outline)]
    geometry = ({"type": "Point", "coordinates": world[0]} if len(world) == 1
                else {"type": "Polygon", "coordinates": [world + [world[0]]]})
    error = None if kind == "thin_plate_spline" else (
        sum(r * r for r in fitted.residuals_m) / len(fitted.residuals_m)) ** 0.5
    return WorldShapeRead(status="placed", geometry=geometry, mask_segment_id=mask.id if mask else None,
                          error_m=error, control_points_used=len(placed), **base)
