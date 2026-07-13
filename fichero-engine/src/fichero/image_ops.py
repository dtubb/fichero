"""Shared non-destructive image-edit operations."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from fichero.workflows.tools.fuzzy_clean_images import apply_fuzzy_clean


def detect_deskew_angle(image: Image.Image) -> float:
    """Return the local Hough-estimated text-line skew angle, or zero."""
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
    except ImportError:
        return 0.0
    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    lines = cv2.HoughLinesP(cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150), 1, np.pi / 180, threshold=100, minLineLength=max(80, gray.shape[1] // 5), maxLineGap=12)
    if lines is None:
        return 0.0
    angles = [float(np.degrees(np.arctan2(y2-y1, x2-x1))) for [[x1, y1, x2, y2]] in lines if -15 <= np.degrees(np.arctan2(y2-y1, x2-x1)) <= 15]
    return float(np.median(angles)) if angles else 0.0


def _remove_black_background_opencv(image: Image.Image) -> Image.Image:
    import cv2  # type: ignore[import-not-found]
    import numpy as np

    gray = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2GRAY)
    if np.count_nonzero(gray < 80) / gray.size < 0.01:
        return image.convert("RGBA")
    _, binary = cv2.threshold(gray, 80, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return image.convert("RGBA")
    areas = [cv2.contourArea(contour) for contour in contours]
    mask = np.zeros_like(binary)
    for contour, area in zip(contours, areas):
        if area >= max(areas) * 0.2:
            cv2.drawContours(mask, [contour], -1, 255, thickness=-1)
    mask = cv2.GaussianBlur(mask, (21, 21), 0)
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return image.convert("RGBA")
    rgba = image.convert("RGBA")
    rgba.putalpha(Image.fromarray(mask))
    return rgba.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1))


def _remove_background(image: Image.Image, params: dict[str, Any]) -> Image.Image:
    method = str(params.get("method", "opencv")).strip().lower()
    if method == "rembg":
        try:
            from rembg import remove
        except ImportError as exc:
            raise HTTPException(501, "rembg is not installed in this backend") from exc
        return remove(image.convert("RGBA"))
    if method == "opencv":
        try:
            import cv2  # type: ignore[import-not-found]
        except ImportError:
            method = "threshold"
        else:
            del cv2
            return _remove_black_background_opencv(image)
    if method == "threshold":
        rgba = image.convert("RGBA")
        rgb = image.convert("RGB")
        diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))).convert("L")
        rgba.putalpha(diff.point(lambda value: 255 if value > int(params.get("threshold", 28)) else 0))
        return rgba
    raise HTTPException(400, f"Unsupported background method: {method}")


def apply_operation(image: Image.Image, op: dict[str, Any]) -> Image.Image:
    """Apply one saved image-edit operation; shared by preview and consumers."""
    name = str(op.get("op", "")).strip().lower()
    params = op.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(400, f"Invalid params for operation: {name}")
    if name in {"rotate", "straighten", "auto_deskew"}:
        angle = detect_deskew_angle(image) if name == "auto_deskew" and "angle" not in params else float(params.get("angle", 0))
        return image.rotate(
            angle,
            expand=bool(params.get("expand", True)),
            resample=Image.Resampling.BICUBIC,
            fillcolor="white",
        )
    if name == "crop":
        base = ImageOps.exif_transpose(image) if bool(params.get("auto_orient", True)) else image
        left, top = int(params.get("left", 0)), int(params.get("top", 0))
        width, height = int(params.get("width", base.width)), int(params.get("height", base.height))
        right, bottom = min(left + width, base.width), min(top + height, base.height)
        if width <= 0 or height <= 0 or left < 0 or top < 0 or right <= left or bottom <= top:
            raise HTTPException(400, "Crop bounds are invalid")
        return base.crop((left, top, right, bottom))
    if name == "flip_horizontal":
        return ImageOps.mirror(image)
    if name == "flip_vertical":
        return ImageOps.flip(image)
    if name == "brightness":
        return ImageEnhance.Brightness(image).enhance(float(params.get("factor", 1.0)))
    if name == "contrast":
        return ImageEnhance.Contrast(image).enhance(float(params.get("factor", 1.0)))
    if name == "sharpen":
        return ImageEnhance.Sharpness(image).enhance(float(params.get("factor", 1.0)))
    if name == "auto_levels":
        return ImageOps.autocontrast(image)
    if name == "enhance":
        edited = image.filter(ImageFilter.MedianFilter(size=3)) if params.get("denoise") else image
        if params.get("auto_levels"):
            edited = ImageOps.autocontrast(edited)
        for enhancer, key in ((ImageEnhance.Brightness, "brightness"), (ImageEnhance.Contrast, "contrast"), (ImageEnhance.Sharpness, "sharpen")):
            edited = enhancer(edited).enhance(float(params.get(key, 1.0)))
        return edited
    if name == "fuzzy_clean":
        return apply_fuzzy_clean(image, despeckle_radius=int(params.get("despeckle_radius", 3)), background_clean=bool(params.get("background_clean", True)))
    if name == "denoise":
        return apply_fuzzy_clean(image, despeckle_radius=int(params.get("radius", 3)), background_clean=False)
    if name == "remove_background":
        return _remove_background(image, params)
    if name == "segment":
        return image
    if name == "grayscale":
        return ImageOps.grayscale(image).convert("RGB")
    raise HTTPException(400, f"Unsupported operation: {name}")
