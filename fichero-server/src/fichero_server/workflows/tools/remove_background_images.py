"""Remove image backgrounds without modifying source files (#1393)."""

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
        "description": "Background colour tolerance for the border flood-fill method.",
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


def remove_background(image: Any, *, method: str = "threshold", threshold: int = 28) -> Any:
    """Remove background via the shared media owner (one implementation for
    the image editor and workflow tools), falling back to the text-preserving
    border flood-fill when optional deps are absent.

    The previous local "opencv" path Otsu-inverted the page — its mask kept
    only DARK pixels, so on a manuscript scan the paper vanished and the
    3x3 morphological open then ate the thin strokes themselves. The contour
    method masks at the page level instead.
    """
    from fichero_server.media.image_ops import (
        remove_black_background_opencv,
        remove_scan_background,
    )

    method = _normalise_method(method)
    if method == "rembg":
        try:
            from rembg import remove
        except ImportError:
            return remove_scan_background(image, threshold)
        return remove(image.convert("RGBA"))

    if method == "opencv":
        try:
            import cv2  # type: ignore[import-not-found]  # noqa: F401
        except ImportError:
            return remove_scan_background(image, threshold)
        return remove_black_background_opencv(image)

    return remove_scan_background(image, threshold)


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

    # Persist the pixels, not just the paths (2026-08-21). The tool wrote PNGs
    # to a temp directory and returned their paths; nothing reached the
    # library, so a run "completed successfully" with no user-visible effect.
    rendition_report = persist_workflow_renditions(
        inputs, state, role="background_removed", results=results
    )

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

    # A run that produced nothing must SAY so — shared so every image tool
    # reports a no-op identically (absence-read-as-success).
    persisted = rendition_report.get("renditions") or []
    no_effect = describe_no_effect(files, output_files, rendition_report)
    if no_effect:
        logger.warning("remove_background_images: %s", no_effect)

    return {
        "output_files": output_files,
        "files": output_files,
        "count": len(output_files),
        "results": results,
        "image_edit_operations": image_edit_operations,
        "renditions": persisted,
        "rendition_report": rendition_report,
        # Surfaced in the run log, not just returned: the caller should not
        # have to infer a no-op from an empty list.
        "no_effect": no_effect,
        "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None),
    }
