"""Recombine segment image files into a derived image (#1392)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_ALLOWED_FORMATS = {"jpg", "jpeg", "png", "tiff", "webp"}
_ALLOWED_LAYOUTS = {"horizontal", "vertical"}

RECOMBINE_SEGMENTS_CONFIG = {
    "layout": {
        "type": "string",
        "enum": ["horizontal", "vertical"],
        "default": "vertical",
        "description": "How segment images should be stitched together.",
    },
    "padding": {
        "type": "integer",
        "default": 0,
        "minimum": 0,
        "maximum": 200,
        "description": "Pixels between segment images.",
    },
    "background": {
        "type": "string",
        "default": "white",
        "description": "Background color for padding/empty area.",
    },
    "output_format": {
        "type": "string",
        "enum": ["jpg", "png", "tiff", "webp"],
        "default": "png",
        "description": "Derived recombined image format.",
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


def recombine_segment_files(
    files: list[str | Path],
    output_dir: str | Path,
    *,
    layout: str = "vertical",
    padding: int = 0,
    background: str = "white",
    output_format: str = "png",
    compression_quality: int = 90,
) -> dict[str, Any]:
    """Stitch segment files into a single derived image."""
    output_root = Path(output_dir)
    layout = (layout or "vertical").strip().lower()
    if layout not in _ALLOWED_LAYOUTS:
        raise ValueError(f"Unsupported recombine layout: {layout}")
    padding = max(0, min(200, int(padding)))
    ext = _extension_for_format(output_format)

    try:
        from PIL import Image

        paths = [Path(path) for path in files]
        images = [Image.open(path).convert("RGB") for path in paths]
        if not images:
            raise ValueError("No segment files provided")

        if layout == "horizontal":
            width = sum(image.width for image in images) + padding * (len(images) - 1)
            height = max(image.height for image in images)
            offsets = []
            cursor = 0
            for image in images:
                offsets.append([cursor, 0])
                cursor += image.width + padding
        else:
            width = max(image.width for image in images)
            height = sum(image.height for image in images) + padding * (len(images) - 1)
            offsets = []
            cursor = 0
            for image in images:
                offsets.append([0, cursor])
                cursor += image.height + padding

        combined = Image.new("RGB", (width, height), color=background)
        for image, offset in zip(images, offsets, strict=True):
            combined.paste(image, tuple(offset))
            image.close()

        output_path = output_root / f"recombined.{ext}"
        _save_image(
            combined,
            output_path,
            output_format=output_format,
            compression_quality=compression_quality,
        )

        return {
            "output_files": [str(output_path)],
            "files": [str(output_path)],
            "details": {
                "layout": layout,
                "padding": padding,
                "background": background,
                "segment_count": len(paths),
                "offsets": offsets,
                "output_size": [width, height],
            },
            "error": None,
        }
    except Exception as exc:
        logger.warning("recombine_segments failed: %s", exc)
        return {"output_files": [], "files": [], "details": {}, "error": str(exc)}


@register_tool(
    name="recombine_segments",
    display_name="Recombine Segments",
    description="Stitch segment image files into one derived image.",
    category="transform",
    icon="rectangle.connected.to.line.below",
    color="orange",
    uses_llm=False,
    supports_batch=True,
    input_ports=[
        PortDef(
            id="files",
            name="Segment Files",
            port_type="input",
            data_type=DataType.FILES,
            required=True,
            description="Segment image files to recombine.",
        ),
    ],
    output_ports=[
        PortDef(
            id="output_files",
            name="Recombined File",
            port_type="output",
            data_type=DataType.FILES,
            description="Recombined image file.",
        ),
    ],
    config_schema=RECOMBINE_SEGMENTS_CONFIG,
    sort_order=30,
)
async def recombine_segments(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Recombine segment images for downstream workflows."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]

    output_dir = inputs.get("output_dir") or str(
        Path(tempfile.gettempdir()) / "fichero-recombined-segments"
    )
    result = recombine_segment_files(
        list(files or []),
        output_dir,
        layout=inputs.get("layout", "vertical"),
        padding=inputs.get("padding", 0),
        background=inputs.get("background", "white"),
        output_format=inputs.get("output_format", "png"),
        compression_quality=inputs.get("compression_quality", 90),
    )
    return {
        "output_files": result["output_files"],
        "files": result["output_files"],
        "count": len(result["output_files"]),
        "results": [result],
        "details": result.get("details", {}),
        "error": result.get("error"),
    }
