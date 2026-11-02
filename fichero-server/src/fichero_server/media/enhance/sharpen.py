"""Sharpen: the legacy unsharp mask, the page x `amount` minus its Gaussian blur x (`amount` - 1) at `sigma`
(`image.enhance.sharpen`, #6190)."""
from __future__ import annotations

from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

STEP = "sharpen"


class Params(BaseModel):
    amount: float = Field(1.5, ge=1.0, le=3.0, description="Weight of the page; the blur is weighted 1 - amount.")
    sigma: float = Field(3.0, ge=0.5, le=10.0, description="Blur radius in pixels.")


def run(image: Image.Image, params: Params) -> tuple[Image.Image, dict[str, Any]]:
    account: dict[str, Any] = {"step": STEP, "amount": params.amount, "sigma": params.sigma}
    try:
        import cv2
        import numpy as np
    except ImportError:
        return image, account
    alpha = image.getchannel("A") if image.mode in {"RGBA", "LA"} else None
    rgb = np.asarray(image.convert("RGB"))
    blur = cv2.GaussianBlur(rgb, (0, 0), float(params.sigma))
    out = Image.fromarray(cv2.addWeighted(rgb, float(params.amount), blur, 1.0 - float(params.amount), 0))
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    return out, account
