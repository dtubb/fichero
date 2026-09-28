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
    residuals,
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
        usable.append((gcp.id, (point[0] * width, point[1] * height), (world["lon"], world["lat"])))
    version = hashlib.sha256(f"{pass_row.transformation}|{mask_id}|{'|'.join(fingerprint)}".encode()).hexdigest()[:16]
    return usable, not_used, version


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
