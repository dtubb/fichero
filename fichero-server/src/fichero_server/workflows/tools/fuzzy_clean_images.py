"""Fuzzy clean scanned document images without modifying source files (#1389)."""

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
    if fmt == "jpeg" and image.mode in {"RGBA", "P"}:
        image = image.convert("RGB")
    image.save(output_path, **save_kwargs)


def apply_fuzzy_clean(image: Any, *, despeckle_radius: int = 3, background_clean: bool = True) -> Any:
    """Apply a conservative document despeckle/background cleanup."""
    from PIL import ImageFilter, ImageOps

    # MedianFilter + autocontrast operate on colour channels only. Remove-
    # Background produces RGBA (transparent edges) and autocontrast raises
    # "not supported for mode RGBA"; palette (P) images choke on the filters
    # too. Split the original alpha off, clean the colour, then re-attach the
    # untouched alpha so transparency is preserved exactly (#1534).
    has_alpha = image.mode in {"RGBA", "LA"}
    alpha = image.getchannel("A") if has_alpha else None
    base = image if image.mode in {"RGB", "L"} else image.convert("RGB")

    cleaned = base.filter(ImageFilter.MedianFilter(size=_normalise_radius(despeckle_radius)))
    if background_clean:
        cleaned = ImageOps.autocontrast(cleaned)
    if alpha is not None:
        cleaned = cleaned.convert("RGBA")
        cleaned.putalpha(alpha)
    return cleaned


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
