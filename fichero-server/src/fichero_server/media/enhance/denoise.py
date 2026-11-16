"""Denoise: `cv2.medianBlur` (radius 3 or 5), then specks off the ink mask: an ink blob whose box fits inside `speck` x `speck`
pixels is filled from the paper around it, and strokes longer than that stay (`image.enhance.denoise`, #6185)."""
from __future__ import annotations

from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

STEP = "denoise"


class Params(BaseModel):
    radius: int = Field(3, ge=3, le=5, description="Median filter size (3 or 5; 4 and above 5 read as 5).")
    speck: int = Field(5, ge=0, le=9, description="Ink blobs no larger than this many pixels each way are removed; 0 is off.")


def run(image: Image.Image, params: Params) -> tuple[Image.Image, dict[str, Any]]:
    size = 5 if params.radius >= 4 else 3
    account: dict[str, Any] = {"step": STEP, "radius": size, "speck": params.speck, "specks_removed": 0}
    try:
        import cv2
        import numpy as np
    except ImportError:  # OpenCV is bundled; without it the PIL median runs and no specks are removed
        from PIL import ImageFilter

        account["specks_removed"] = None
        return image.convert("RGB").filter(ImageFilter.MedianFilter(size=size)), account
    alpha = image.getchannel("A") if image.mode in {"RGBA", "LA"} else None
    rgb = cv2.medianBlur(np.asarray(image.convert("RGB")), size)
    if params.speck:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        _, ink = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
        count, labels, stats, _centres = cv2.connectedComponentsWithStats(ink, connectivity=8)
        small = [i for i in range(1, count)
                 if stats[i, cv2.CC_STAT_WIDTH] <= params.speck and stats[i, cv2.CC_STAT_HEIGHT] <= params.speck]
        if small:
            mask = np.isin(labels, small).astype("uint8") * 255
            rgb = cv2.inpaint(rgb, cv2.dilate(mask, np.ones((3, 3), "uint8")), 3, cv2.INPAINT_TELEA)
            account["specks_removed"] = len(small)
    out = Image.fromarray(rgb)
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    return out, account
