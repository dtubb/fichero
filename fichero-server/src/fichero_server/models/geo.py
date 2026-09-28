"""A point in the world, as a reading (`maps-and-georeference.md`, #5122).

A ground control point is a `control-point` segment (its pixel end is the segment's anchor) whose
READING of kind `world-point` is its place on the earth. A reading, not a second table, so a GCP's
world end has a maker, a history, corrections that count (#5175) and undo for free.

The rules, all ruled:
* **The CRS it arrived in is always said** (`source.geo.crs-explicit`): a write naming none is
  refused. `"unknown"` is a value a file with no CRS states, never an assumption of WGS 84.
* **Stored in WGS 84** (`source.geo.crs-stored-as-wgs84`, ruled on #5124): EPSG:4326 is stored as
  it is; the CRS it arrived in, its axis order and the conversion used are recorded.
* **No conversion is guessed** (`source.geo.crs-unknown`): any other CRS is held with its numbers
  unconverted and `crs: "unknown"` until PROJ ships with the app (`source.geo.proj-at-build`, the
  maintainer's decision), so it can be looked at and not overlaid or exported as a place.
"""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

WORLD_POINT = "world-point"
WGS84 = "EPSG:4326"
CRS_UNKNOWN = "unknown"
NO_CONVERSION = "no conversion available: PROJ is not shipped with the app yet (source.geo.proj-at-build)"


class WorldPointIn(BaseModel):
    """What a caller writes: the two numbers AS ENTERED, their CRS and their axis order."""

    model_config = ConfigDict(extra="forbid")

    coordinates: list[float] = Field(min_length=2, max_length=2)
    #: An EPSG code (`EPSG:4326`), WKT2 text, or `unknown`. Required: never assumed.
    crs: str = Field(min_length=1)
    #: Which number is which. Required for the same reason: `lat,lon` and `lon,lat` are both common.
    axis_order: Literal["lon,lat", "lat,lon", "x,y"]
    #: How precise the person was, in metres ("to the nearest 50 m").
    precision_m: Optional[float] = Field(default=None, gt=0)


class WorldPoint(BaseModel):
    """What is stored: WGS 84 lon/lat, or None with `crs: unknown` and the numbers as entered."""

    lon: Optional[float]
    lat: Optional[float]
    crs: str
    crs_in: str
    axis_order_in: str
    as_entered: list[float]
    conversion: str
    precision_m: Optional[float] = None


class WorldPointRefused(ValueError):
    """A world point that cannot be stored as it was written."""


def _canonical_crs(crs: str) -> str:
    value = crs.strip()
    upper = value.upper().replace(" ", "")
    if upper in {"EPSG:4326", "URN:OGC:DEF:CRS:EPSG::4326", "WGS84", "CRS84", "OGC:CRS84"}:
        return WGS84
    if value.lower() == CRS_UNKNOWN:
        return CRS_UNKNOWN
    return value


def world_point(value: dict[str, Any] | WorldPointIn) -> WorldPoint:
    """The stored form of a world point written as `value`, or `WorldPointRefused`."""
    try:
        written = value if isinstance(value, WorldPointIn) else WorldPointIn.model_validate(value)
    except Exception as exc:  # noqa: BLE001 -- pydantic's message names the field
        raise WorldPointRefused(
            f"a world point needs its two coordinates, its CRS (an EPSG code, WKT2, or 'unknown') "
            f"and its axis order; {exc}"
        ) from exc
    crs = _canonical_crs(written.crs)
    a, b = written.coordinates
    common = {"crs_in": written.crs.strip(), "axis_order_in": written.axis_order,
              "as_entered": [a, b], "precision_m": written.precision_m}
    if crs != WGS84:
        reason = "the file stated no CRS" if crs == CRS_UNKNOWN else NO_CONVERSION
        return WorldPoint(lon=None, lat=None, crs=CRS_UNKNOWN, conversion=reason, **common)
    if written.axis_order == "x,y":
        raise WorldPointRefused("EPSG:4326 coordinates need 'lon,lat' or 'lat,lon', not 'x,y'")
    lon, lat = (a, b) if written.axis_order == "lon,lat" else (b, a)
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise WorldPointRefused(f"({lon}, {lat}) is not a longitude and latitude (axis order {written.axis_order})")
    return WorldPoint(lon=lon, lat=lat, crs=WGS84, conversion="none: arrived in EPSG:4326", **common)


def world_point_content(content: str) -> str:
    """A `world-point` reading's content, checked and stored in its canonical form (JSON)."""
    try:
        raw = json.loads(content)
    except (TypeError, ValueError) as exc:
        raise WorldPointRefused(f"a world-point reading's content is JSON; {exc}") from exc
    if not isinstance(raw, dict):
        raise WorldPointRefused("a world-point reading's content is a JSON object")
    return world_point(raw).model_dump_json()
