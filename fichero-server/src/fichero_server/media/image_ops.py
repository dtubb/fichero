"""Shared non-destructive image-edit operations."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat


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


def detect_content_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    """Find the non-border content rectangle using a local threshold."""
    gray = image.convert("L")
    pixels = gray.load()
    xs, ys = [], []
    for y in range(gray.height):
        for x in range(gray.width):
            if pixels[x, y] > 20:
                xs.append(x)
                ys.append(y)
    if not xs:
        return 0, 0, image.width, image.height
    left, top, right, bottom = min(xs), min(ys), max(xs) + 1, max(ys) + 1
    return left, top, right - left, bottom - top


def remove_black_background_opencv(image: Image.Image) -> Image.Image:
    """Contour-based page lift for photographed documents on a dark ground.

    Ported from the legacy Fichero pipeline: threshold for the dark ground,
    keep the large/central contours, fill them SOLID, feather, crop. Because
    the kept contour covers the whole page, every ink stroke inside it
    survives — the mask is drawn at the page level, never per pixel.
    """
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


#: Connectivity is computed at this bounded working size; similarity stays at
#: full resolution, so the page edge remains crisp while the flood fill stays
#: fast on multi-megapixel scans.
_MAX_FLOOD_DIM = 1024


def _border_connected(similar: "Any") -> "Any":
    """Boolean mask of background-similar pixels reachable from the border.

    Iterative 4-neighbour dilation, fully vectorised; converges when the
    reachable set stops growing (bounded by the image diameter).
    """
    import numpy as np

    reach = np.zeros_like(similar)
    reach[0, :] = similar[0, :]
    reach[-1, :] = similar[-1, :]
    reach[:, 0] = similar[:, 0]
    reach[:, -1] = similar[:, -1]
    for _ in range(similar.shape[0] + similar.shape[1]):
        grown = reach.copy()
        grown[1:, :] |= reach[:-1, :]
        grown[:-1, :] |= reach[1:, :]
        grown[:, 1:] |= reach[:, :-1]
        grown[:, :-1] |= reach[:, 1:]
        grown &= similar
        if np.array_equal(grown, reach):
            break
        reach = grown
    return reach


def remove_scan_background(image: Image.Image, threshold: int = 28) -> Image.Image:
    """Magic-wand background removal that preserves page content.

    Flood-fills from the image borders: only pixels within ``threshold`` of
    the border colour AND connected to the border become transparent. Ink
    strokes — and the paper between them — are interior, so they survive.

    The per-pixel colour-difference this replaces made EVERY background-
    coloured pixel transparent: on a manuscript scan the paper itself matched,
    so the whole ground vanished and faint/anti-aliased stroke edges went with
    it (Daniel, 2026-09-02: remove-background "eats parts of the text").
    """
    import numpy as np

    threshold = max(0, min(255, int(threshold)))
    rgb_full = np.asarray(image.convert("RGB"), dtype=np.int16)
    height, width = rgb_full.shape[:2]
    border = np.concatenate(
        [rgb_full[0, :], rgb_full[-1, :], rgb_full[:, 0], rgb_full[:, -1]]
    )
    # Median of ALL border pixels, not one corner: robust when a page corner
    # pokes into the frame edge.
    background = np.median(border, axis=0)
    similar_full = np.abs(rgb_full - background).max(axis=2) <= threshold

    scale = max(height, width) / _MAX_FLOOD_DIM
    if scale > 1:
        small = image.convert("RGB").resize(
            (max(1, round(width / scale)), max(1, round(height / scale))),
            Image.Resampling.BILINEAR,
        )
        rgb_small = np.asarray(small, dtype=np.int16)
        similar_small = np.abs(rgb_small - background).max(axis=2) <= threshold
        reach_small = _border_connected(similar_small)
        reach_image = Image.fromarray(
            reach_small.astype(np.uint8) * 255, mode="L"
        ).resize((width, height), Image.Resampling.BILINEAR)
        # Upsampling dilates reach by ~a pixel; ANDing with the full-res
        # similarity mask restores the exact page edge.
        reach = (np.asarray(reach_image) > 0) & similar_full
    else:
        reach = _border_connected(similar_full)

    alpha = np.where(reach, 0, 255).astype(np.uint8)
    rgba = image.convert("RGBA")
    rgba.putalpha(Image.fromarray(alpha, mode="L"))
    return rgba


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
            return remove_black_background_opencv(image)
    if method == "threshold":
        return remove_scan_background(image, int(params.get("threshold", 28)))
    raise HTTPException(400, f"Unsupported background method: {method}")


def _flatten_illumination(base: Image.Image) -> Image.Image:
    """Divide the page by its own background estimate to even out lighting.

    Grayscale-dilate at a downscale (MaxFilter reaches past the ink to the
    paper), blur, upscale, then normalise each pixel against that estimate.
    Shadows, stains and yellowing flatten to near-white while ink keeps its
    contrast — the classic document-cleanup trick from the legacy pipeline.
    """
    import numpy as np

    small = base.resize(
        (max(1, base.width // 8), max(1, base.height // 8)), Image.Resampling.BOX
    )
    background = small.filter(ImageFilter.MaxFilter(7)).filter(
        ImageFilter.GaussianBlur(4)
    )
    background = background.resize(base.size, Image.Resampling.BILINEAR)
    values = np.asarray(base, dtype=np.float32)
    estimate = np.maximum(np.asarray(background, dtype=np.float32), 1.0)
    flattened = np.clip(values / estimate * 245.0, 0, 255).astype(np.uint8)
    return Image.fromarray(flattened, mode=base.mode)


def apply_fuzzy_clean(
    image: Image.Image, *, despeckle_radius: int = 3, background_clean: bool = True
) -> Image.Image:
    """Despeckle and clean a scanned page for legibility.

    MedianFilter kills isolated speckles; ``background_clean`` then flattens
    uneven illumination (see :func:`_flatten_illumination`), autocontrasts and
    lightly unsharpens — the legacy pipeline's CLAHE-and-sharpen intent in
    pure PIL/numpy, so it works in the embedded engine without OpenCV.
    """
    # MedianFilter + autocontrast operate on colour channels only. Remove-
    # Background produces RGBA (transparent edges) and autocontrast raises
    # "not supported for mode RGBA"; palette (P) images choke on the filters
    # too. Split the original alpha off, clean the colour, then re-attach the
    # untouched alpha so transparency is preserved exactly (#1534).
    has_alpha = image.mode in {"RGBA", "LA"}
    alpha = image.getchannel("A") if has_alpha else None
    # Analysis path — the base for pixel statistics, never written out.
    base = image if image.mode in {"RGB", "L"} else image.convert("RGB")

    radius = 5 if int(despeckle_radius) >= 5 else 3
    cleaned = base.filter(ImageFilter.MedianFilter(size=radius))
    if background_clean:
        # The background estimate needs room to see paper past the ink; on a
        # thumbnail-sized image just autocontrast.
        if min(cleaned.size) >= 32:
            # No autocontrast after the flatten: the divide already normalises
            # paper to ~245, and stretching a background-dominated histogram
            # would clip the paper itself toward black.
            cleaned = _flatten_illumination(cleaned)
            cleaned = cleaned.filter(
                ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2)
            )
        else:
            cleaned = ImageOps.autocontrast(cleaned)
    if alpha is not None:
        cleaned = cleaned.convert("RGBA")
        cleaned.putalpha(alpha)
    return cleaned


def apply_operation(image: Image.Image, op: dict[str, Any]) -> Image.Image:
    """Apply one saved image-edit operation; shared by preview and consumers."""
    name = str(op.get("op", "")).strip().lower()
    params = op.get("params") or {}
    if not isinstance(params, dict):
        raise HTTPException(400, f"Invalid params for operation: {name}")
    if name in {"rotate", "straighten", "auto_deskew"}:
        angle = detect_deskew_angle(image) if name == "auto_deskew" and "angle" not in params else float(params.get("angle", 0))
        # Exact quarter turns are LOSSLESS transposes (Daniel, 2026-08-30:
        # "edits seemed to make the quality worse" — every rotate-left click
        # was bicubic-resampling the whole page). Only a fractional angle
        # needs interpolation.
        quarter = angle % 360
        if quarter in (0.0, 90.0, 180.0, 270.0):
            transposes = {
                90.0: Image.Transpose.ROTATE_90,
                180.0: Image.Transpose.ROTATE_180,
                270.0: Image.Transpose.ROTATE_270,
            }
            method = transposes.get(quarter)
            return image.transpose(method) if method is not None else image
        return image.rotate(
            angle,
            expand=bool(params.get("expand", True)),
            resample=Image.Resampling.BICUBIC,
            fillcolor="white",
        )
    if name == "crop":
        base = ImageOps.exif_transpose(image) if bool(params.get("auto_orient", True)) else image
        missing = {key for key in ("left", "top", "width", "height") if key not in params}
        if missing:
            raise HTTPException(400, f"Crop operation missing required params: {sorted(missing)}")
        left, top = int(params["left"]), int(params["top"])
        width, height = int(params["width"]), int(params["height"])
        right, bottom = min(left + width, base.width), min(top + height, base.height)
        if width <= 0 or height <= 0 or left < 0 or top < 0 or right <= left or bottom <= top:
            raise HTTPException(400, "Crop bounds are invalid")
        return base.crop((left, top, right, bottom))
    if name == "auto_crop_border":
        left, top, width, height = detect_content_bbox(image)
        return apply_operation(image, {"op": "crop", "params": {"left": left, "top": top, "width": width, "height": height}})
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
    if name == "adaptive_binarize":
        gray = image.convert("L")
        # ImageStat, not sum(gray.getdata()): Pillow 12.3 deprecates getdata
        # (removal in Pillow 14) and materialising every pixel into Python just
        # to average it is wasteful on a scanned page. ImageStat reads the
        # histogram, so the mean is identical, not approximated (#4337).
        threshold = ImageStat.Stat(gray).mean[0]
        return gray.point(lambda value: 255 if value >= threshold else 0).convert("RGB")
    if name == "remove_background":
        return _remove_background(image, params)
    if name == "segment":
        return image
    if name == "grayscale":
        return ImageOps.grayscale(image).convert("RGB")
    raise HTTPException(400, f"Unsupported operation: {name}")
