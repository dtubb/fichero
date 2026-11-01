"""Deskew: the page's text-line tilt measured (Hough median, `media.image_ops.detect_deskew_angle`) and the page turned back
by `rotate.run`. A tilt under `STRAIGHTEN_MIN_DEGREES` leaves the page as it was (`image.enhance.rotate-deskew`)."""
from __future__ import annotations

from typing import Any

from PIL import Image
from pydantic import BaseModel

from fichero_server.media.enhance import rotate

STEP = "deskew"


class Params(BaseModel):
    """No tunables yet: the threshold is `image_ops.STRAIGHTEN_MIN_DEGREES`."""


def measure(image: Image.Image, params: Params) -> float:
    """The angle to turn by: the Hough skew, or 0.0 under the minimum. The node records it on its row without turning pixels."""
    from fichero_server.media.image_ops import auto_straighten_angle

    return auto_straighten_angle(image)


def run(image: Image.Image, params: Params) -> tuple[Image.Image, dict[str, Any]]:
    angle = measure(image, params)
    account: dict[str, Any] = {"step": "deskew", "angle": angle, "method": "hough"}
    if not angle:
        return image, account
    turned, _ = rotate.run(image, rotate.Params(angle=angle, expand=True))
    return turned, account
