"""Remove image backgrounds without modifying source files (#1393)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fichero.llm import LLMConfig
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.image_edit_chains import append_image_edit_operations
from fichero.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
_ALLOWED_METHODS = {"threshold", "opencv", "rembg"}
_ALLOWED_FORMATS = {"png", "webp", "tiff"}

REMOVE_BACKGROUND_IMAGES_CONFIG = {
    "method": {
        "type": "string",
        "enum": ["threshold", "opencv", "rembg"],
        "default": "threshold",
        "description": "Background removal method. opencv/rembg fall back when unavailable.",
    },
    "threshold": {
        "type": "integer",
        "default": 28,
        "minimum": 0,
        "maximum": 255,
        "description": "Foreground threshold for threshold/opencv fallback methods.",
    },
    "output_format": {
        "type": "string",
        "enum": ["png", "webp", "tiff"],
        "default": "png",
        "description": "Derived image format. Must support alpha.",
    },
    "compression_quality": {
        "type": "integer",
        "default": 90,
        "minimum": 1,
        "maximum": 100,
        "description": "WebP compression quality.",
    },
    "output_dir": {
        "type": "string",
        "default": "",
        "description": "Optional output directory. Defaults to a temp directory.",
    },
}


def _normalise_method(method: str) -> str:
    value = (method or "threshold").strip().lower()
    if value not in _ALLOWED_METHODS:
        raise ValueError(f"Unsupported background removal method: {method}")
    return value


def _normalise_format(output_format: str) -> str:
    fmt = (output_format or "png").lower().lstrip(".")
    if fmt not in _ALLOWED_FORMATS:
        raise ValueError(f"Unsupported output format: {output_format}")
    return fmt


def _remove_background_threshold(image: Any, threshold: int) -> Any:
    from PIL import Image, ImageChops

    threshold = max(0, min(255, int(threshold)))
    rgba = image.convert("RGBA")
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, background).convert("L")
    alpha = diff.point(lambda value: 255 if value > threshold else 0)
    rgba.putalpha(alpha)
    return rgba


def _dark_edge_trim_bbox(gray: Any) -> tuple[int, int, int, int] | None:
    """Find sustained black photocopy bands near page edges.

    Some scans have a thin white scanner strip outside the black border, so this
    deliberately looks for dark runs near the edge instead of requiring the
    first/last row or column itself to be black.
    """
    import numpy as np

    height, width = gray.shape
    dark_threshold = 35
    max_band_fraction = 0.45
    min_run_fraction = 0.02

    def edge_run(means: Any, *, from_start: bool) -> tuple[int, int] | None:
        size = len(means)
        max_band = int(size * max_band_fraction)
        min_run = max(3, int(size * min_run_fraction))
        dark = means < dark_threshold
        runs: list[tuple[int, int]] = []
        start: int | None = None
        for index, is_dark in enumerate(dark):
            if is_dark and start is None:
                start = index
            if (not is_dark or index == size - 1) and start is not None:
                end = index - 1 if not is_dark else index
                if end - start + 1 >= min_run:
                    runs.append((start, end))
                start = None
        if from_start:
            candidates = [run for run in runs if run[0] <= min_run and run[1] < max_band]
            return max(candidates, key=lambda run: run[1] - run[0]) if candidates else None
        candidates = [run for run in runs if run[1] >= size - min_run - 1 and run[0] > size - max_band]
        return max(candidates, key=lambda run: run[1] - run[0]) if candidates else None

    row_means = np.mean(gray, axis=1)
    col_means = np.mean(gray, axis=0)
    left = 0
    top = 0
    right = width
    bottom = height
    if run := edge_run(col_means, from_start=True):
        left = min(width - 1, run[1] + 1)
    if run := edge_run(col_means, from_start=False):
        right = max(left + 1, run[0])
    if run := edge_run(row_means, from_start=True):
        top = min(height - 1, run[1] + 1)
    if run := edge_run(row_means, from_start=False):
        bottom = max(top + 1, run[0])

    if left == 0 and top == 0 and right == width and bottom == height:
        return None
    if right - left < width * 0.2 or bottom - top < height * 0.2:
        return None
    return left, top, right, bottom


def _remove_black_background_opencv(image: Any) -> Any:
    """Archive OpenCV document background remover for black photocopy margins.

    Ported from ``fichero_archive/_archive/fichero_legacy/tools/remove_background.py``.
    It keeps large foreground contours, builds a softened alpha mask, and crops
    to the non-black document area. This is intentionally document-biased rather
    than a general foreground segmentation algorithm.
    """
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - exercised by fallback test
        raise RuntimeError("OpenCV background removal requires cv2 and numpy") from exc

    img_array = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    edge_bbox = _dark_edge_trim_bbox(gray)
    if edge_bbox is not None:
        left, top, right, bottom = edge_bbox
        img_array = img_array[top:bottom, left:right, :]
        gray = gray[top:bottom, left:right]
    height, width = gray.shape
    image_area = height * width

    black_thresh = 80
    black_pixels = np.count_nonzero(gray < black_thresh)
    black_ratio = black_pixels / float(image_area)
    if black_ratio < 0.01:
        rgba_skip = cv2.cvtColor(img_array, cv2.COLOR_RGB2RGBA)
        rgba_skip[:, :, 3] = 255
        return Image.fromarray(rgba_skip, mode="RGBA")

    _, bin_mask = cv2.threshold(gray, black_thresh, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(bin_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        rgba_fallback = cv2.cvtColor(img_array, cv2.COLOR_RGB2RGBA)
        rgba_fallback[:, :, 3] = 255
        return Image.fromarray(rgba_fallback, mode="RGBA")

    contour_areas = [cv2.contourArea(contour) for contour in contours]
    total_foreground_area = sum(contour_areas)
    sorted_by_area = sorted(zip(contours, contour_areas), key=lambda item: item[1], reverse=True)
    largest_contour_area = sorted_by_area[0][1]

    keep_contours = []
    for contour, area in sorted_by_area:
        if area <= 0:
            continue
        frac_of_foreground = area / total_foreground_area if total_foreground_area else 0
        frac_of_largest = area / largest_contour_area if largest_contour_area else 0
        x, y, contour_width, contour_height = cv2.boundingRect(contour)
        center_x = x + contour_width / 2
        center_y = y + contour_height / 2
        near_center = abs(center_x - width / 2) < width * 0.1 and abs(center_y - height / 2) < height * 0.1
        if frac_of_foreground > 0.2 or frac_of_largest > 0.2 or near_center:
            keep_contours.append(contour)

    if not keep_contours:
        keep_contours = [sorted_by_area[0][0]]

    doc_mask = np.zeros_like(bin_mask, dtype=np.uint8)
    for contour in keep_contours:
        cv2.drawContours(doc_mask, [contour], -1, color=255, thickness=-1)

    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    doc_mask = cv2.morphologyEx(doc_mask, cv2.MORPH_OPEN, kernel_open)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
    doc_mask = cv2.morphologyEx(doc_mask, cv2.MORPH_CLOSE, kernel_close)
    blurred_mask = cv2.GaussianBlur(doc_mask, (21, 21), 0)
    blurred_mask = cv2.normalize(blurred_mask, None, 0, 255, cv2.NORM_MINMAX)
    final_mask = (blurred_mask.astype(np.float32) * 0.95).astype(np.uint8)

    rgba = cv2.cvtColor(img_array, cv2.COLOR_RGB2RGBA)
    rgba[:, :, 3] = final_mask
    ys, xs = np.nonzero(final_mask > 0)
    if len(xs) == 0 or len(ys) == 0:
        return Image.fromarray(rgba, mode="RGBA")

    cropped_rgba = rgba[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1, :]
    return Image.fromarray(cropped_rgba, mode="RGBA")


def remove_background(image: Any, *, method: str = "threshold", threshold: int = 28) -> Any:
    """Remove background, falling back to threshold when optional deps are absent."""
    method = _normalise_method(method)
    if method == "rembg":
        try:
            from rembg import remove
        except ImportError:
            return _remove_background_threshold(image, threshold)
        return remove(image.convert("RGBA"))

    if method == "opencv":
        try:
            return _remove_black_background_opencv(image)
        except RuntimeError:
            return _remove_background_threshold(image, threshold)

    return _remove_background_threshold(image, threshold)


def _save_image(
    image: Any,
    output_path: Path,
    *,
    output_format: str,
    compression_quality: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = _normalise_format(output_format)
    save_kwargs: dict[str, Any] = {"format": fmt.upper()}
    if fmt == "webp":
        save_kwargs["quality"] = max(1, min(100, int(compression_quality)))
    image.save(output_path, **save_kwargs)


def remove_background_image_file(
    file_path: str | Path,
    output_dir: str | Path,
    *,
    method: str = "threshold",
    threshold: int = 28,
    output_format: str = "png",
    compression_quality: int = 90,
) -> dict[str, Any]:
    """Remove background from one image into a derived output file."""
    source = Path(file_path)
    output_root = Path(output_dir)
    ext = _normalise_format(output_format)

    try:
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")

        from PIL import Image

        method = _normalise_method(method)
        threshold = max(0, min(255, int(threshold)))
        with Image.open(source) as image:
            original_size = list(image.size)
            prepared = remove_background(image, method=method, threshold=threshold)
            output_path = output_root / f"{source.stem}.{ext}"
            _save_image(
                prepared,
                output_path,
                output_format=output_format,
                compression_quality=compression_quality,
            )

        return {
            "source": str(source),
            "outputs": [str(output_path)],
            "output_files": [str(output_path)],
            "details": {
                "original_format": source.suffix.lower(),
                "output_format": ext,
                "original_size": original_size,
                "prepared_size": list(prepared.size),
                "method": method,
                "threshold": threshold,
            },
            "error": None,
        }
    except Exception as exc:
        logger.warning("remove_background_images failed for %s: %s", source, exc)
        return {
            "source": str(source),
            "outputs": [],
            "output_files": [],
            "details": {},
            "error": str(exc),
        }


@register_tool(
    name="remove_background_images",
    display_name="Remove Background Images",
    description="Create alpha-background image derivatives without modifying source files.",
    category="transform",
    icon="person.crop.square",
    color="orange",
    uses_llm=False,
    supports_batch=True,
    input_ports=[
        PortDef(
            id="files",
            name="Files",
            port_type="input",
            data_type=DataType.FILES,
            required=True,
            description="Image files to remove backgrounds from.",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Document metadata for preview-editor edit-chain updates.",
        ),
    ],
    output_ports=[
        PortDef(
            id="output_files",
            name="Background-Removed Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Background-removed derived image files.",
        ),
    ],
    config_schema=REMOVE_BACKGROUND_IMAGES_CONFIG,
    sort_order=28,
)
async def remove_background_images(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Remove backgrounds from input images for editing workflows."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]

    output_dir = inputs.get("output_dir") or str(
        Path(tempfile.gettempdir()) / "fichero-background-removed-images"
    )
    method = _normalise_method(inputs.get("method", "threshold"))
    threshold = max(0, min(255, int(inputs.get("threshold", 28))))
    results = [
        remove_background_image_file(
            file_path,
            output_dir,
            method=method,
            threshold=threshold,
            output_format=inputs.get("output_format", "png"),
            compression_quality=inputs.get("compression_quality", 90),
        )
        for file_path in files
    ]

    image_edit_operations = append_image_edit_operations(
        inputs,
        state,
        lambda _doc: {
            "op": "remove_background",
            "page": int(inputs.get("page", 1)),
            "params": {"method": method, "threshold": threshold},
        },
    )

    output_files = [path for result in results for path in result.get("outputs", [])]
    errors = [result["error"] for result in results if result.get("error")]
    return {
        "output_files": output_files,
        "files": output_files,
        "count": len(output_files),
        "results": results,
        "image_edit_operations": image_edit_operations,
        "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None),
    }
