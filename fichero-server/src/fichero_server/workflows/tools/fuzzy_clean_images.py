"""Fuzzy clean scanned document images without modifying source files (#1389)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.image_edit_chains import (
    append_image_edit_operations,
    describe_no_effect,
    persist_workflow_renditions,
)
from fichero_server.workflows.types import DataType, PortDef, State
from fichero_server.media.image_flatten import flatten_for_opaque_format
from fichero_server.media.image_ops import apply_fuzzy_clean

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
_ALLOWED_FORMATS = {"jpg", "jpeg", "png", "tiff", "webp"}

FUZZY_CLEAN_IMAGES_CONFIG = {
    "despeckle_radius": {
        "type": "integer",
        "enum": [3, 5],
        "default": 3,
        "description": "Median-filter window size for speckle removal.",
    },
    "background_clean": {
        "type": "boolean",
        "default": True,
        "description": "Apply autocontrast to reduce uneven scan background.",
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


def _normalise_radius(value: int) -> int:
    radius = int(value)
    return 5 if radius >= 5 else 3


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
    if fmt == "jpeg":
        # JPEG has no alpha. convert("RGB") would DROP the channel and keep the
        # black underneath a cut-out; this composites it onto white instead.
        image = flatten_for_opaque_format(image)
    image.save(output_path, **save_kwargs)


def fuzzy_clean_image_file(
    file_path: str | Path,
    output_dir: str | Path,
    *,
    despeckle_radius: int = 3,
    background_clean: bool = True,
    output_format: str = "jpg",
    compression_quality: int = 90,
) -> dict[str, Any]:
    """Fuzzy-clean one image into a derived output file."""
    source = Path(file_path)
    output_root = Path(output_dir)
    ext = _extension_for_format(output_format)

    try:
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")

        from PIL import Image

        radius = _normalise_radius(despeckle_radius)
        with Image.open(source) as image:
            prepared = image.copy()
            original_size = list(prepared.size)
            prepared = apply_fuzzy_clean(
                prepared,
                despeckle_radius=radius,
                background_clean=background_clean,
            )

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
                "despeckle_radius": radius,
                "background_clean": background_clean,
            },
            "error": None,
        }
    except Exception as exc:
        logger.warning("fuzzy_clean_images failed for %s: %s", source, exc)
        return {
            "source": str(source),
            "outputs": [],
            "output_files": [],
            "details": {},
            "error": str(exc),
        }


@register_tool(
    name="fuzzy_clean_images",
    display_name="Fuzzy Clean Images",
    description="Despeckle and clean scan background without modifying source files.",
    category="transform",
    icon="sparkles",
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
            description="Image files to fuzzy-clean.",
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
            name="Cleaned Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Fuzzy-cleaned derived image files.",
        ),
    ],
    config_schema=FUZZY_CLEAN_IMAGES_CONFIG,
    sort_order=27,
)
async def fuzzy_clean_images(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Fuzzy-clean input images for downstream OCR or image workflows."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]

    output_dir = inputs.get("output_dir") or str(
        Path(tempfile.gettempdir()) / "fichero-fuzzy-cleaned-images"
    )
    radius = _normalise_radius(inputs.get("despeckle_radius", 3))
    background_clean = bool(inputs.get("background_clean", True))
    results = [
        fuzzy_clean_image_file(
            file_path,
            output_dir,
            despeckle_radius=radius,
            background_clean=background_clean,
            output_format=inputs.get("output_format", "jpg"),
            compression_quality=inputs.get("compression_quality", 90),
        )
        for file_path in files
    ]

    image_edit_operations = append_image_edit_operations(
        inputs,
        state,
        lambda _doc: {
            "op": "fuzzy_clean",
            "page": int(inputs.get("page", 1)),
            "params": {"despeckle_radius": radius, "background_clean": background_clean},
        },
    )

    # Persist the pixels, not just the paths (2026-08-21). These tools wrote
    # derived images to a temp directory and returned the paths; nothing
    # reached the library, so a run "completed" with no user-visible effect.
    rendition_report = persist_workflow_renditions(
        inputs, state, role="fuzzy_cleaned", results=results
    )

    output_files = [path for result in results for path in result.get("outputs", [])]
    no_effect = describe_no_effect(files, output_files, rendition_report)
    if no_effect:
        logger.warning("fuzzy_clean_images: %s", no_effect)
    errors = [result["error"] for result in results if result.get("error")]
    return {
        "output_files": output_files,
        "renditions": rendition_report.get("renditions") or [],
        "rendition_report": rendition_report,
        "no_effect": no_effect,
        "files": output_files,
        "count": len(output_files),
        "results": results,
        "image_edit_operations": image_edit_operations,
        "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None),
    }
