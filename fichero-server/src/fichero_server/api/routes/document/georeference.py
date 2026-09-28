"""A georeferencing pass's transformation and its worked-out transform (#5122, slice 15 B).

* `georef.set_transformation` -- the pass's transformation type, one audited, undoable action;
  a type the pass has too few GCPs for is refused with the number it needs
  (`source.geo.transformation-type`).
* `GET /api/georeference/passes/{pass_id}/transform` -- the transform WORKED OUT from the pass's
  GCPs and type, never stored (`source.geo.transform-is-derived`), with every GCP's residual in
  metres and pixels (`source.geo.residuals`) and the GCP-set version a caller may cache it by.

A GCP is usable when it is live and its counted `world-point` reading has a place in WGS 84; one
held as `unknown` (a CRS not converted yet) is listed in `not_used`, never guessed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.db import Database
from fichero_server.models import ContentRepresentation, Document, Segment
from fichero_server.models.geo import (
    MIN_GCPS,
    TRANSFORMATIONS,
    WORLD_POINT,
    TooFewControlPoints,
    UnknownTransformation,
    WorkedOutTransform,
    inside_polygon,
    residuals,
    world_points,
)
from fichero_server.models.segments import SegmentPass
from fichero_server.models.typed_links import TypedLink

router = APIRouter(prefix="/georeference")

GCP_KIND = "control-point"
MASK_KIND = "mask"


def _live_pass(db: Database, pass_id: str) -> SegmentPass:
    row = db.get(SegmentPass, pass_id)
    if row is None or row.deleted_at is not None:
        raise LookupError(f"Pass not found: {pass_id}")
    return row


def control_points(
    db: Database, pass_row: SegmentPass, mask_id: str | None = None
) -> tuple[list[tuple[str, tuple[float, float], tuple[float, float]]], list[dict[str, str]], str]:
    """(usable GCPs as (segment id, pixel, (lon, lat)), those left out and why, GCP-set version).

    With a `mask_id`, only the GCPs that `control` that mask (a sheet with two maps has two)."""
    from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment

    document = db.get(Document, pass_row.document_id)
    metadata = (document.metadata if document is not None else None) or {}
    width, height = metadata.get("width"), metadata.get("height")
    if not (isinstance(width, (int, float)) and isinstance(height, (int, float)) and width > 0 and height > 0):
        raise ValueError("the page's pixel size is not recorded, so a GCP's pixel end cannot be measured")
    gcps = [s for s in db.query(Segment, pass_id=pass_row.id) if s.kind == GCP_KIND and s.deleted_at is None]
    if mask_id is not None:
        controlling = {l.from_id for l in db.query(TypedLink, to_id=mask_id)
                       if l.link_type == "controls" and l.deleted_at is None}
        gcps = [g for g in gcps if g.id in controlling]
    usable, not_used, fingerprint = [], [], []
    for gcp in sorted(gcps, key=lambda s: s.id):
        items = readings_of_segment(db, gcp.id)
        counted = counting_by_kind(db, gcp.id, items).get(WORLD_POINT)
        reading = db.get(ContentRepresentation, counted.representation_id) if counted and counted.representation_id else None
        fingerprint.append(f"{gcp.id}:{gcp.version}:{reading.id if reading else '-'}")
        if reading is None:
            not_used.append({"segment_id": gcp.id, "reason": "no world position counts for it"})
            continue
        world = json.loads(reading.content)
        if world.get("lon") is None or world.get("lat") is None:
            not_used.append({"segment_id": gcp.id, "reason": f"its place is held as {world.get('crs')}: {world.get('conversion')}"})
            continue
        shapes = gcp.anchor.shapes or []
        point = next((sh.points[0] for sh in shapes if str(getattr(sh.kind, "value", sh.kind)) == "point" and sh.points), None)
        if point is None:
            not_used.append({"segment_id": gcp.id, "reason": "it has no point on the image"})
            continue
        try:
            # Measured on another image of the page: carried to the page's frame only through a
            # recorded alignment (`source.geo.gcp-other-image`); otherwise said, not guessed.
            [point] = page_frame_points(db, gcp.anchor.rendition_id, [point])
        except NoKnownAlignment as refusal:
            not_used.append({"segment_id": gcp.id, "reason": str(refusal)})
            continue
        usable.append((gcp.id, (point[0] * width, point[1] * height), (world["lon"], world["lat"])))
    version = hashlib.sha256(f"{pass_row.transformation}|{mask_id}|{'|'.join(fingerprint)}".encode()).hexdigest()[:16]
    return usable, not_used, version


class NoKnownAlignment(ValueError):
    """A shape measured on an image whose relation to the page's own frame is not recorded:
    Fichero says it cannot place it, rather than guess (`source.geo.gcp-other-image`,
    `source.segment.no-guessing-across-images`)."""


#: Roles whose image is turned against the page: a crop rect alone does not say how.
_TURNED = {"rotated", "deskewed"}


def page_frame_points(db: Database, rendition_id: str | None, points: list[list[float]], _depth: int = 0) -> list[list[float]]:
    """Normalised points measured on `rendition_id` expressed in the PAGE's own frame, through the
    rendition's recorded relation to it (`Rendition.transform`, which chains). No rendition, or a
    pure resample (no transform), is the page's frame already. A crop maps exactly. Anything else
    -- a turned image, a relation in pixels of an unknown size, a missing rendition -- raises
    `NoKnownAlignment` naming why."""
    from fichero_server.models import Rendition

    if rendition_id is None:
        return [list(p) for p in points]
    if _depth > 8:
        raise NoKnownAlignment(f"rendition {rendition_id}'s frames chain too deep to follow")
    rendition = db.get(Rendition, rendition_id)
    if rendition is None:
        raise NoKnownAlignment(f"it was measured on image {rendition_id}, which is not in this library")
    region = rendition.transform
    if region is None:
        return [list(p) for p in points]                       # a pure resample: the same frame
    if rendition.role in _TURNED:
        raise NoKnownAlignment(
            f"it was measured on a {rendition.role} image ({rendition_id}) whose turn against the page "
            "is not recorded, so it cannot be carried to the page")
    if str(getattr(region.space, "value", region.space)) != "normalized":
        raise NoKnownAlignment(f"image {rendition_id}'s place on the page is recorded in pixels of a size not known here")
    x, y, w, h = region.rect
    mapped = [[x + px * w, y + py * h] for px, py in points]
    return page_frame_points(db, region.rendition_id, mapped, _depth + 1)


def _masks(db: Database, pass_row: SegmentPass) -> list[str]:
    return [s.id for s in db.query(Segment, pass_id=pass_row.id) if s.kind == MASK_KIND and s.deleted_at is None]


class TransformationSetParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_id: str
    #: One of `models.geo.TRANSFORMATIONS`. None only as an undo's way back to a pass that had
    #: none.
    transformation: Optional[str]


def _invert_set_transformation(before, after, ctx: ActionContext):
    if not before:
        return None
    return ("georef.set_transformation", {"pass_id": before["pass_id"], "transformation": before["transformation"]})


@action(
    "georef.set_transformation",
    TransformationSetParams,
    domains=["georeference"],
    undoable=True,
    invert=_invert_set_transformation,
)
def _action_set_transformation(db: Database, params: TransformationSetParams, ctx: ActionContext):
    """Choose a georeferencing pass's transformation type (`source.geo.transformation-type`)."""
    pass_row = _live_pass(db, params.pass_id)
    if params.transformation is not None:
        if params.transformation not in TRANSFORMATIONS:
            raise UnknownTransformation(f"{params.transformation!r} is not one of {', '.join(TRANSFORMATIONS)}")
        # Every map on the sheet must be fittable: each mask's GCPs, or the pass's when it has none.
        for mask_id in _masks(db, pass_row) or [None]:
            usable, _not_used, _version = control_points(db, pass_row, mask_id)
            if len(usable) < MIN_GCPS[params.transformation]:
                raise TooFewControlPoints(params.transformation, len(usable))
    before = {"pass_id": pass_row.id, "transformation": pass_row.transformation}
    pass_row.transformation = params.transformation
    db.save(pass_row)
    return (
        {"pass_id": pass_row.id, "transformation": pass_row.transformation},
        ChangeSpec(
            domains=["georeference"], target_ids=[pass_row.id], before=before,
            after={"pass_id": pass_row.id, "transformation": pass_row.transformation},
            emit_type="segment.pass_updated", pass_ids=[pass_row.id], document_ids=[pass_row.document_id],
        ),
    )


class DepictsSetParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pass_id: str
    #: An `EvidentialDateRange`: the date (or span) the map shows, its wording and its basis; None clears.
    depicts: Optional[dict[str, Any]] = None


def _invert_set_depicts(before, after, ctx: ActionContext):
    return ("georef.set_depicts", {"pass_id": before["pass_id"], "depicts": before["depicts"]}) if before else None


@action("georef.set_depicts", DepictsSetParams, domains=["georeference"], undoable=True, invert=_invert_set_depicts)
def _action_set_depicts(db: Database, params: DepictsSetParams, ctx: ActionContext):
    """Say what date a georeferenced map depicts (`source.geo.map-depicts-date`)."""
    from fichero_server.models.knowledge import EvidentialDateRange

    pass_row = _live_pass(db, params.pass_id)
    if not pass_row.transformation:
        raise HTTPException(status_code=422, detail=f"pass {pass_row.id} georeferences nothing: a depicted date belongs to a georeferenced map")
    before = {"pass_id": pass_row.id, "depicts": pass_row.depicts.model_dump(mode="json") if pass_row.depicts else None}
    pass_row.depicts = EvidentialDateRange.model_validate(params.depicts) if params.depicts is not None else None
    db.save(pass_row)
    after = {"pass_id": pass_row.id, "depicts": pass_row.depicts.model_dump(mode="json") if pass_row.depicts else None}
    return after, ChangeSpec(domains=["georeference"], target_ids=[pass_row.id], before=before, after=after,
                             emit_type="segment.pass_updated", pass_ids=[pass_row.id], document_ids=[pass_row.document_id])


