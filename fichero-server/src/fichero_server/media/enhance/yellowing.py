"""Yellowing: the legacy `DocumentEnhancer.enhance` step 2. The cast is (mean LAB b - 128) / 30 clamped to 0-1; where it is over
0.1 (or `strength` is given) b is lowered by `strength` (auto: min(8, 3 x cast)) and a is scaled by `desaturate_a`
(`image.enhance.yellowing`, #6190)."""
from __future__ import annotations

from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

STEP = "yellowing"
#: The cast under which a page is not yellowed and an auto strength writes nothing.
CAST_FLOOR = 0.1


class Params(BaseModel):
    strength: float | None = Field(None, ge=0.0, le=8.0, description="The subtraction in LAB b; empty is min(8, 3 x cast).")
    desaturate_a: float = Field(0.98, ge=0.9, le=1.0, description="The factor on LAB a.")


def cast_of(image: Image.Image) -> float:
    """The yellow cast of a page, 0-1, from the mean of LAB b."""
    import cv2
    import numpy as np

    lab = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2LAB)
    return float(min(1.0, max(0.0, (float(lab[:, :, 2].mean()) - 128.0) / 30.0)))


def run(image: Image.Image, params: Params) -> tuple[Image.Image, dict[str, Any]]:
    account: dict[str, Any] = {"step": STEP, "applied": False}
    try:
        import cv2
        import numpy as np
    except ImportError:  # OpenCV is bundled; without it the page is returned as it was
        return image, account
    alpha = image.getchannel("A") if image.mode in {"RGBA", "LA"} else None
    rgb = np.asarray(image.convert("RGB"))
    cast = cast_of(image)
    account["cast"] = round(cast, 3)
    if params.strength is None and cast <= CAST_FLOOR:
        return image, account
    strength = float(params.strength) if params.strength is not None else min(8.0, 3.0 * cast)
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    b = lab[:, :, 2].astype("float32") - strength
    lab[:, :, 2] = np.clip(np.rint(b), 0, 255).astype("uint8")
    lab[:, :, 1] = cv2.convertScaleAbs(lab[:, :, 1], alpha=float(params.desaturate_a), beta=0)
    out = Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    account.update(applied=True, strength=strength, desaturate_a=float(params.desaturate_a))
    return out, account
