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


#: A georeferencing pass's transformation type (`source.geo.transformation-type`): the words
#: Allmaps and QGIS share. `polynomial-1` is affine, the default, and what a world file holds.
TRANSFORMATIONS = ("polynomial-1", "polynomial-2", "polynomial-3", "thin-plate-spline", "helmert", "projective")
DEFAULT_TRANSFORMATION = "polynomial-1"


class UnknownTransformation(ValueError):
    """A transformation this library does not know: refused by name, never guessed."""


def transformation_from_iiif(value: dict[str, Any] | None) -> str:
    """A IIIF georef `transformation` object as one of `TRANSFORMATIONS`; the default when none."""
    if not value:
        return DEFAULT_TRANSFORMATION
    kind = str(value.get("type") or "")
    if kind == "polynomial":
        order = (value.get("options") or {}).get("order", 1)
        name = f"polynomial-{order}"
    else:
        name = {"thinPlateSpline": "thin-plate-spline", "helmert": "helmert", "projective": "projective"}.get(kind, kind)
    if name not in TRANSFORMATIONS:
        raise UnknownTransformation(
            f"the file's transformation {value!r} is not one of {', '.join(TRANSFORMATIONS)}; "
            "nothing was imported rather than guess one"
        )
    return name


# ---------------------------------------------------------------------------
# The transform: WORKED OUT from a pass's GCPs and its transformation type, never stored
# (`source.geo.transform-is-derived`), with each GCP's residual (`source.geo.residuals`).
# ---------------------------------------------------------------------------

#: The fewest GCPs each transformation can be fitted from. A polynomial of order n has
#: (n+1)(n+2)/2 terms per axis; helmert (similarity) 2 points; projective 4; a thin-plate spline
#: carries an affine part, so 3.
MIN_GCPS = {"polynomial-1": 3, "polynomial-2": 6, "polynomial-3": 10, "helmert": 2, "projective": 4,
            "thin-plate-spline": 3}

#: Metres per degree of latitude (a sphere of the mean Earth radius): residuals are reported in
#: metres on a local equirectangular plane about the GCPs' centre -- an ERROR measure over a
#: map's extent, not a survey computation.
_EARTH_RADIUS_M = 6_371_008.8


class TooFewControlPoints(ValueError):
    """A transformation that cannot be fitted from the GCPs there are: says how many it needs."""

    def __init__(self, transformation: str, have: int) -> None:
        self.needed = MIN_GCPS[transformation]
        super().__init__(
            f"{transformation} needs at least {self.needed} control points with a known place; "
            f"this has {have}"
        )


def _local_plane(worlds: list[tuple[float, float]]):
    """(to_metres, to_lonlat): lon/lat <-> x/y metres on a plane about the points' centre."""
    import math

    lon0 = sum(p[0] for p in worlds) / len(worlds)
    lat0 = sum(p[1] for p in worlds) / len(worlds)
    k = math.pi / 180 * _EARTH_RADIUS_M
    c = math.cos(math.radians(lat0))

    def to_metres(lon: float, lat: float) -> tuple[float, float]:
        return ((lon - lon0) * k * c, (lat - lat0) * k)

    def to_lonlat(x: float, y: float) -> tuple[float, float]:
        return (lon0 + x / (k * c), lat0 + y / k)

    return to_metres, to_lonlat


def _local_metres(worlds: list[tuple[float, float]]):
    return _local_plane(worlds)[0]