def working_georeference(db: Database, document_id: str) -> tuple[str | None, str | None]:
    """(pass id, basis): the image's working georeferencing pass, by the SAME rule as its text
    pass (`resolve_working_pass`) over its georeferencing passes only (#5122,
    `source.geo.georef-is-a-pass`): a person's choice, then a pass a person made or touched, then an
    imported one, then the newest."""
    from fichero_server.api.routes.document.segment_readings import (
        SegmentPassChoice,
        _pass_candidates,
        project_record_rule,
        resolve_working_pass,
    )

    answer = resolve_working_pass(
        project_record_rule(db),
        list(db.query(SegmentPassChoice, document_id=document_id)),
        _pass_candidates(db, document_id, georeferencing=True),
    )
    return answer.pass_id, (answer.basis.value if answer.pass_id else None)


def _labels(db: Database, pass_row: SegmentPass) -> dict[str, Any]:
    from fichero_server.models.knowledge import ProvenanceKind

    working_id, basis = working_georeference(db, pass_row.document_id)
    machine = pass_row.provenance_kind not in (ProvenanceKind.human, ProvenanceKind.external_import)
    chosen = working_id == pass_row.id and basis in ("chosen", "human-touched")
    return {
        "pass_provenance": getattr(pass_row.provenance_kind, "value", pass_row.provenance_kind),
        "working": working_id == pass_row.id,
        "pass_basis": basis if working_id == pass_row.id else None,
        "unchosen": machine and not chosen,
    }


def worked_out_transform(db: Database, pass_id: str, mask_id: str | None = None) -> WorkedOutTransform:
    pass_row = _live_pass(db, pass_id)
    if not pass_row.transformation:
        raise ValueError(f"pass {pass_id} georeferences nothing: it has no transformation")
    masks = _masks(db, pass_row)
    if mask_id is None and len(masks) > 1:
        raise ValueError(f"this sheet has {len(masks)} maps; name one (mask_id): {', '.join(masks)}")
    mask_id = mask_id or (masks[0] if masks else None)
    usable, not_used, version = control_points(db, pass_row, mask_id)
    rows, rms_m, rms_px = residuals(pass_row.transformation, usable) if usable else ([], 0.0, 0.0)
    return WorkedOutTransform(
        pass_id=pass_row.id, mask_id=mask_id, transformation=pass_row.transformation,
        gcp_set_version=version, gcps=rows, rms_m=rms_m, rms_px=rms_px, not_used=not_used,
        **_labels(db, pass_row),
    )


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, LookupError):
        return HTTPException(404, str(exc))
    return HTTPException(422, str(exc))


class TransformationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transformation: str


