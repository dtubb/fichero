"""Enhance scanned document images without modifying source files (#1388)."""

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
_ALLOWED_FORMATS = {"jpg", "jpeg", "png", "tiff", "webp"}

ENHANCE_IMAGES_CONFIG = {
    "contrast": {
        "type": "number",
        "default": 1.25,
        "minimum": 0.1,
        "maximum": 3.0,
        "description": "Contrast multiplier. 1.0 leaves contrast unchanged.",
    },
    "sharpness": {
        "type": "number",
        "default": 1.1,
        "minimum": 0.0,
        "maximum": 3.0,
        "description": "Sharpness multiplier. 1.0 leaves sharpness unchanged.",
    },
    "denoise": {
        "type": "boolean",
        "default": False,
        "description": "Apply a light median filter for speckle/noise reduction.",
    },
    "output_format": {
        "type": "string",
        "enum": ["jpg", "png", "tiff", "webp"],
        "default": "jpg",
        "description": "Derived image format.",
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
    fmt = (output_format or "jpg").lower().lstrip(".")
    if fmt not in _ALLOWED_FORMATS:
        raise ValueError(f"Unsupported output format: {output_format}")
    return "jpeg" if fmt == "jpg" else fmt


def _extension_for_format(output_format: str) -> str:
    fmt = _normalise_format(output_format)
    return "jpg" if fmt == "jpeg" else fmt


def _clamp_factor(value: float, *, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))


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


def enhance_image_file(
    file_path: str | Path,
    output_dir: str | Path,
    *,
    contrast: float = 1.25,
    sharpness: float = 1.1,
    denoise: bool = False,
    output_format: str = "jpg",
    compression_quality: int = 90,
) -> dict[str, Any]:
    """Enhance one image into a derived output file."""
    source = Path(file_path)
    output_root = Path(output_dir)
    ext = _extension_for_format(output_format)

    try:
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")

        from PIL import Image, ImageEnhance, ImageFilter

        contrast = _clamp_factor(contrast, minimum=0.1, maximum=3.0)
        sharpness = _clamp_factor(sharpness, minimum=0.0, maximum=3.0)
        with Image.open(source) as image:
            prepared = image.copy()
            original_size = list(prepared.size)
            if denoise:
                prepared = prepared.filter(ImageFilter.MedianFilter(size=3))
            if contrast != 1.0:
                prepared = ImageEnhance.Contrast(prepared).enhance(contrast)
            if sharpness != 1.0:
                prepared = ImageEnhance.Sharpness(prepared).enhance(sharpness)

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
                "contrast": contrast,
                "sharpness": sharpness,
                "denoise": denoise,
            },
            "error": None,
        }
    except Exception as exc:
        logger.warning("enhance_images failed for %s: %s", source, exc)
        return {
            "source": str(source),
            "outputs": [],
            "output_files": [],
            "details": {},
            "error": str(exc),
        }


@register_tool(
    name="enhance_images",
    display_name="Enhance Images",
    description="Create contrast/sharpness/denoise image derivatives without modifying source files.",
    category="transform",
    icon="wand.and.rays",
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
            description="Image files to enhance.",
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
            name="Enhanced Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Enhanced derived image files.",
        ),
    ],
    config_schema=ENHANCE_IMAGES_CONFIG,
    sort_order=26,
)
async def enhance_images(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Enhance input images for downstream OCR or image workflows."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]

    output_dir = inputs.get("output_dir") or str(
        Path(tempfile.gettempdir()) / "fichero-enhanced-images"
    )
    results = [
        enhance_image_file(
            file_path,
            output_dir,
            contrast=inputs.get("contrast", 1.25),
            sharpness=inputs.get("sharpness", 1.1),
            denoise=bool(inputs.get("denoise", False)),
            output_format=inputs.get("output_format", "jpg"),
            compression_quality=inputs.get("compression_quality", 90),
        )
        for file_path in files
    ]

    image_edit_operations = append_image_edit_operations(
        inputs,
        state,
        lambda _doc: {
            "op": "enhance",
            "page": int(inputs.get("page", 1)),
            "params": {
                "brightness": 1.0,
                "contrast": _clamp_factor(inputs.get("contrast", 1.25), minimum=0.1, maximum=3.0),
                "sharpen": _clamp_factor(inputs.get("sharpness", 1.1), minimum=0.0, maximum=3.0),
                "auto_levels": bool(inputs.get("auto_levels", False)),
                "denoise": bool(inputs.get("denoise", False)),
            },
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
