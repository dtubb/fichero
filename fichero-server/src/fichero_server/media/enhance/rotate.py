"""Rotate: a quarter turn is a lossless transpose, any other angle is one bicubic resample, white fill (`image.enhance.rotate-deskew`).

The editor's `rotate` row, the `rotate_images` node and `deskew` all turn pixels here. Positive angles turn counter-clockwise
(PIL's convention)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from PIL import Image

STEP = "rotate"


class Params(BaseModel):
    angle: float = Field(ge=-360.0, le=360.0)
    expand: bool = True


def run(image: Image.Image, params: Params) -> tuple[Image.Image, dict[str, Any]]:
    """The image turned by `params.angle`. Exact quarter turns are transposes (an earlier version resampled every click and
    softened the page); the account says which."""
    from PIL import Image  # lazy: PIL stays off the engine boot path (#3950)
    angle = float(params.angle)
    quarter = angle % 360
    account: dict[str, Any] = {"step": "rotate", "angle": angle, "expand": params.expand}
    if quarter in (0.0, 90.0, 180.0, 270.0):
        method = {90.0: Image.Transpose.ROTATE_90, 180.0: Image.Transpose.ROTATE_180, 270.0: Image.Transpose.ROTATE_270}.get(quarter)
        return (image.transpose(method) if method is not None else image), {**account, "method": "quarter-turn"}
    turned = image.rotate(angle, expand=params.expand, resample=Image.Resampling.BICUBIC, fillcolor="white")
    return turned, {**account, "method": "rotate"}
