"""Remove image backgrounds without modifying source files (#1393)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.image_edit_chains import append_image_edit_operations
from fichero_server.workflows.types import DataType, PortDef, State

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
            import cv2  # type: ignore[import-not-found]
            import numpy as np
            from PIL import Image
        except ImportError:
            return _remove_background_threshold(image, threshold)
        rgb = np.array(image.convert("RGB"))
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        rgba = image.convert("RGBA")
        rgba.putalpha(Image.fromarray(mask))
        return rgba

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
