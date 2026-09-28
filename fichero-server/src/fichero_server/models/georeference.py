"""Georeferencing records (slice 15, #4933; `maps-and-georeference.md`).

A ground control point IS a segment -- kind ``control-point``, one point on one image, in a pass,
with a maker (`source.geo.gcp-is-a-segment`). Moving its pixel end or withdrawing it are the segment
actions that already exist. What a segment cannot hold is its WORLD end, so that is this record:
one live row per control point, superseded (never overwritten) when it is retyped, so each change is
one audited step on that point alone (`source.geo.gcp-corrected-alone`).

The pass that holds a map's control points and masks is the georeferencing pass
(`source.geo.georef-is-a-pass`); its one property here is the transformation type, kept by pass id.
The transform itself is worked out, never stored (`georef/transform.py`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind

GCP_KIND = "control-point"
MASK_KIND = "mask"


class ControlPointPlace(BaseModel):
    """Where on the earth one control point is (`source.geo.crs-*`).

    Stored in WGS 84 (EPSG:4326, ruled on #5124) as ``lon``/``lat``, with what it ARRIVED as kept
    beside it: the CRS, the two numbers in the order typed, the axis order, and the conversion used.
    A CRS of ``unknown`` is held unconverted -- ``lon``/``lat`` stay None, so it can be looked at but
    is never fitted, overlaid or exported as a place (`source.geo.crs-unknown`)."""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    segment_id: str
    lon: float | None = None
    lat: float | None = None
    source_crs: str
    source_x: float
    source_y: float
    #: "lon,lat" or "lat,lon": how ``source_x``/``source_y`` were meant. Recorded, never assumed.
    axis_order: str
    #: "none (already WGS 84)", or the conversion's name once PROJ ships; None while unknown.
    conversion: str | None = None
    #: "to the nearest 50 m", as metres, when the person said.
    precision_m: float | None = Field(default=None, gt=0)
    #: The mask this point belongs to, when the sheet has several maps (`source.geo.mask`).
    mask_segment_id: str | None = None
    provenance_kind: ProvenanceKind = ProvenanceKind.unknown
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    #: Superseded or withdrawn, never deleted.
    withdrawn_at: datetime | None = None


class GeoreferencingSettings(BaseModel):
    """A georeferencing pass's transformation type (`source.geo.transformation-type`). ``id`` IS the
    pass id, so it resolves to the pass's document with no resolver of its own."""

    id: str
    transformation_type: str
    set_by: str | None = None
    set_at: datetime = Field(default_factory=utc_now)