def world_points(transformation: str, gcps, pixels: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Pixels on the image to WGS 84 (lon, lat) through the transform worked out from `gcps`
    ([(id, pixel, world), ...]) -- the same fit the residuals report on."""
    to_metres, to_lonlat = _local_plane([g[2] for g in gcps])
    forward = fit(transformation, [g[1] for g in gcps], [to_metres(*g[2]) for g in gcps])
    return [tuple(round(v, 9) for v in to_lonlat(float(x), float(y))) for x, y in forward(pixels)]


def inside_polygon(point: tuple[float, float], polygon: list[list[float]]) -> bool:
    """Even-odd rule; a point on an edge counts as inside."""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y):
            crossing = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x == crossing:
                return True
            if x < crossing:
                inside = not inside
    return inside


def _poly_terms(x, y, order: int):
    import numpy as np

    return np.column_stack([x ** i * y ** j for n in range(order + 1) for i in range(n + 1) for j in [n - i]])


def fit(transformation: str, sources: list[tuple[float, float]], targets: list[tuple[float, float]]):
    """A function mapping source points to target points, fitted by `transformation`.

    Least squares for the polynomials, helmert and projective; a thin-plate spline interpolates,
    so it is exact at its GCPs (its residuals are zero by construction -- that is the method,
    not a finding)."""
    import numpy as np

    if transformation not in MIN_GCPS:
        raise UnknownTransformation(f"{transformation!r} is not one of {', '.join(TRANSFORMATIONS)}")
    if len(sources) < MIN_GCPS[transformation]:
        raise TooFewControlPoints(transformation, len(sources))
    src = np.asarray(sources, dtype=float)
    dst = np.asarray(targets, dtype=float)
    # Normalise the sources: pixel coordinates cubed overflow the conditioning of a polynomial.
    mean, scale = src.mean(axis=0), max(float(np.abs(src - src.mean(axis=0)).max()), 1e-12)

    def norm(points):
        return (np.asarray(points, dtype=float).reshape(-1, 2) - mean) / scale

    s = norm(src)
    if transformation.startswith("polynomial-"):
        order = int(transformation.rsplit("-", 1)[1])
        coeffs, *_ = np.linalg.lstsq(_poly_terms(s[:, 0], s[:, 1], order), dst, rcond=None)
        return lambda p: _poly_terms(norm(p)[:, 0], norm(p)[:, 1], order) @ coeffs
    if transformation == "helmert":
        # x' = a x - b y + tx ; y' = b x + a y + ty -- a similarity, which cannot reflect. An
        # image's y runs DOWN and a map's north UP, so the source's y is turned round first
        # (otherwise the best "fit" is a rotation by half a turn, hundreds of metres off).
        flip = np.array([1.0, -1.0])
        f = s * flip
        rows = np.vstack([np.column_stack([f[:, 0], -f[:, 1], np.ones(len(f)), np.zeros(len(f))]),
                          np.column_stack([f[:, 1], f[:, 0], np.zeros(len(f)), np.ones(len(f))])])
        (a, b, tx, ty), *_ = np.linalg.lstsq(rows, np.concatenate([dst[:, 0], dst[:, 1]]), rcond=None)

        def helmert(p):
            q = norm(p) * flip
            return np.column_stack([a * q[:, 0] - b * q[:, 1] + tx, b * q[:, 0] + a * q[:, 1] + ty])
        return helmert
    if transformation == "projective":
        rows, rhs = [], []
        for (x, y), (u, v) in zip(s, dst):
            rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); rhs.append(u)
            rows.append([0, 0, 0, x, y, 1, -v * x, -v * y]); rhs.append(v)
        h, *_ = np.linalg.lstsq(np.asarray(rows), np.asarray(rhs), rcond=None)

        def projective(p):
            q = norm(p)
            w = h[6] * q[:, 0] + h[7] * q[:, 1] + 1
            return np.column_stack([(h[0] * q[:, 0] + h[1] * q[:, 1] + h[2]) / w,
                                    (h[3] * q[:, 0] + h[4] * q[:, 1] + h[5]) / w])
        return projective
    # thin-plate spline: U(r) = r^2 log r^2, plus an affine part
    n = len(s)

    def kernel(a, b):
        r2 = ((a[:, None, :] - b[None, :, :]) ** 2).sum(-1)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(r2 > 0, r2 * np.log(r2), 0.0)

    P = np.column_stack([np.ones(n), s])
    system = np.zeros((n + 3, n + 3))
    system[:n, :n], system[:n, n:], system[n:, :n] = kernel(s, s), P, P.T
    weights = np.linalg.solve(system, np.vstack([dst, np.zeros((3, 2))]))
    return lambda p: kernel(norm(p), s) @ weights[:n] + np.column_stack([np.ones(len(norm(p))), norm(p)]) @ weights[n:]


class ControlPointResidual(BaseModel):
    segment_id: str
    #: The pixel end (in the image's pixels) and the world end (WGS 84 lon, lat).
    pixel: list[float]
    world: list[float]
    #: How far the fitted transform misses this GCP: on the ground (metres), and on the image
    #: (pixels, through the inverse fit of the same type).
    residual_m: float
    residual_px: float


class WorkedOutTransform(BaseModel):
    """A georeferencing pass's transform as worked out now. Never stored as the truth: a caller
    that caches it keys the cache on `gcp_set_version`, which changes when any GCP does."""

    pass_id: str
    mask_id: str | None = None
    transformation: str
    gcp_set_version: str
    gcps: list[ControlPointResidual]
    rms_m: float
    rms_px: float
    #: GCPs left out, and why (a place held as `unknown`, no counted world end).
    not_used: list[dict[str, str]] = []


def residuals(transformation: str, gcps: list[tuple[str, tuple[float, float], tuple[float, float]]]):
    """Each GCP's residual in metres and pixels under `transformation`: [(id, pixel, world), ...]."""
    import math

    import numpy as np

    pixels = [g[1] for g in gcps]
    to_metres = _local_metres([g[2] for g in gcps])
    metres = [to_metres(*g[2]) for g in gcps]
    forward = fit(transformation, pixels, metres)
    backward = fit(transformation, metres, pixels)
    miss_m = np.linalg.norm(forward(pixels) - np.asarray(metres), axis=1)
    miss_px = np.linalg.norm(backward(metres) - np.asarray(pixels), axis=1)
    rows = [
        ControlPointResidual(segment_id=g[0], pixel=list(g[1]), world=list(g[2]),
                             residual_m=round(float(m), 3), residual_px=round(float(px), 3))
        for g, m, px in zip(gcps, miss_m, miss_px)
    ]
    rms = lambda values: round(math.sqrt(sum(v * v for v in values) / len(values)), 3)  # noqa: E731
    return rows, rms([r.residual_m for r in rows]), rms([r.residual_px for r in rows])
