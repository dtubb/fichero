"""Stain flattening: the page's background is estimated on the lightness channel by a large morphological closing (an
ellipse of the long side / `kernel_divisor`, so a stain wider than the kernel stays in the estimate and ink thinner than it does
not), blurred, and the page is divided by it and rescaled to the paper's median (`image.enhance.stain-flattening`, #6195).
The colour channels are left alone."""
from __future__ import annotations

from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

STEP = "stain-flatten"
#: The background is estimated at this long side, then scaled back up.
_WORK_LONG_SIDE = 1000


class Params(BaseModel):
    kernel_divisor: int = Field(40, ge=20, le=80, description="The closing kernel is the page's long side divided by this.")
    strength: float = Field(1.0, ge=0.0, le=1.0, description="Blend of the flattened lightness with the original (1 is all flattened).")


def _paper(light: Any) -> float:
    """The median of the brightest 20 % of the lightness channel."""
    import numpy as np

    cut = np.percentile(light, 80)
    return float(np.median(light[light >= cut]))


def run(image: Image.Image, params: Params) -> tuple[Image.Image, dict[str, Any]]:
    account: dict[str, Any] = {"step": STEP, "kernel_divisor": params.kernel_divisor, "strength": params.strength}
    try:
        import cv2
        import numpy as np
    except ImportError:  # OpenCV is bundled; without it the page is returned as it was
        return image, account
    alpha = image.getchannel("A") if image.mode in {"RGBA", "LA"} else None
    lab = cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2LAB)
    light = lab[:, :, 0]
    height, width = light.shape
    scale = min(1.0, _WORK_LONG_SIDE / max(height, width))
    small = cv2.resize(light, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1.0 else light
    size = max(3, int(round(max(small.shape) / params.kernel_divisor)) | 1)
    closed = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
    closed = cv2.GaussianBlur(closed, (0, 0), max(1.0, size / 4))
    background = cv2.resize(closed, (width, height), interpolation=cv2.INTER_LINEAR) if scale < 1.0 else closed
    paper = _paper(light)
    flat = np.clip(light.astype("float32") / np.maximum(background.astype("float32"), 1.0) * paper, 0, 255)
    mixed = params.strength * flat + (1.0 - params.strength) * light.astype("float32")
    lab[:, :, 0] = np.clip(np.rint(mixed), 0, 255).astype("uint8")
    out = Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    account["paper"] = round(paper, 1)
    return out, account
