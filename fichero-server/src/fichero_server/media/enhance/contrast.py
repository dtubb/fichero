"""Contrast: local contrast on the lightness channel (CLAHE, `media.image_ops.apply_clahe_contrast`) or, where no CLAHE field is set,
the old `factor` as PIL's global contrast (`image.enhance.contrast-clahe`)."""
from __future__ import annotations

from typing import Any, Literal

from PIL import Image, ImageEnhance
from pydantic import BaseModel, Field

STEP = "contrast"
#: Any of these makes the row the CLAHE step; `factor` alone keeps the old PIL contrast.
CLAHE_FIELDS = ("clip", "tile", "gain", "lift", "profile")


class Params(BaseModel):
    """`factor` is the old PIL contrast; any of the rest makes it the CLAHE step (`image.enhance.contrast-clahe`)."""

    factor: float = Field(1.0, ge=0.0, le=10.0)
    clip: float | None = Field(None, ge=1.0, le=4.0)
    tile: int | None = Field(None, ge=4, le=16)
    gain: float | None = Field(None, ge=0.8, le=1.4)
    lift: float | None = Field(None, ge=-20.0, le=20.0)
    profile: Literal["handwritten", "typescript"] | None = None


def run(image: Image.Image, params: Params) -> tuple[Image.Image, dict[str, Any]]:
    # A row that names any CLAHE field (even as null) is the CLAHE step, null meaning the profile's default: how the chain has always read it.
    if params.model_fields_set & set(CLAHE_FIELDS):
        given = {k: getattr(params, k) for k in CLAHE_FIELDS if getattr(params, k) is not None}
        from fichero_server.media.image_ops import apply_clahe_contrast

        return apply_clahe_contrast(image, **given), {"step": "contrast", "method": "clahe", **given}
    return (ImageEnhance.Contrast(image).enhance(float(params.factor)),
            {"step": "contrast", "method": "pil-contrast", "factor": float(params.factor)})