@router.put("/passes/{pass_id}/transformation", response_model=dict)
async def set_transformation(
    pass_id: str,
    body: TransformationBody,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict[str, Any]:
    """`PUT /api/georeference/passes/{pass_id}/transformation` -- choose the type; 422 with the
    number of GCPs it needs when the pass has too few."""
    try:
        result = registry.invoke(db, "georef.set_transformation",
                                 {"pass_id": pass_id, "transformation": body.transformation}, ctx)
    except (LookupError, ValueError) as exc:
        raise _http(exc) from exc
    return {**result.result, "audit_id": result.audit_id}


@router.get("/passes/{pass_id}/transform", response_model=WorkedOutTransform)
async def get_transform(
    pass_id: str,
    mask_id: Optional[str] = Query(None, description="Which map on the sheet, when it has several"),
    db: Database = Depends(get_library_database),
) -> WorkedOutTransform:
    """`GET /api/georeference/passes/{pass_id}/transform` -- worked out now, with residuals."""
    try:
        return worked_out_transform(db, pass_id, mask_id)
    except (LookupError, ValueError) as exc:
        raise _http(exc) from exc


class WorldShape(BaseModel):
    """A segment's place in the world, WORKED OUT through a georeferencing pass and never stored
    as the segment's truth (`source.geo.world-shape`). `outside_the_map` instead of a shape when
    any of it lies outside the map's mask (`source.geo.outside-the-mask`): never extrapolated."""

    segment_id: str
    pass_id: str
    mask_id: str | None = None
    transformation: str
    gcp_set_version: str
    crs: str = "EPSG:4326"
    #: RFC 7946 geometry, lon/lat, or None when outside the map.
    geometry: dict[str, Any] | None = None
    #: The fit's RMS residual on the ground: how far off the answer may be.
    error_m: float
    outside_the_map: bool = False
    reason: str | None = None
    #: As on the transform: whose pass, whether working and why, and whether it is a machine's
    #: GCPs nobody has chosen (then the place is SHOWN, labelled, not the record).
    pass_provenance: str | None = None
    working: bool = False
    pass_basis: str | None = None
    unchosen: bool = False
    #: The date the map depicts (the pass's `depicts`), or None when nobody has said.
    depicts: dict[str, Any] | None = None


def _segment_shape(segment: Segment) -> tuple[str, list[list[float]]]:
    """(GeoJSON type, normalised points) for a segment's own shape."""
    anchor = segment.anchor
    for shape in anchor.shapes or []:
        kind = str(getattr(shape.kind, "value", shape.kind))
        if kind == "point" and shape.points:
            return "Point", [shape.points[0]]
        if kind == "path" and shape.points:
            return "LineString", shape.points
        if kind in ("polygon", "rect") and shape.points:
            return "Polygon", shape.points
    if anchor.polygon:
        return "Polygon", anchor.polygon
    if anchor.rect:
        x, y, w, h = anchor.rect
        return "Polygon", [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    raise ValueError(f"segment {segment.id} has no shape on the image")


def world_shape(db: Database, segment_id: str, pass_id: str | None = None) -> WorldShape:
    segment = db.get(Segment, segment_id)
    if segment is None or segment.deleted_at is not None:
        raise LookupError(f"Segment not found: {segment_id}")
    if pass_id is None:
        pass_id, _basis = working_georeference(db, segment.document_id)
        if pass_id is None:
            raise ValueError("this image is not georeferenced: no pass on it has a transformation")
    pass_row = _live_pass(db, pass_id)
    if pass_row.document_id != segment.document_id:
        raise ValueError(f"pass {pass_id} georeferences another image")
    kind, points = _segment_shape(segment)
    points = page_frame_points(db, segment.anchor.rendition_id, points)     # NoKnownAlignment -> 422
    masks = [db.get(Segment, m) for m in _masks(db, pass_row)]

    def mask_on_page(mask: Segment) -> list[list[float]] | None:
        try:
            return page_frame_points(db, mask.anchor.rendition_id, mask.anchor.polygon)
        except NoKnownAlignment:
            return None   # a mask that cannot be placed on the page contains nothing we can say

    containing = [m for m in masks if m is not None and m.anchor.polygon and (outline := mask_on_page(m))
                  and all(inside_polygon((x, y), outline) for x, y in points)]
    transform = worked_out_transform(db, pass_row.id, containing[0].id if containing else (masks[0].id if len(masks) == 1 else None))
    common = {"segment_id": segment.id, "pass_id": pass_row.id, "transformation": transform.transformation,
              "gcp_set_version": transform.gcp_set_version, "error_m": transform.rms_m,
              "depicts": pass_row.depicts.model_dump(mode="json") if pass_row.depicts else None,
              **{k: getattr(transform, k) for k in ("pass_provenance", "working", "pass_basis", "unchosen")}}
    if masks and not containing:
        return WorldShape(**common, mask_id=None, outside_the_map=True,
                          reason="the segment is not wholly inside any of this sheet's maps (masks)")
    document = db.get(Document, segment.document_id)
    width, height = document.metadata["width"], document.metadata["height"]
    usable, _not_used, _version = control_points(db, pass_row, transform.mask_id)
    lonlat = [list(p) for p in world_points(transform.transformation, usable, [(x * width, y * height) for x, y in points])]
    coordinates: Any = lonlat[0] if kind == "Point" else lonlat if kind == "LineString" else [lonlat + [lonlat[0]]]
    return WorldShape(**common, mask_id=transform.mask_id, geometry={"type": kind, "coordinates": coordinates})


@router.get("/segments/{segment_id}/world-shape", response_model=WorldShape)
async def get_world_shape(
    segment_id: str,
    pass_id: Optional[str] = Query(None, description="The georeferencing pass, when the image has several"),
    db: Database = Depends(get_library_database),
) -> WorldShape:
    """`GET /api/georeference/segments/{segment_id}/world-shape` -- worked out now."""
    try:
        return world_shape(db, segment_id, pass_id)
    except (LookupError, ValueError) as exc:
        raise _http(exc) from exc


@router.get("/documents/{doc_id}/geojson", response_model=dict)
async def get_document_geojson(
    doc_id: str,
    kinds: str = Query("place", description="Comma-separated segment kinds to place"),
    db: Database = Depends(get_library_database),
) -> dict[str, Any]:
    """`GET /api/georeference/documents/{doc_id}/geojson` -- this image's segments of `kinds`, placed
    in the world through its working georeferencing pass, as an RFC 7946 FeatureCollection
    (`source.geo.geojson-out`). Each Feature is the segment's `world-shape`: its id, its citable
    reference back, the pass and transform version, the error estimate and whether the GCPs are a
    machine's unchosen ones. A segment that cannot be placed (outside the map, on an image with no
    recorded alignment) is not a Feature: it is listed, with why, in the foreign member
    `fichero:not_placed` -- never dropped silently, never extrapolated."""
    from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment
    from fichero_server.models.geo import counterclockwise, geojson_problems

    wanted = {k.strip() for k in kinds.split(",") if k.strip()}
    georef = {p.id for p in db.query(SegmentPass, document_id=doc_id) if p.transformation}
    rows = sorted((s for s in db.query(Segment, document_id=doc_id)
                   if s.deleted_at is None and s.kind in wanted and s.pass_id not in georef), key=lambda s: s.id)
    library_uuid = db.library_uuid() or "unknown"
    features, not_placed = [], []
    for row in rows:
        try:
            shape = world_shape(db, row.id)
        except (LookupError, ValueError) as refusal:
            not_placed.append({"segment_id": row.id, "reason": str(refusal)})
            continue
        if shape.outside_the_map or shape.geometry is None:
            not_placed.append({"segment_id": row.id, "reason": shape.reason or "outside the map"})
            continue
        items = readings_of_segment(db, row.id)
        counted = counting_by_kind(db, row.id, items).get("transcription")
        text = next((i.content for i in items if counted and i.id == counted.representation_id), None)
        features.append({
            "type": "Feature",
            "id": row.id,
            "geometry": counterclockwise(shape.geometry),
            "properties": {
                "reference": f"fichero:segment/{library_uuid}/{row.document_id}/{row.id}",
                "segment_id": row.id, "kind": row.kind, "text": text,
                "georeference_pass_id": shape.pass_id, "transformation": shape.transformation,
                "gcp_set_version": shape.gcp_set_version, "error_m": shape.error_m, "unchosen": shape.unchosen,
            },
        })
    collection = {"type": "FeatureCollection", "features": features, "fichero:not_placed": not_placed}
    problems = geojson_problems(collection)
    if problems:
        raise HTTPException(500, "the GeoJSON written breaks RFC 7946: " + "; ".join(problems))
    return collection
