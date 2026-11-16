"""Binarise: black and white by Otsu's global threshold or a Gaussian adaptive threshold (`image.enhance.binarise`, #6185).
The old `adaptive_binarize` operation (a global mean threshold) stays as it was for the chain rows that carry it."""
from __future__ import annotations

from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel, Field

STEP = "binarise"


class Params(BaseModel):
    method: Literal["otsu", "adaptive"] = "adaptive"
    block: int = Field(31, ge=11, le=101, description="Adaptive neighbourhood in pixels; an even value is used as the next odd one.")
    c: int = Field(2, ge=-10, le=10, description="Subtracted from the adaptive local mean; larger keeps less ink.")


def run(image: Image.Image, params: Params) -> tuple[Image.Image, dict[str, Any]]:
    block = int(params.block) | 1
    account: dict[str, Any] = {"step": STEP, "method": params.method, "block": block, "c": params.c}
    try:
        import cv2
        import numpy as np
    except ImportError:  # OpenCV is bundled; without it the page is returned as it was
        return image, account
    gray = np.asarray(image.convert("L"))
    if params.method == "otsu":
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    else:
        binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, params.c)
    return Image.fromarray(binary).convert("RGB"), account
