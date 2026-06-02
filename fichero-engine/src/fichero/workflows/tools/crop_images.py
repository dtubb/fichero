"""Crop photocopy/document pages without modifying source files (#1595)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fichero.llm import LLMConfig
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.image_edit_chains import append_image_edit_operations
from fichero.workflows.tools.remove_background_images import _dark_edge_trim_bbox
from fichero.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
_ALLOWED_FORMATS = {"jpg", "jpeg", "png", "tiff", "webp"}

CROP_IMAGES_CONFIG = {
    "method": {
        "type": "string",
        "enum": ["photocopy", "contour"],
        "default": "photocopy",
        "description": "photocopy trims sustained black edge bands; contour uses archive-style document contour detection.",
    },
    "padding": {
        "type": "integer",
        "default": 20,
        "minimum": 0,
        "maximum": 200,
        "description": "Padding to add around detected document crop.",
    },
    "output_format": {
        "type": "string",
        "enum": ["jpg", "png", "tiff", "webp"],
        "default": "png",
        "description": "Derived crop image format.",
    },
    "compression_quality": {
        "type": "integer",
        "default": 90,
        "minimum": 1,
        "maximum": 100,
        "description": "JPEG/WebP compression quality.",
    },
    "output_dir": {
        "type": "string",
        "default": "",
        "description": "Optional output directory. Defaults to a temp directory.",
    },
}


def _normalise_format(output_format: str) -> str:
    fmt = (output_format or "png").lower().lstrip(".")
    if fmt not in _ALLOWED_FORMATS:
        raise ValueError(f"Unsupported output format: {output_format}")
    return "jpeg" if fmt == "jpg" else fmt


def _extension_for_format(output_format: str) -> str:
    fmt = _normalise_format(output_format)
    return "jpg" if fmt == "jpeg" else fmt


def _save_image(
    image: Any,
    output_path: Path,
    *,
    output_format: str,
    compression_quality: int,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fmt = _normalise_format(output_format)
    save_kwargs: dict[str, Any] = {"format": fmt.upper() if fmt != "jpeg" else "JPEG"}
    if fmt in {"jpeg", "webp"}:
        save_kwargs["quality"] = max(1, min(100, int(compression_quality)))
    if fmt == "jpeg" and image.mode in {"RGBA", "P"}:
        image = image.convert("RGB")
    image.save(output_path, **save_kwargs)


def _with_padding(
    bbox: tuple[int, int, int, int],
    *,
    width: int,
    height: int,
    padding: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    padding = max(0, min(200, int(padding)))
    return (
        max(0, left - padding),
        max(0, top - padding),
        min(width, right + padding),
        min(height, bottom + padding),
    )


def _contour_crop_bbox(image: Any, *, padding: int) -> tuple[int, int, int, int] | None:
    """Archive-style contour crop for a page/document foreground."""
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
    except ImportError:
        return None

    img_array = np.array(image.convert("RGB"))
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    if bbox := _dark_edge_trim_bbox(gray):
        return _with_padding(bbox, width=image.width, height=image.height, padding=padding)

    mean_brightness = float(np.mean(gray))
    if mean_brightness > 127:
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY_INV)
    else:
        _, thresh = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    image_area = image.width * image.height
    candidates = []
    for contour in contours:
        area_ratio = cv2.contourArea(contour) / image_area
        if not 0.1 <= area_ratio <= 0.99:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        aspect_ratio = w / h if h else 0
        if 0.4 <= aspect_ratio <= 2.5:
            candidates.append((contour, x, y, w, h))
    if not candidates:
        return None
    _, x, y, w, h = max(candidates, key=lambda item: cv2.contourArea(item[0]))
    return _with_padding((x, y, x + w, y + h), width=image.width, height=image.height, padding=padding)


def crop_image_file(
    file_path: str | Path,
    output_dir: str | Path,
    *,
    method: str = "photocopy",
    padding: int = 20,
    output_format: str = "png",
    compression_quality: int = 90,
) -> dict[str, Any]:
    """Crop one image into a derived output file."""
    source = Path(file_path)
    output_root = Path(output_dir)
    ext = _extension_for_format(output_format)

    try:
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")

        import numpy as np
        from PIL import Image, ImageOps

        with Image.open(source) as image:
            prepared = ImageOps.exif_transpose(image)
            original_size = list(prepared.size)
            bbox = None
            if method == "photocopy":
                try:
                    import cv2  # type: ignore[import-not-found]

                    gray = cv2.cvtColor(np.array(prepared.convert("RGB")), cv2.COLOR_RGB2GRAY)
                    bbox = _dark_edge_trim_bbox(gray)
                    if bbox is not None:
                        bbox = _with_padding(bbox, width=prepared.width, height=prepared.height, padding=padding)
                except ImportError:
                    bbox = None
            if bbox is None:
                bbox = _contour_crop_bbox(prepared, padding=padding)
            if bbox is None:
                bbox = (0, 0, prepared.width, prepared.height)
                crop_method = "original"
            else:
                crop_method = method
            cropped = prepared.crop(bbox)
            output_path = output_root / f"{source.stem}.{ext}"
            _save_image(
                cropped,
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
                "prepared_size": list(cropped.size),
                "crop_bbox": list(bbox),
                "method": crop_method,
                "padding": padding,
            },
            "error": None,
        }
    except Exception as exc:
        logger.warning("crop_images failed for %s: %s", source, exc)
        return {
            "source": str(source),
            "outputs": [],
            "output_files": [],
            "details": {},
            "error": str(exc),
        }


@register_tool(
    name="crop_images",
    display_name="Crop Images",
    description="Crop photocopy/document pages without modifying source files.",
    category="transform",
    icon="crop",
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
            description="Image files to crop.",
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
            name="Cropped Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Cropped derived image files.",
        ),
    ],
    config_schema=CROP_IMAGES_CONFIG,
    sort_order=27,
)
async def crop_images(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Crop input images for downstream workflows."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]

    output_dir = inputs.get("output_dir") or str(Path(tempfile.gettempdir()) / "fichero-cropped-images")
    method = (inputs.get("method") or "photocopy").strip().lower()
    results = [
        crop_image_file(
            file_path,
            output_dir,
            method=method,
            padding=inputs.get("padding", 20),
            output_format=inputs.get("output_format", "png"),
            compression_quality=inputs.get("compression_quality", 90),
        )
        for file_path in files
    ]

    image_edit_operations = append_image_edit_operations(
        inputs,
        state,
        lambda _doc: {
            "op": "crop",
            "page": int(inputs.get("page", 1)),
            "params": {"method": method, "padding": int(inputs.get("padding", 20))},
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
