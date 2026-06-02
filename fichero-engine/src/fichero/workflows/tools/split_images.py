"""Split images/PDF pages into derived files without modifying sources (#1394)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fichero.llm import LLMConfig
from fichero.workflows.registry import register_tool
from fichero.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
_ALLOWED_FORMATS = {"jpg", "jpeg", "png", "tiff", "webp"}

SPLIT_IMAGES_CONFIG = {
    "rows": {
        "type": "integer",
        "default": 1,
        "minimum": 1,
        "maximum": 20,
        "description": "Rows for image grid splitting.",
    },
    "columns": {
        "type": "integer",
        "default": 2,
        "minimum": 1,
        "maximum": 20,
        "description": "Columns for image grid splitting.",
    },
    "strategy": {
        "type": "string",
        "enum": ["grid", "auto"],
        "default": "grid",
        "description": "grid splits fixed rows/columns; auto detects two-page spreads using the restored archive OpenCV splitter.",
    },
    "pdf_dpi": {
        "type": "integer",
        "default": 200,
        "minimum": 72,
        "maximum": 600,
        "description": "DPI used when rendering PDF pages.",
    },
    "output_format": {
        "type": "string",
        "enum": ["jpg", "png", "tiff", "webp"],
        "default": "png",
        "description": "Derived split image format.",
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


def _to_jsonable(value: Any) -> Any:
    try:
        import numpy as np
    except ImportError:  # pragma: no cover - numpy is present in engine env
        np = None  # type: ignore[assignment]

    if np is not None:
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    return value


def _is_likely_single_cover_or_label(source: Path) -> bool:
    name = source.stem.lower()
    parent = source.parent.name.lower()
    label_patterns = ("_001", "_img_001", "cover", "label", "title", "front", "endpaper")
    photo_patterns = ("photo", "album", "photograph")
    is_first = any(part.isdigit() and int(part) == 1 for part in name.split("_"))
    return any(pattern in name for pattern in label_patterns) or is_first or any(
        pattern in parent for pattern in photo_patterns
    )


def _analyse_content_density(gray: Any) -> tuple[float, float]:
    import numpy as np

    height, width = gray.shape
    midpoint = width // 2
    threshold = 240
    left_content = np.sum(gray[:, :midpoint] < threshold)
    right_content = np.sum(gray[:, midpoint:] < threshold)
    half_pixels = height * midpoint
    return left_content / half_pixels, right_content / half_pixels


def _detect_auto_split_point(image: Any, source: Path) -> tuple[bool, int | None, dict[str, Any]]:
    """Detect double-page spreads using the known-good archive heuristics."""
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np
    except ImportError:
        return False, None, {"strategy": "auto", "reason": "opencv_unavailable"}

    width, height = image.size
    aspect_ratio = width / height
    debug: dict[str, Any] = {
        "strategy": "auto",
        "aspect_ratio": float(aspect_ratio),
        "should_split": False,
        "split_point": None,
    }
    if aspect_ratio < 1.2 or width < 1000:
        debug["reason"] = "not_wide_enough"
        return False, None, debug

    gray = np.array(image.convert("L"))
    edges = cv2.Canny(gray, 100, 200)
    edge_density = np.sum(edges > 0) / (width * height)
    text_density = np.mean(gray < 200)
    left_density, right_density = _analyse_content_density(gray)

    if _is_likely_single_cover_or_label(source):
        debug.update(
            {
                "reason": "cover_or_label_filename",
                "edge_density": float(edge_density),
                "text_density": float(text_density),
            }
        )
        return False, None, debug

    if min(left_density, right_density) < 0.02 and max(left_density, right_density) > 0.10:
        debug.update(
            {
                "reason": "one_side_empty",
                "content_density": {"left": float(left_density), "right": float(right_density)},
            }
        )
        return False, None, debug

    center_x = width // 2
    mid_region_start = max(0, int(width * 0.4))
    mid_region_end = min(width, int(width * 0.6))
    if aspect_ratio > 1.6:
        max_deviation = int(width * 0.1)
        mid_region_start = max(mid_region_start, center_x - max_deviation)
        mid_region_end = min(mid_region_end, center_x + max_deviation)

    vertical_sums = np.array([np.sum(gray[:, x]) / height for x in range(mid_region_start, mid_region_end)])
    if vertical_sums.size == 0:
        debug["reason"] = "empty_center_region"
        return False, None, debug

    local_index = int(np.argmin(vertical_sums))
    split_x = mid_region_start + local_index
    avg_darkness = float(vertical_sums[local_index])
    slice_start = max(0, local_index - 3)
    slice_end = min(vertical_sums.size, local_index + 4)
    avg_slice_value = float(np.mean(vertical_sums[slice_start:slice_end]))
    darkness_diff = avg_slice_value - avg_darkness
    vertical_pattern = float(np.std(np.diff(vertical_sums))) if vertical_sums.size > 1 else 0.0

    should_split = False
    if width > 2000 and aspect_ratio > 1.35 and text_density > 0.9 and abs(left_density - right_density) < 0.2:
        should_split = True
        split_x = center_x
    if not should_split and aspect_ratio > 1.4:
        if vertical_pattern > 10:
            should_split = darkness_diff > 3
        else:
            should_split = (avg_darkness < 180 and darkness_diff > 8) or darkness_diff > 15
    if aspect_ratio > 1.65 and not should_split:
        should_split = darkness_diff > 5
    if aspect_ratio > 1.35 and vertical_pattern > 1000:
        should_split = True
        search_range = min(200, center_x)
        min_sum = float("inf")
        split_x = center_x
        for x in range(center_x - search_range, min(width, center_x + search_range)):
            vertical_sum = np.sum(gray[:, x])
            if vertical_sum < min_sum:
                min_sum = vertical_sum
                split_x = x

    debug.update(
        _to_jsonable(
            {
                "should_split": bool(should_split),
                "split_point": int(split_x),
                "avg_darkness": avg_darkness,
                "darkness_diff": float(darkness_diff),
                "vertical_pattern": vertical_pattern,
                "edge_density": float(edge_density),
                "text_density": float(text_density),
                "content_density": {"left": float(left_density), "right": float(right_density)},
                "mid_region_start": int(mid_region_start),
                "mid_region_end": int(mid_region_end),
            }
        )
    )
    return bool(should_split), int(split_x), debug


def _split_image_auto(
    image: Any,
    source: Path,
    output_root: Path,
    *,
    output_format: str,
    compression_quality: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    ext = _extension_for_format(output_format)
    should_split, split_x, debug = _detect_auto_split_point(image, source)
    width, height = image.size
    boxes = [(0, 0, width, height)]
    if should_split and split_x is not None:
        boxes = [(0, 0, split_x, height), (split_x, 0, width, height)]

    outputs: list[str] = []
    parts: list[dict[str, Any]] = []
    for index, box in enumerate(boxes, start=1):
        cropped = image.crop(box)
        suffix = f"_part_{index:03d}" if len(boxes) > 1 else ""
        output_path = output_root / f"{source.stem}{suffix}.{ext}"
        _save_image(
            cropped,
            output_path,
            output_format=output_format,
            compression_quality=compression_quality,
        )
        left, top, right, bottom = box
        outputs.append(str(output_path))
        parts.append(
            {
                "part": index,
                "bbox": [left, top, right - left, bottom - top],
                "output_file": str(output_path),
                "debug": debug,
            }
        )
    return outputs, parts


def _split_image_grid(
    image: Any,
    source_stem: str,
    output_root: Path,
    *,
    rows: int,
    columns: int,
    output_format: str,
    compression_quality: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    rows = max(1, min(20, int(rows)))
    columns = max(1, min(20, int(columns)))
    ext = _extension_for_format(output_format)
    tile_width = image.width // columns
    tile_height = image.height // rows
    outputs: list[str] = []
    parts: list[dict[str, Any]] = []
    index = 0
    for row in range(rows):
        for column in range(columns):
            index += 1
            left = column * tile_width
            top = row * tile_height
            right = image.width if column == columns - 1 else left + tile_width
            bottom = image.height if row == rows - 1 else top + tile_height
            cropped = image.crop((left, top, right, bottom))
            output_path = output_root / f"{source_stem}_part_{index:03d}.{ext}"
            _save_image(
                cropped,
                output_path,
                output_format=output_format,
                compression_quality=compression_quality,
            )
            outputs.append(str(output_path))
            parts.append(
                {
                    "part": index,
                    "row": row + 1,
                    "column": column + 1,
                    "bbox": [left, top, right - left, bottom - top],
                    "output_file": str(output_path),
                }
            )
    return outputs, parts


def _split_pdf_pages(
    source: Path,
    output_root: Path,
    *,
    pdf_dpi: int,
    output_format: str,
    compression_quality: int,
) -> tuple[list[str], list[dict[str, Any]]]:
    try:
        import fitz  # type: ignore[import-not-found]
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on local extras
        raise RuntimeError("PDF splitting requires PyMuPDF and Pillow") from exc

    ext = _extension_for_format(output_format)
    doc = fitz.open(source)
    zoom = max(72, min(600, int(pdf_dpi))) / 72
    matrix = fitz.Matrix(zoom, zoom)
    outputs: list[str] = []
    parts: list[dict[str, Any]] = []
    for index, page in enumerate(doc, start=1):
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        output_path = output_root / f"{source.stem}_page_{index:03d}.{ext}"
        _save_image(
            image,
            output_path,
            output_format=output_format,
            compression_quality=compression_quality,
        )
        outputs.append(str(output_path))
        parts.append(
            {
                "part": index,
                "page": index,
                "bbox": [0, 0, pix.width, pix.height],
                "output_file": str(output_path),
            }
        )
    doc.close()
    return outputs, parts


def split_image_file(
    file_path: str | Path,
    output_dir: str | Path,
    *,
    strategy: str = "grid",
    rows: int = 1,
    columns: int = 2,
    pdf_dpi: int = 200,
    output_format: str = "png",
    compression_quality: int = 90,
) -> dict[str, Any]:
    """Split one image/PDF into derived output files."""
    source = Path(file_path)
    output_root = Path(output_dir)

    try:
        if source.suffix.lower() == ".pdf":
            outputs, parts = _split_pdf_pages(
                source,
                output_root,
                pdf_dpi=pdf_dpi,
                output_format=output_format,
                compression_quality=compression_quality,
            )
            split_mode = "pdf_pages"
        else:
            if source.suffix.lower() not in _IMAGE_SUFFIXES:
                raise ValueError(f"Unsupported input file type: {source.suffix}")
            from PIL import Image

            with Image.open(source) as image:
                image_copy = image.copy()
            if (strategy or "grid").strip().lower() == "auto":
                outputs, parts = _split_image_auto(
                    image_copy,
                    source,
                    output_root,
                    output_format=output_format,
                    compression_quality=compression_quality,
                )
                split_mode = "auto"
            else:
                outputs, parts = _split_image_grid(
                    image_copy,
                    source.stem,
                    output_root,
                    rows=rows,
                    columns=columns,
                    output_format=output_format,
                    compression_quality=compression_quality,
                )
                split_mode = "grid"

        return {
            "source": str(source),
            "outputs": outputs,
            "output_files": outputs,
            "parts": parts,
            "details": {
                "split_mode": split_mode,
                "rows": rows,
                "columns": columns,
                "total_parts": len(parts),
            },
            "error": None,
        }
    except Exception as exc:
        logger.warning("split_images failed for %s: %s", source, exc)
        return {
            "source": str(source),
            "outputs": [],
            "output_files": [],
            "parts": [],
            "details": {},
            "error": str(exc),
        }


@register_tool(
    name="split_images",
    display_name="Split Images",
    description="Split images into grid tiles or PDFs into page images without modifying sources.",
    category="transform",
    icon="rectangle.split.3x1",
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
            description="Image/PDF files to split.",
        ),
    ],
    output_ports=[
        PortDef(
            id="output_files",
            name="Split Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Split derived files.",
        ),
        PortDef(
            id="parts",
            name="Parts",
            port_type="output",
            data_type=DataType.JSON,
            description="Split part metadata.",
        ),
    ],
    config_schema=SPLIT_IMAGES_CONFIG,
    sort_order=31,
)
async def split_images(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Split input images/PDFs for downstream workflows."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]

    output_dir = inputs.get("output_dir") or str(
        Path(tempfile.gettempdir()) / "fichero-split-images"
    )
    results = [
        split_image_file(
            file_path,
            output_dir,
            rows=inputs.get("rows", 1),
            columns=inputs.get("columns", 2),
            strategy=inputs.get("strategy", "grid"),
            pdf_dpi=inputs.get("pdf_dpi", 200),
            output_format=inputs.get("output_format", "png"),
            compression_quality=inputs.get("compression_quality", 90),
        )
        for file_path in files
    ]

    output_files = [path for result in results for path in result.get("outputs", [])]
    parts = [part for result in results for part in result.get("parts", [])]
    errors = [result["error"] for result in results if result.get("error")]
    return {
        "output_files": output_files,
        "files": output_files,
        "count": len(output_files),
        "parts": parts,
        "results": results,
        "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None),
    }
