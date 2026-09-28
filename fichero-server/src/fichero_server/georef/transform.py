"""The transform from an image to the world, WORKED OUT from control points and never stored
(`source.geo.transform-is-derived`).

Image points are the anchor's normalised ``[x, y]``; world points are WGS 84 ``(lon, lat)``. Fitting
happens in Web Mercator metres (EPSG:3857, a closed formula, no PROJ), which is what Allmaps does, so
a polynomial means the same here as in the files we read and write. Residuals are measured back in
WGS 84 as great-circle metres (`source.geo.residuals`), and in the image through the inverse fit.

Pure: numbers in, numbers out. `api/routes/document/georef.py` reads the records and answers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

_R = 6378137.0  # the WGS 84 semi-major axis Web Mercator uses

#: Each type the spec names (`source.geo.transformation-type`) and the fewest control points it needs.
NEEDED: dict[str, int] = {
    "helmert": 2,
    "polynomial1": 3,  # affine; the default, and what a world file can hold
    "projective": 4,
    "polynomial2": 6,
    "polynomial3": 10,
    "thin_plate_spline": 3,
}
DEFAULT_TYPE = "polynomial1"


class TooFew(ValueError):
    def __init__(self, kind: str, have: int):
        self.kind, self.have, self.needed = kind, have, NEEDED[kind]
        super().__init__(f"{kind} needs {self.needed} control points with a known place; this pass has {have}")


def to_mercator(lon: float, lat: float) -> tuple[float, float]:
    lat = max(min(lat, 85.05112878), -85.05112878)
    return _R * math.radians(lon), _R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def from_mercator(x: float, y: float) -> tuple[float, float]:
    return math.degrees(x / _R), math.degrees(2 * math.atan(math.exp(y / _R)) - math.pi / 2)


def metres_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance between two (lon, lat), haversine on the mean earth radius."""
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1.0, h)))


def _monomials(pts: np.ndarray, order: int) -> np.ndarray:
    x, y = pts[:, 0], pts[:, 1]
    return np.column_stack([x ** (i - j) * y ** j for i in range(order + 1) for j in range(i + 1)])


def _tps_kernel(r2: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(r2 > 0, r2 * np.log(r2), 0.0)


@dataclass
class Fit:
    """One direction of a fitted transform, applied to many points at once."""

    kind: str
    src_shift: np.ndarray
    src_scale: float
    dst_shift: np.ndarray
    dst_scale: float
    params: np.ndarray
    ctrl: np.ndarray | None = None  # the thin-plate spline's own control points (normalised)

    def __call__(self, pts) -> np.ndarray:
        p = (np.asarray(pts, dtype=float).reshape(-1, 2) - self.src_shift) / self.src_scale
        if self.kind.startswith("polynomial"):
            out = _monomials(p, int(self.kind[-1])) @ self.params
        elif self.kind == "helmert":
            a, b, tx, ty = self.params
            out = np.column_stack([a * p[:, 0] - b * p[:, 1] + tx, b * p[:, 0] + a * p[:, 1] + ty])
        elif self.kind == "projective":
            h = np.append(self.params, 1.0).reshape(3, 3)
            hom = np.column_stack([p, np.ones(len(p))]) @ h.T
            out = hom[:, :2] / hom[:, 2:3]
        else:
            r2 = ((p[:, None, :] - self.ctrl[None, :, :]) ** 2).sum(-1)
            out = np.column_stack([_tps_kernel(r2), np.ones(len(p)), p]) @ self.params
        return out * self.dst_scale + self.dst_shift


def fit(kind: str, src, dst) -> Fit:
    """Fit ``src -> dst`` by least squares (exactly, for a thin-plate spline). Both sides are centred
    and scaled first, so a cubic over Mercator metres is not ill-conditioned."""
    if kind not in NEEDED:
        raise ValueError(f"unknown transformation type {kind!r}; one of {sorted(NEEDED)}")
    src, dst = np.asarray(src, dtype=float), np.asarray(dst, dtype=float)
    if len(src) < NEEDED[kind]:
        raise TooFew(kind, len(src))
    s_shift, d_shift = src.mean(0), dst.mean(0)
    s_scale = float(np.abs(src - s_shift).max()) or 1.0
    d_scale = float(np.abs(dst - d_shift).max()) or 1.0
    s, d = (src - s_shift) / s_scale, (dst - d_shift) / d_scale
    ctrl = None
    if kind.startswith("polynomial"):
        params = np.linalg.lstsq(_monomials(s, int(kind[-1])), d, rcond=None)[0]
    elif kind == "helmert":
        rows = np.vstack([np.column_stack([s[:, 0], -s[:, 1], np.ones(len(s)), np.zeros(len(s))]),
                          np.column_stack([s[:, 1], s[:, 0], np.zeros(len(s)), np.ones(len(s))])])
        params = np.linalg.lstsq(rows, np.concatenate([d[:, 0], d[:, 1]]), rcond=None)[0]
    elif kind == "projective":
        x, y, u, v = s[:, 0], s[:, 1], d[:, 0], d[:, 1]
        one, zero = np.ones(len(s)), np.zeros(len(s))
        rows = np.vstack([np.column_stack([x, y, one, zero, zero, zero, -u * x, -u * y]),
                          np.column_stack([zero, zero, zero, x, y, one, -v * x, -v * y])])
        params = np.linalg.lstsq(rows, np.concatenate([u, v]), rcond=None)[0]
    else:
        n = len(s)
        k = _tps_kernel(((s[:, None, :] - s[None, :, :]) ** 2).sum(-1))
        p = np.column_stack([np.ones(n), s])
        system = np.block([[k, p], [p.T, np.zeros((3, 3))]])
        params = np.linalg.lstsq(system, np.vstack([d, np.zeros((3, 2))]), rcond=None)[0]
        ctrl = s
    return Fit(kind, s_shift, s_scale, d_shift, d_scale, params, ctrl)


@dataclass
class Georeference:
    """A fitted pass: image -> world and back, and each control point's residual."""

    forward: Fit
    inverse: Fit
    residuals_m: list[float]
    #: Per point, (dx, dy) in the image's normalised units: the inverse fit's miss.
    residuals_image: list[tuple[float, float]]

    def to_world(self, image_pts) -> list[tuple[float, float]]:
        return [from_mercator(x, y) for x, y in self.forward(image_pts)]


def georeference(kind: str, image_pts, world_pts) -> Georeference:
    """``image_pts`` normalised [x, y]; ``world_pts`` (lon, lat) WGS 84, one per control point."""
    merc = [to_mercator(lon, lat) for lon, lat in world_pts]
    forward, inverse = fit(kind, image_pts, merc), fit(kind, merc, image_pts)
    predicted = [from_mercator(x, y) for x, y in forward(image_pts)]
    back = inverse(merc)
    return Georeference(
        forward, inverse,
        residuals_m=[metres_between(p, tuple(w)) for p, w in zip(predicted, world_pts)],
        residuals_image=[(float(b[0] - i[0]), float(b[1] - i[1])) for b, i in zip(back, image_pts)],
    )


def inside(point, ring) -> bool:
    """Even-odd ray cast: is ``point`` inside the closed ``ring`` of [x, y]?"""
    x, y = point
    hit = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            hit = not hit
    return hit
