"""A place over time: which of its geometries held at a date (maps D7, #5120;
`source.geo.geometry-over-time`).

A place's geometries are its dated `EvidentialPlace` rows -- a span (Pleiades's -330..640) or a point
in time (a Wikidata position `P585` 2019: start == end). As of a date the answer is EVERY geometry
valid then (rivals stay rivals, each with its source), or none with the reason -- never the nearest,
which would be a guess presented as a fact. An undated geometry is listed apart: valid, time unknown.

Years are compared at year granularity on the astronomical count (1 BC = 0), each span converted
from the numbering it names (`EvidentialDateRange.numbering`); the years themselves are stored as the
source wrote them. The full date model (`source.date.*`, #4936) is not this: a span keeps its wording.
"""

from __future__ import annotations

import math
import re

_YEAR = re.compile(r"^\s*([+-]?)0*(\d{1,6})")


def astronomical_year(value, numbering: str | None = None) -> int | None:
    """The year of `value` ("-330", "1700", "+2019-00-00T00:00:00Z", "1831-06-01") on the
    astronomical count, or None when it states none."""
    if value is None:
        return None
    match = _YEAR.match(str(value))
    if not match:
        return None
    year = int(match.group(1) + match.group(2))
    if numbering == "historical" and year < 0:
        year += 1          # historical numbering has no year 0: 1 BC is astronomical 0
    return year


def is_dated(span) -> bool:
    return span is not None and (astronomical_year(span.start, span.numbering) is not None
                                 or astronomical_year(span.end, span.numbering) is not None)


def valid_at(span, year: int) -> bool:
    """Whether `span` holds in `year`. A bound left out is open only when the span says so
    (`open_start` / `open_end`); otherwise the other bound stands for it -- a point in time."""
    start = astronomical_year(span.start, span.numbering)
    end = astronomical_year(span.end, span.numbering)
    low = start if start is not None else (None if span.open_start else end)
    high = end if end is not None else (None if span.open_end else start)
    return (low is None or low <= year) and (high is None or year <= high)


def geometries_as_of(entity, as_of: str) -> dict:
    """{geometries, undated, reason} for the entity's place evidence as of `as_of` (an ISO 8601
    year or date, astronomical count). `reason` is None when something is valid."""
    year = astronomical_year(as_of, "astronomical")
    if year is None:
        raise ValueError(f"as_of {as_of!r} is not a year or an ISO 8601 date")
    # A relative place has no coordinates of its own: it is answered apart (`relative_as_of`).
    places = [place for place in entity.place_values or [] if place.relative is None]
    valid = [place for place in places if is_dated(place.when) and valid_at(place.when, year)]
    undated = [place for place in places if not is_dated(place.when)]
    return {"geometries": valid, "undated": undated,
            "reason": None if valid else f"none valid in {as_of}"}


# ---------------------------------------------------------------------------
# Relative places (maps D10, `source.geo.relative-place`): an anchor, a distance as written, maybe a
# bearing -- resolved on read to an AREA, never a point. Spherical earth, stdlib maths: a ring around
# the anchor at distance ± tolerance, or the sector of it the bearing allows.
# ---------------------------------------------------------------------------

EARTH_RADIUS_M = 6371008.8     # the IUGG mean radius
_STEPS = 72


def destination(lat: float, lon: float, bearing_deg: float, distance_m: float) -> tuple[float, float]:
    """(lon, lat) `distance_m` from (lat, lon) along `bearing_deg`, on a sphere."""
    phi, lam, theta = math.radians(lat), math.radians(lon), math.radians(bearing_deg)
    delta = distance_m / EARTH_RADIUS_M
    phi2 = math.asin(math.sin(phi) * math.cos(delta) + math.cos(phi) * math.sin(delta) * math.cos(theta))
    lam2 = lam + math.atan2(math.sin(theta) * math.sin(delta) * math.cos(phi),
                            math.cos(delta) - math.sin(phi) * math.sin(phi2))
    return round((math.degrees(lam2) + 540) % 360 - 180, 7), round(math.degrees(phi2), 7)


