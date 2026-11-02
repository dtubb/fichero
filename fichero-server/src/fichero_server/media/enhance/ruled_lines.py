"""Ruled lines: coloured ruling is found by an HSV hue mask (green, blue or red), kept where it is thin (under `max_width`
px) and long (a run over `min_length` of the page's side, horizontal or vertical), and filled from the surrounding paper by
`cv2.inpaint`. Pixels that are dark are never filled, so the ink crossing a rule is unchanged (`image.enhance.ruled-lines`,
#6195). Grey ruling is not handled."""
from __future__ import annotations

from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel, Field

STEP = "ruled-lines"
#: OpenCV hue (0-179) bands of the three colours.
_BANDS = {"green": [(35, 90)], "blue": [(90, 135)], "red": [(0, 10), (170, 180)]}
#: A ruling pixel is at least this saturated and this bright; anything darker is ink.
_MIN_SATURATION, _MIN_VALUE = 40, 90
#: Under this many ruling pixels a colour is not present on the page.
_MIN_PIXELS = 200


class Params(BaseModel):
    colour: Literal["auto", "green", "blue", "red", "none"] = Field("auto", description="Which ruling colour; auto takes the colour with most ruling.")
    max_width: int = Field(3, ge=1, le=10, description="Ruling is thinner than this, in pixels.")
    min_length: float = Field(0.3, ge=0.1, le=1.0, description="Ruling is longer than this fraction of the page's side.")
    inpaint_radius: int = Field(3, ge=1, le=10)


def _ruling(hsv: Any, colour: str, params: Params) -> Any:
    """The boolean mask of thin, long ruling of one colour."""
    import cv2
    import numpy as np

    hue = hsv[:, :, 0]
    band = np.zeros(hue.shape, bool)
    for low, high in _BANDS[colour]:
        band |= (hue >= low) & (hue < high)
    mask = (band & (hsv[:, :, 1] >= _MIN_SATURATION) & (hsv[:, :, 2] >= _MIN_VALUE)).astype("uint8")
    height, width = mask.shape
    keep = np.zeros_like(mask)
    horizontal, vertical = int(width * params.min_length), int(height * params.min_length)
    if horizontal >= 3:  # a gap where ink crosses a rule is bridged before the length is judged
        bridged = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((1, 9), "uint8"))
        keep |= cv2.morphologyEx(bridged, cv2.MORPH_OPEN, np.ones((1, horizontal), "uint8"))
    if vertical >= 3:
        bridged = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 1), "uint8"))
        keep |= cv2.morphologyEx(bridged, cv2.MORPH_OPEN, np.ones((vertical, 1), "uint8"))
    thick = cv2.morphologyEx(keep, cv2.MORPH_OPEN, np.ones((params.max_width + 1, params.max_width + 1), "uint8"))
    return (keep & ~thick).astype(bool) & mask.astype(bool)


def run(image: Image.Image, params: Params) -> tuple[Image.Image, dict[str, Any]]:
    account: dict[str, Any] = {"step": STEP, "colour": params.colour, "max_width": params.max_width, "pixels": 0}
    if params.colour == "none":
        return image, account
    try:
        import cv2
        import numpy as np
    except ImportError:
        return image, account
    alpha = image.getchannel("A") if image.mode in {"RGBA", "LA"} else None
    rgb = np.asarray(image.convert("RGB"))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    colours = list(_BANDS) if params.colour == "auto" else [params.colour]
    found = {c: _ruling(hsv, c, params) for c in colours}
    best = max(found, key=lambda c: int(found[c].sum()))
    mask = found[best]
    if int(mask.sum()) < _MIN_PIXELS:
        return image, account
    # the anti-aliased edge of a rule: one pixel out, but never onto ink
    wide = cv2.dilate(mask.astype("uint8"), np.ones((3, 3), "uint8")).astype(bool) & (hsv[:, :, 2] >= _MIN_VALUE)
    filled = cv2.inpaint(rgb, wide.astype("uint8") * 255, int(params.inpaint_radius), cv2.INPAINT_TELEA)
    out = Image.fromarray(filled)
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    account.update(colour=best, pixels=int(wide.sum()))
    return out, account
