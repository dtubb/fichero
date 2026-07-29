"""Rotate/auto-orient images without modifying source files (#1387)."""

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
_ALLOWED_ROTATIONS = {0, 90, 180, 270}

ROTATE_IMAGES_CONFIG = {
    "rotation_degrees": {
        "type": "integer",
        "enum": [0, 90, 180, 270],
        "default": 0,
        "description": "Clockwise rotation to apply after EXIF auto-orientation.",
    },
    "auto_orient": {
        "type": "boolean",
        "default": True,
        "description": "Apply EXIF orientation before any explicit rotation.",
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


def _normalise_rotation(rotation_degrees: int) -> int:
    rotation = int(rotation_degrees) % 360
    if rotation not in _ALLOWED_ROTATIONS:
        raise ValueError(f"Unsupported rotation: {rotation_degrees}")
    return rotation


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


def rotate_image_file(
    file_path: str | Path,
    output_dir: str | Path,
    *,
    rotation_degrees: int = 0,
    auto_orient: bool = True,
    output_format: str = "jpg",
    compression_quality: int = 90,
) -> dict[str, Any]:
    """Rotate one image into a derived output file."""
    source = Path(file_path)
    output_root = Path(output_dir)
    ext = _extension_for_format(output_format)

    try:
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")

        from PIL import Image, ImageOps

        rotation = _normalise_rotation(rotation_degrees)
        with Image.open(source) as image:
            original_size = list(image.size)
            prepared = ImageOps.exif_transpose(image) if auto_orient else image.copy()
            oriented_size = list(prepared.size)
            if rotation:
                # PIL rotates counter-clockwise for positive angles; negate for clockwise UI semantics.
                prepared = prepared.rotate(-rotation, expand=True)

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
                "oriented_size": oriented_size,
                "prepared_size": list(prepared.size),
                "auto_orient": auto_orient,
                "rotation_degrees": rotation,
            },
            "error": None,
        }
    except Exception as exc:
        logger.warning("rotate_images failed for %s: %s", source, exc)
        return {
            "source": str(source),
            "outputs": [],
            "output_files": [],
            "details": {},
            "error": str(exc),
        }


@register_tool(
    name="rotate_images",
    display_name="Rotate / Auto-Orient Images",
    description="Create rotated or EXIF-oriented image derivatives without modifying source files.",
    category="transform",
    icon="rotate.right",
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
            description="Image files to rotate or auto-orient.",
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
            name="Rotated Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Rotated derived image files.",
        ),
    ],
    config_schema=ROTATE_IMAGES_CONFIG,
    sort_order=24,
)
async def rotate_images(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Rotate/auto-orient input images for downstream workflows."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]

    output_dir = inputs.get("output_dir") or str(
        Path(tempfile.gettempdir()) / "fichero-rotated-images"
    )
    results = [
        rotate_image_file(
            file_path,
            output_dir,
            rotation_degrees=inputs.get("rotation_degrees", 0),
            auto_orient=bool(inputs.get("auto_orient", True)),
            output_format=inputs.get("output_format", "jpg"),
            compression_quality=inputs.get("compression_quality", 90),
        )
        for file_path in files
    ]

    image_edit_operations = append_image_edit_operations(
        inputs,
        state,
        lambda _doc: {
            "op": "rotate",
            "page": int(inputs.get("page", 1)),
            "params": {
                "angle": -_normalise_rotation(inputs.get("rotation_degrees", 0)),
                "expand": True,
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