def area_around(lat: float, lon: float, inner_m: float, outer_m: float,
                bearing_deg: float | None = None, halfwidth_deg: float = 22.5) -> dict:
    """The GeoJSON Polygon between `inner_m` and `outer_m` of the anchor: a ring (with a hole) in
    every direction, or the sector `bearing_deg ± halfwidth_deg` of it. Exterior counterclockwise."""
    if bearing_deg is None:
        # Counterclockwise on the map = decreasing compass bearing.
        outer = [destination(lat, lon, 360 - 360 * i / _STEPS, outer_m) for i in range(_STEPS)]
        rings = [outer + [outer[0]]]
        if inner_m > 0:
            inner = [destination(lat, lon, 360 * i / _STEPS, inner_m) for i in range(_STEPS)]
            rings.append(inner + [inner[0]])
        return {"type": "Polygon", "coordinates": rings}
    steps = max(4, int(_STEPS * halfwidth_deg / 180))
    start, end = bearing_deg - halfwidth_deg, bearing_deg + halfwidth_deg
    arc = [start + (end - start) * i / steps for i in range(steps + 1)]
    outer = [destination(lat, lon, b % 360, outer_m) for b in reversed(arc)]          # counterclockwise
    inner = [destination(lat, lon, b % 360, inner_m) for b in arc] if inner_m > 0 else [(round(lon, 7), round(lat, 7))]
    ring = outer + inner
    return {"type": "Polygon", "coordinates": [ring + [ring[0]]]}


def _anchor_point(place) -> tuple[float, float] | None:
    """(lat, lon) of an anchor geometry: its point, or the mean of a shape's outer ring."""
    if place.lat is not None and place.lon is not None:
        return place.lat, place.lon
    shape = place.geojson or {}
    ring = shape.get("coordinates", [[]])[0] if shape.get("type") == "Polygon" else None
    if ring:
        return sum(p[1] for p in ring) / len(ring), sum(p[0] for p in ring) / len(ring)
    return None


def relative_as_of(db, entity, as_of: str, conversions: dict[str, str] | None = None) -> list[dict]:
    """Each relative place of `entity`, resolved as of `as_of`: its area, the conversion and tolerance
    used, and the anchor geometry -- or no area with the reason. `conversions` is the library's
    choice per unit ({"legua": "comun"}); a unit not in it uses its default."""
    from fichero_server.knowledge.units import UnknownUnit, resolve_distance
    from fichero_server.models.knowledge import KnowledgeEntity

    out = []
    for place in entity.place_values or []:
        relative = place.relative
        if relative is None:
            continue
        answer = {"place_id": place.id, "label": place.label, "relative": relative.model_dump(mode="json"),
                  "area": None, "conversion": None, "anchor": None, "reason": None}
        out.append(answer)
        try:
            conversion = resolve_distance(relative.distance_value, relative.unit, (conversions or {}).get(relative.unit))
        except (UnknownUnit, KeyError) as refusal:
            answer["reason"] = str(refusal)
            continue
        answer["conversion"] = conversion
        anchor = db.get(KnowledgeEntity, relative.anchor_entity_id)
        if anchor is None:
            answer["reason"] = f"the anchor {relative.anchor_entity_id} is not in the library"
            continue
        placed = geometries_as_of(anchor, as_of)
        basis, candidates = ("dated", placed["geometries"]) if placed["geometries"] else ("undated", placed["undated"])
        points = [(p, _anchor_point(p)) for p in candidates]
        points = [(p, xy) for p, xy in points if xy is not None]
        if not points:
            answer["reason"] = f"the anchor {anchor.canonical_name} has no geometry to measure from as of {as_of}"
            continue
        anchor_place, (lat, lon) = points[0]
        inner = max(0.0, conversion["distance_m"] - conversion["tolerance_m"])
        outer = conversion["distance_m"] + conversion["tolerance_m"]
        answer["area"] = area_around(lat, lon, inner, outer, relative.bearing_deg, relative.bearing_halfwidth_deg)
        answer["anchor"] = {"entity_id": anchor.id, "name": anchor.canonical_name, "lat": lat, "lon": lon,
                            "place_id": anchor_place.id, "basis": basis,
                            "rivals": len(points) - 1}
    return out
