"""Prepare image/PDF pages for OCR without modifying source files (#1390)."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools._doc_lookup import documents_from_state_outputs
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
_ALLOWED_FORMATS = {"jpeg", "jpg", "png", "tiff", "webp"}

PREPARE_IMAGES_CONFIG = {
    "output_format": {
        "type": "string",
        "enum": ["jpg", "png", "tiff", "webp"],
        "default": "jpg",
        "description": "Prepared image format.",
    },
    "compression_quality": {
        "type": "integer",
        "default": 85,
        "minimum": 1,
        "maximum": 100,
        "description": "JPEG/WebP compression quality.",
    },
    "grayscale": {
        "type": "boolean",
        "default": False,
        "description": "Convert prepared images to grayscale for OCR.",
    },
    "autocontrast": {
        "type": "boolean",
        "default": False,
        "description": "Apply autocontrast to improve low-contrast scans.",
    },
    "pdf_dpi": {
        "type": "integer",
        "default": 200,
        "minimum": 72,
        "maximum": 600,
        "description": "DPI used when rendering PDF pages.",
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


def _apply_exif_rotation(image: Any) -> tuple[Any, dict[str, Any]]:
    from PIL import ImageOps

    original_size = list(image.size)
    rotated = ImageOps.exif_transpose(image)
    prepared_size = list(rotated.size)
    return rotated, {
        "applied": prepared_size != original_size,
        "original_dimensions": original_size,
        "final_dimensions": prepared_size,
    }


def _prepare_image(image: Any, *, grayscale: bool, autocontrast: bool) -> Any:
    from PIL import ImageOps

    if grayscale:
        image = ImageOps.grayscale(image)
    elif image.mode not in {"RGB", "RGBA", "L"}:
        image = image.convert("RGB")

    if autocontrast:
        image = ImageOps.autocontrast(image)
    return image


def _save_prepared_image(
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
        save_kwargs["quality"] = compression_quality
    if fmt == "jpeg" and image.mode in {"RGBA", "P"}:
        image = image.convert("RGB")
    image.save(output_path, **save_kwargs)


def _load_pages(path: Path, *, pdf_dpi: int) -> tuple[list[Any], dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz  # type: ignore
            from PIL import Image
        except ImportError as exc:  # pragma: no cover - depends on local extras
            raise RuntimeError("PDF preparation requires PyMuPDF and Pillow") from exc

        doc = fitz.open(path)
        zoom = pdf_dpi / 72
        matrix = fitz.Matrix(zoom, zoom)
        pages = []
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            pages.append(Image.frombytes("RGB", [pix.width, pix.height], pix.samples))
        return pages, {"original_format": ".pdf", "total_pages": len(pages)}

    if suffix not in _IMAGE_SUFFIXES:
        raise ValueError(f"Unsupported input file type: {path.suffix}")

    from PIL import Image

    image = Image.open(path)
    return [image.copy()], {"original_format": path.suffix.lower(), "total_pages": 1}


def prepare_image_file(
    file_path: str | Path,
    output_dir: str | Path,
    *,
    output_format: str = "jpg",
    compression_quality: int = 85,
    grayscale: bool = False,
    autocontrast: bool = False,
    pdf_dpi: int = 200,
    page_index: int | None = None,
) -> dict[str, Any]:
    """Prepare one image/PDF into derived OCR-friendly image files.

    ``page_index`` (0-based) confines a PDF to that single page — a
    page-scoped run must never render, prepare, and feed EVERY page of the
    parent PDF downstream (#4298).
    """
    source = Path(file_path)
    output_root = Path(output_dir)
    ext = _extension_for_format(output_format)
    compression_quality = max(1, min(100, int(compression_quality)))

    try:
        pages, metadata = _load_pages(source, pdf_dpi=pdf_dpi)
        first_page_number = 1
        if page_index is not None and source.suffix.lower() == ".pdf":
            if not 0 <= page_index < len(pages):
                raise ValueError(f"PDF page {page_index + 1} not found in: {source}")
            pages = [pages[page_index]]
            first_page_number = page_index + 1
        outputs: list[str] = []
        page_details: list[dict[str, Any]] = []
        is_multipage = len(pages) > 1 or source.suffix.lower() == ".pdf"

        for idx, page in enumerate(pages, start=first_page_number):
            original_size = list(page.size)
            page, rotation = _apply_exif_rotation(page)
            page = _prepare_image(page, grayscale=grayscale, autocontrast=autocontrast)

            suffix = f"_page_{idx:03d}" if is_multipage else ""
            output_path = output_root / f"{source.stem}{suffix}.{ext}"
            _save_prepared_image(
                page,
                output_path,
                output_format=output_format,
                compression_quality=compression_quality,
            )
            outputs.append(str(output_path))
            page_details.append(
                {
                    "page": idx,
                    "original_size": original_size,
                    "prepared_size": list(page.size),
                    "rotation_applied": rotation,
                }
            )

        return {
            "source": str(source),
            "outputs": outputs,
            "output_files": outputs,
            "details": {
                "original_format": metadata["original_format"],
                "output_format": ext,
                "compression_quality": compression_quality,
                "total_pages": len(pages),
                "is_multipage": is_multipage,
                "grayscale": grayscale,
                "autocontrast": autocontrast,
                "pages": page_details,
            },
            "error": None,
        }
    except Exception as exc:
        logger.warning("prepare_images failed for %s: %s", source, exc)
        return {
            "source": str(source),
            "outputs": [],
            "output_files": [],
            "details": {},
            "error": str(exc),
        }


@register_tool(
    name="prepare_images",
    display_name="Prepare Images",
    description="Normalize images/PDF pages for OCR without modifying source files.",
    category="transform",
    icon="wand.and.stars",
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
            description="Image or PDF files to prepare.",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Document metadata for future preview-editor integration.",
        ),
    ],
    output_ports=[
        PortDef(
            id="output_files",
            name="Prepared Files",
            port_type="output",
            data_type=DataType.FILES,
            description="Prepared image files.",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="output",
            data_type=DataType.JSON,
            description="Documents index-aligned with the prepared files (#4298).",
        ),
    ],
    config_schema=PREPARE_IMAGES_CONFIG,
    sort_order=25,
)
async def prepare_images(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Prepare input images/PDF pages for downstream OCR."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]

    output_dir = inputs.get("output_dir") or str(
        Path(tempfile.gettempdir()) / "fichero-prepared-images"
    )
    # Page scoping (#4298): a page-scoped run pairs each file path with the
    # page document whose `sequence` confines the work to that ONE page. The
    # old code dropped the pairing entirely, so selecting one page of a PDF
    # rendered and prepared EVERY page for downstream OCR. Honor the wired
    # `documents` input; recover the pairing from the upstream node's recorded
    # outputs when the port isn't wired (older stored graphs).
    documents = list(inputs.get("documents") or []) or documents_from_state_outputs(state, files)
    results = []
    for index, file_path in enumerate(files):
        document = documents[index] if index < len(documents) else None
        raw_page = document.get("sequence") if isinstance(document, dict) else None
        page_index = int(raw_page) - 1 if raw_page is not None else None
        results.append(
            prepare_image_file(
                file_path,
                output_dir,
                output_format=inputs.get("output_format", "jpg"),
                compression_quality=inputs.get("compression_quality", 85),
                grayscale=bool(inputs.get("grayscale", False)),
                autocontrast=bool(inputs.get("autocontrast", False)),
                pdf_dpi=int(inputs.get("pdf_dpi", 200)),
                page_index=page_index,
            )
        )

    output_files = [path for result in results for path in result.get("outputs", [])]
    # Keep the (file, document) pairing alive downstream: one document per
    # emitted output, index-aligned like zoom does (#4146/#4298).
    output_documents = [
        documents[index]
        for index, result in enumerate(results)
        for _ in result.get("outputs", [])
        if index < len(documents)
    ]
    errors = [result["error"] for result in results if result.get("error")]
    return {
        "output_files": output_files,
        "files": output_files,
        "documents": output_documents,
        "count": len(output_files),
        "results": results,
        "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None),
    }
