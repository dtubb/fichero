"""Segment document image regions without modifying source files (#1391)."""

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

SEGMENT_IMAGES_CONFIG = {
    "method": {
        "type": "string",
        "enum": ["foreground", "page"],
        "default": "foreground",
        "description": "Segmentation method.",
    },
    "threshold": {
        "type": "integer",
        "default": 28,
        "minimum": 0,
        "maximum": 255,
        "description": "Foreground threshold for document-region detection.",
    },
    "min_area": {
        "type": "integer",
        "default": 100,
        "minimum": 1,
        "description": "Minimum segment area in pixels.",
    },
    "max_segments": {
        "type": "integer",
        "default": 20,
        "minimum": 1,
        "maximum": 200,
        "description": "Maximum number of regions to emit.",
    },
    "output_format": {
        "type": "string",
        "enum": ["jpg", "png", "tiff", "webp"],
        "default": "png",
        "description": "Derived segment image format.",
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


def detect_segments(
    image: Any,
    *,
    method: str = "foreground",
    threshold: int = 28,
    min_area: int = 100,
    max_segments: int = 20,
) -> list[dict[str, Any]]:
    """Detect foreground connected-component regions."""
    method = (method or "foreground").strip().lower()
    if method == "page":
        return [{"bbox": [0, 0, image.width, image.height], "area": image.width * image.height, "segment_type": "page"}]
    if method != "foreground":
        raise ValueError(f"Unsupported segmentation method: {method}")

    from PIL import Image, ImageChops

    threshold = max(0, min(255, int(threshold)))
    min_area = max(1, int(min_area))
    max_segments = max(1, min(200, int(max_segments)))
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, rgb.getpixel((0, 0)))
    diff = ImageChops.difference(rgb, background).convert("L")
    mask = diff.point(lambda value: 255 if value > threshold else 0)
    pixels = mask.load()
    width, height = mask.size
    visited: set[tuple[int, int]] = set()
    segments: list[dict[str, Any]] = []

    for y in range(height):
        for x in range(width):
            if (x, y) in visited or pixels[x, y] == 0:
                continue
            stack = [(x, y)]
            visited.add((x, y))
            min_x = max_x = x
            min_y = max_y = y
            area = 0
            while stack:
                px, py = stack.pop()
                area += 1
                min_x = min(min_x, px)
                max_x = max(max_x, px)
                min_y = min(min_y, py)
                max_y = max(max_y, py)
                for nx, ny in ((px - 1, py), (px + 1, py), (px, py - 1), (px, py + 1)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height:
                        continue
                    if (nx, ny) in visited or pixels[nx, ny] == 0:
                        continue
                    visited.add((nx, ny))
                    stack.append((nx, ny))
            if area >= min_area:
                segments.append(
                    {
                        "bbox": [min_x, min_y, max_x - min_x + 1, max_y - min_y + 1],
                        "area": area,
                        "segment_type": "foreground",
                    }
                )
    segments.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))
    return segments[:max_segments]


def segment_image_file(
    file_path: str | Path,
    output_dir: str | Path,
    *,
    method: str = "foreground",
    threshold: int = 28,
    min_area: int = 100,
    max_segments: int = 20,
    output_format: str = "png",
    compression_quality: int = 90,
) -> dict[str, Any]:
    """Segment one image into cropped derived files."""
    source = Path(file_path)
    output_root = Path(output_dir)
    ext = _extension_for_format(output_format)

    try:
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")

        from PIL import Image

        with Image.open(source) as image:
            original = image.copy()
            segments = detect_segments(
                original,
                method=method,
                threshold=threshold,
                min_area=min_area,
                max_segments=max_segments,
            )
            outputs: list[str] = []
            for index, segment in enumerate(segments, start=1):
                left, top, width, height = segment["bbox"]
                cropped = original.crop((left, top, left + width, top + height))
                output_path = output_root / f"{source.stem}_segment_{index:03d}.{ext}"
                _save_image(
                    cropped,
                    output_path,
                    output_format=output_format,
                    compression_quality=compression_quality,
                )
                outputs.append(str(output_path))

        return {
            "source": str(source),
            "outputs": outputs,
            "output_files": outputs,
            "segments": segments,
            "details": {
                "original_format": source.suffix.lower(),
                "output_format": ext,
                "total_segments": len(segments),
                "method": method,
                "threshold": threshold,
                "min_area": min_area,
                "max_segments": max_segments,
            },
            "error": None,
        }
    except Exception as exc:
        logger.warning("segment_images failed for %s: %s", source, exc)
        return {
            "source": str(source),
            "outputs": [],
            "output_files": [],
            "segments": [],
            "details": {},
            "error": str(exc),
        }


@register_tool(
    name="segment_images",
    display_name="Segment Images",
    description="Detect foreground document regions and emit cropped segment derivatives.",
    category="transform",
    icon="square.split.2x2",
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
            description="Image files to segment.",
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
            name="Segment Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Cropped segment image files.",
        ),
        PortDef(
            id="segments",
            name="Segments",
            port_type="output",
            data_type=DataType.JSON,
            description="Detected segment bounding boxes.",
        ),
    ],
    config_schema=SEGMENT_IMAGES_CONFIG,
    sort_order=29,
)
async def segment_images(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Segment input images for downstream editing workflows."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]

    output_dir = inputs.get("output_dir") or str(
        Path(tempfile.gettempdir()) / "fichero-segmented-images"
    )
    params = {
        "method": inputs.get("method", "foreground"),
        "threshold": int(inputs.get("threshold", 28)),
        "min_area": int(inputs.get("min_area", 100)),
        "max_segments": int(inputs.get("max_segments", 20)),
    }
    results = [
        segment_image_file(
            file_path,
            output_dir,
            **params,
            output_format=inputs.get("output_format", "png"),
            compression_quality=inputs.get("compression_quality", 90),
        )
        for file_path in files
    ]

    all_segments = [segment for result in results for segment in result.get("segments", [])]
    image_edit_operations = append_image_edit_operations(
        inputs,
        state,
        lambda _doc: {
            "op": "segment",
            "page": int(inputs.get("page", 1)),
            "params": params,
            "segments": all_segments,
        },
    )

    output_files = [path for result in results for path in result.get("outputs", [])]
    errors = [result["error"] for result in results if result.get("error")]
    return {
        "output_files": output_files,
        "files": output_files,
        "count": len(output_files),
        "segments": all_segments,
        "results": results,
        "image_edit_operations": image_edit_operations,
        "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None),
    }
