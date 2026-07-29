"""Split images/PDF pages into derived files without modifying sources (#1394)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.types import DataType, PortDef, State

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
                outputs, parts = _split_image_grid(
                    image.copy(),
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
