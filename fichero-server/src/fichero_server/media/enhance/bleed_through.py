"""Bleed-through (show-through) suppression (`image.enhance.bleed-through-suppression`, #6196). The original is never written.

Method A needs only the page. The paper is estimated per colour channel by a closing (an ellipse of the long side /
`window_divisor`) at a working size; a pixel is ink where it is darker than the paper by more than `k` x the page's ink
darkness (the 99.5th percentile of that darkness). Ink, and one pixel around it, is kept exactly; every other pixel is set to
the paper estimate, so faint mirrored writing goes to paper and strokes are not thinned.

Method B also takes the verso scan: it is mirrored, registered to the recto with `cv2.findTransformECC` (affine, on a
downsampled pair), and its darkness, times a gain fitted on the pixels under its ink, is taken from the recto where the recto
is not ink. Where the registration does not converge the page is returned unchanged and the account says why."""
from __future__ import annotations

from typing import Any, Literal

from PIL import Image
from pydantic import BaseModel, Field

STEP = "bleed-through"
_WORK_LONG_SIDE = 1000
_ECC_LONG_SIDE = 500


class Params(BaseModel):
    method: Literal["a", "b"] = Field("a", description="a: the page alone. b: the page and its verso (mirrored, registered, subtracted).")
    k: float = Field(0.25, ge=0.0, le=0.5, description="A mark lighter than this fraction of the page's ink darkness is show-through.")
    window_divisor: int = Field(60, ge=20, le=120, description="The paper estimate's closing kernel is the long side divided by this.")
    gain: float | None = Field(None, ge=0.0, le=1.0, description="Method b: the verso's share seen through; empty fits it.")
    verso_path: str | None = Field(None, description="Method b: the verso image file, when it is not handed to `run`.")


def _paper(rgb: Any, divisor: int) -> Any:
    """The paper under the ink: a closing per channel, blurred, at a working size and scaled back up (float32, H x W x 3)."""
    import cv2
    import numpy as np

    height, width = rgb.shape[:2]
    scale = min(1.0, _WORK_LONG_SIDE / max(height, width))
    small = cv2.resize(rgb, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1.0 else rgb
    size = max(3, int(round(max(small.shape[:2]) / divisor)) | 1)
    closed = cv2.morphologyEx(small, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
    closed = cv2.GaussianBlur(closed, (0, 0), max(1.0, size / 4))
    if scale < 1.0:
        closed = cv2.resize(closed, (width, height), interpolation=cv2.INTER_LINEAR)
    return closed.astype(np.float32)


def _darkness(rgb: Any, paper: Any) -> Any:
    """How far each pixel is under the paper, on the grey of the page (float32, H x W)."""
    import cv2
    import numpy as np

    grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    paper_grey = cv2.cvtColor(np.clip(paper, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    return paper_grey - grey


def register_verso(recto_grey: Any, verso_grey: Any) -> tuple[Any, Any] | None:
    """The 2 x 3 affine matrix taking the MIRRORED verso onto the recto (ECC on a downsampled pair) and that mirrored verso, or None
    where it does not converge."""
    import cv2
    import numpy as np

    height, width = recto_grey.shape
    scale = min(1.0, _ECC_LONG_SIDE / max(height, width))
    mirrored = cv2.flip(cv2.resize(verso_grey, (width, height), interpolation=cv2.INTER_AREA), 1)

    def prep(grey: Any, factor: float) -> Any:
        small = cv2.resize(grey, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA) if factor < 1.0 else grey
        return cv2.GaussianBlur(small.astype(np.float32), (0, 0), 2.0)

    warp = np.eye(2, 3, dtype=np.float32)
    try:
        for factor in (scale * 0.5, scale):  # coarse, then fine
            warp[:, 2] *= 1.0 if factor == scale * 0.5 else 2.0
            _, warp = cv2.findTransformECC(prep(recto_grey, factor), prep(mirrored, factor), warp, cv2.MOTION_AFFINE,
                                           (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-5), None, 5)
    except cv2.error:
        return None
    warp[:, 2] /= scale  # translation back to the full size
    return warp, mirrored


def run(image: Image.Image, params: Params, verso: Image.Image | None = None) -> tuple[Image.Image, dict[str, Any]]:
    account: dict[str, Any] = {"step": STEP, "method": params.method, "k": params.k, "applied": False}
    try:
        import cv2
        import numpy as np
    except ImportError:  # OpenCV is bundled; without it the page is returned as it was
        return image, account
    alpha = image.getchannel("A") if image.mode in {"RGBA", "LA"} else None
    rgb = np.asarray(image.convert("RGB"))
    paper = _paper(rgb, params.window_divisor)
    dark = _darkness(rgb, paper)
    ink_level = float(np.percentile(dark, 99.5))
    if ink_level <= 8.0:  # no ink to tell show-through from
        return image, account
    ink = dark > params.k * ink_level
    out = rgb.astype(np.float32)
    if params.method == "a":
        keep = cv2.dilate(ink.astype("uint8"), np.ones((3, 3), "uint8")).astype(bool)
        out = np.where(keep[:, :, None], out, paper)
        account["ink_level"] = round(ink_level, 1)
    else:
        if verso is None and params.verso_path:
            with Image.open(params.verso_path) as opened:
                verso = opened.convert("RGB")
        if verso is None:
            account["reason"] = "no verso"
            return image, account
        verso_rgb = np.asarray(verso.convert("RGB"))
        verso_dark = _darkness(verso_rgb, _paper(verso_rgb, params.window_divisor))
        # both are registered as darkness (same polarity), the recto's without its own ink
        found = register_verso(np.clip(np.where(ink, 0.0, dark), 0, 255).astype("uint8"), np.clip(verso_dark, 0, 255).astype("uint8"))
        if found is None:
            account["reason"] = "the verso did not register"
            return image, account
        warp, mirrored = found
        height, width = dark.shape
        aligned = cv2.warpAffine(mirrored.astype(np.float32), warp, (width, height),
                                 flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderValue=0)
        under_verso_ink = (aligned > 0.5 * float(np.percentile(aligned, 99.5))) & ~ink
        if params.gain is not None:
            gain = float(params.gain)
        elif int(under_verso_ink.sum()) >= 50:
            gain = float(np.clip(np.median(dark[under_verso_ink] / np.maximum(aligned[under_verso_ink], 1.0)), 0.0, 1.0))
        else:
            account["reason"] = "no pixel of the verso's ink lies on bare recto"
            return image, account
        lift = np.where(ink, 0.0, gain * aligned)  # ink is not touched
        out = out + lift[:, :, None]
        account["gain"] = round(gain, 3)
    result = Image.fromarray(np.clip(np.rint(out), 0, 255).astype("uint8"))
    if alpha is not None:
        result = result.convert("RGBA")
        result.putalpha(alpha)
    account["applied"] = True
    return result, account
