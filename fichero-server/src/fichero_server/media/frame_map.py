"""Where a point on the page's upright photograph lands on an edited copy of it (#6296).

Geometry is stored as fractions of the page's upright photograph (`media/upright.py`). A model is sent the page's CURRENT image
(`media/current_image.py`): the edit chain applied, or a rendition. When that copy is cropped, turned or squared, a line's
fractions are not fractions of it, so a line cut from it with them lands beside the ink. Every edit that moves pixels is a
projective map of pixels (crop, quarter turn, any angle, flip, a square from four corners): this module composes them, so lines
carry to the copy and what a step finds on the copy carries back.

An edit whose frame is not known (a flatten's displacement field, an op this module has never heard of) is `Unmappable`, never
guessed: the caller then reads lines on the photograph and says so.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

Size = tuple[float, float]
Points = list[list[float]]
Matrix = tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]

IDENTITY: Matrix = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

#: Edits that keep every pixel where it is.
_SAME_FRAME = frozenset({"brightness", "contrast", "sharpen", "auto_levels", "enhance", "fuzzy_clean", "denoise",
                         "adaptive_binarize", "grayscale", "segment", "remove_background"})
_TURNS = frozenset({"rotate", "straighten", "auto_deskew"})


class Unmappable(ValueError):
    """The frame of the edited copy against the photograph is not known."""


def _mul(a: Matrix, b: Matrix) -> Matrix:
    """`a` after `b` (apply b first)."""
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))  # type: ignore[return-value]


def _inv(m: Matrix) -> Matrix:
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(det) < 1e-12:
        raise Unmappable("an edit that flattens the page cannot be reversed")
    return (((e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det),
            ((f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det),
            ((d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det))


def _affine(a: float, b: float, c: float, d: float, e: float, f: float) -> Matrix:
    return ((a, b, c), (d, e, f), (0.0, 0.0, 1.0))


@dataclass(frozen=True)
class FrameMap:
    """The pixel map `m` from an image of size `src` to one of size `dst`."""

    src: Size
    dst: Size
    m: Matrix

    def pixels(self, x: float, y: float) -> tuple[float, float]:
        (a, b, c), (d, e, f), (g, h, i) = self.m
        w = g * x + h * y + i
        return (a * x + b * y + c) / w, (d * x + e * y + f) / w

    def carry(self, points: Any) -> Points:
        """Fractions of the source image as fractions of the destination."""
        out = []
        for x, y in points:
            px, py = self.pixels(float(x) * self.src[0], float(y) * self.src[1])
            out.append([px / self.dst[0], py / self.dst[1]])
        return out

    def carry_pixels(self, points: Any) -> Points:
        """Pixels of the source image as pixels of the destination."""
        return [list(self.pixels(float(x), float(y))) for x, y in points]

    def carry_rect(self, rect: Any) -> list[float]:
        """A fractional [x, y, w, h] as the box that holds its four carried corners."""
        x, y, w, h = (float(v) for v in rect)
        moved = self.carry([[x, y], [x + w, y], [x + w, y + h], [x, y + h]])
        xs, ys = [p[0] for p in moved], [p[1] for p in moved]
        return [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]

    def inverse(self) -> "FrameMap":
        return FrameMap(self.dst, self.src, _inv(self.m))

    def with_size(self, dst: Size) -> "FrameMap":
        """The same map onto a picture whose real size is `dst` (the size worked out here can be a pixel off a file's)."""
        sx, sy = dst[0] / self.dst[0], dst[1] / self.dst[1]
        return FrameMap(self.src, dst, _mul(_affine(sx, 0, 0, 0, sy, 0), self.m))

    def then(self, other: "FrameMap") -> "FrameMap":
        return FrameMap(self.src, other.dst, _mul(other.m, self.m))


def identity(size: Size) -> FrameMap:
    return FrameMap(size, size, IDENTITY)


def exif_map(orientation: int, raw: Size) -> FrameMap:
    """The page's raw pixels (orientation tag not applied) to its upright pixels, as `ImageOps.exif_transpose` makes them."""
    w, h = raw
    table: dict[int, tuple[Matrix, Size]] = {
        2: (_affine(-1, 0, w, 0, 1, 0), (w, h)),
        3: (_affine(-1, 0, w, 0, -1, h), (w, h)),
        4: (_affine(1, 0, 0, 0, -1, h), (w, h)),
        5: (_affine(0, 1, 0, 1, 0, 0), (h, w)),
        6: (_affine(0, -1, h, 1, 0, 0), (h, w)),
        7: (_affine(0, -1, h, -1, 0, w), (h, w)),
        8: (_affine(0, 1, 0, -1, 0, w), (h, w)),
    }
    move, dst = table.get(int(orientation or 1), (IDENTITY, (w, h)))
    return FrameMap(raw, dst, move)


def crop_map(size: Size, left: float, top: float, width: float, height: float) -> FrameMap:
    right, bottom = min(left + width, size[0]), min(top + height, size[1])
    if width <= 0 or height <= 0 or left < 0 or top < 0 or right <= left or bottom <= top:
        raise Unmappable("a crop outside the page")
    return FrameMap(size, (right - left, bottom - top), _affine(1, 0, -left, 0, 1, -top))


def box_map(size: Size, box: Any, dst: Size) -> FrameMap:
    """The crop of the fractional `box` [x, y, w, h] of an image of `size`, as a picture of `dst` pixels."""
    bx, by, bw, bh = (float(v) for v in box)
    if bw <= 0 or bh <= 0:
        raise Unmappable("a crop with no area")
    sx, sy = dst[0] / (bw * size[0]), dst[1] / (bh * size[1])
    return FrameMap(size, dst, _affine(sx, 0, -bx * size[0] * sx, 0, sy, -by * size[1] * sy))


def turn_map(size: Size, angle: float, expand: bool = True) -> FrameMap:
    """A counter-clockwise turn as `Image.rotate` / `Image.transpose` make it (a quarter turn is exact)."""
    w, h = size
    quarter = angle % 360
    exact: dict[float, tuple[Matrix, Size]] = {
        0.0: (IDENTITY, (w, h)), 90.0: (_affine(0, 1, 0, -1, 0, w), (h, w)),
        180.0: (_affine(-1, 0, w, 0, -1, h), (w, h)), 270.0: (_affine(0, -1, h, 1, 0, 0), (h, w))}
    if quarter in exact:
        move, dst = exact[quarter]
        return FrameMap(size, dst, move)
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    nw, nh = ((math.ceil(round(abs(w * c) + abs(h * s), 6)), math.ceil(round(abs(w * s) + abs(h * c), 6)))
              if expand else (w, h))
    # about the old centre, then onto the new one (PIL's counter-clockwise turn, y down)
    move = _affine(c, s, -(w / 2) * c - (h / 2) * s + nw / 2, -s, c, (w / 2) * s - (h / 2) * c + nh / 2)
    return FrameMap(size, (nw, nh), move)


def homography_map(size: Size, homography: Any, dst: Size) -> FrameMap:
    """A recorded 3x3 homography (photograph pixels to squared pixels, `media/square_page.py`)."""
    rows = tuple(tuple(float(v) for v in row) for row in homography)
    if len(rows) != 3 or any(len(row) != 3 for row in rows):
        raise Unmappable("a homography that is not 3 x 3")
    return FrameMap(size, dst, rows)  # type: ignore[arg-type]


def _step(op: dict[str, Any], size: Size, image: Any | None) -> FrameMap:
    from fichero_server.media.image_ops import detect_content_bbox, detect_deskew_angle

    name = str(op.get("op", "")).strip().lower()
    params = op.get("params") or {}
    if name in _SAME_FRAME:
        return identity(size)
    if name == "crop":
        return crop_map(size, float(params["left"]), float(params["top"]), float(params["width"]), float(params["height"]))
    if name in _TURNS:
        if name == "auto_deskew" and "angle" not in params:
            if image is None:
                raise Unmappable("an automatic straighten whose angle is not recorded")
            angle = detect_deskew_angle(image)
        else:
            angle = float(params.get("angle", 0))
        return turn_map(size, angle, bool(params.get("expand", True)))
    if name == "flip_horizontal":
        return FrameMap(size, size, _affine(-1, 0, size[0], 0, 1, 0))
    if name == "flip_vertical":
        return FrameMap(size, size, _affine(1, 0, 0, 0, -1, size[1]))
    if name == "auto_crop_border":
        if image is None:
            raise Unmappable("an automatic crop whose box is not recorded")
        return crop_map(size, *(float(v) for v in detect_content_bbox(image)))
    raise Unmappable(f"the edit '{name}' has no known effect on the page's frame")


def _pixel_dependent(op: dict[str, Any]) -> bool:
    name = str(op.get("op", "")).strip().lower()
    return name in ("auto_crop_border", "remove_background") or (
        name == "auto_deskew" and "angle" not in (op.get("params") or {}))


def chain_map(size: Size, operations: list[dict[str, Any]], load: Callable[[], Any]) -> FrameMap:
    """The map from the upright photograph (`size`) to the chain's result. `load` gives the upright photograph, called only
    when an edit's geometry depends on its pixels (the chain is then replayed beside the map)."""
    from fichero_server.media.image_ops import apply_operation

    image = load() if any(_pixel_dependent(op) for op in operations) else None
    whole = identity(size)
    for op in operations:
        whole = whole.then(_step(op, whole.dst, image))
        if image is not None:
            after = apply_operation(image, op)
            if after.size != image.size and str(op.get("op", "")).strip().lower() == "remove_background":
                raise Unmappable("a background removal that cropped the page")  # its box is not recorded
            image = after
    return whole
