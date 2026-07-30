"""Crop and magnify manuscript image regions without changing their source."""

from __future__ import annotations

import logging
import math
import tempfile
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools._doc_lookup import documents_from_state_outputs
from fichero_server.workflows.tools.enhance_images import _extension_for_format, _save_image
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}

ZOOM_CONFIG = {
    "mode": {"type": "string", "enum": ["region", "tile"], "default": "tile"},
    "x": {"type": "integer"},
    "y": {"type": "integer"},
    "width": {"type": "integer"},
    "height": {"type": "integer"},
    "rows": {"type": "integer", "default": 0, "minimum": 0, "description": "Line strips; 0 chooses from image height."},
    "overlap": {"type": "number", "default": 0.15, "minimum": 0.0, "maximum": 0.3},
    "scale": {"type": "number", "default": 2.0, "minimum": 1.0, "maximum": 6.0},
    "pdf_dpi": {"type": "integer", "default": 200, "minimum": 72, "maximum": 600},
    "output_format": {"type": "string", "enum": ["jpg", "png", "tiff", "webp"], "default": "jpg"},
    "compression_quality": {"type": "integer", "default": 90, "minimum": 1, "maximum": 100},
    "output_dir": {"type": "string", "default": ""},
}


def zoom_image_file(
    file_path: str | Path,
    output_dir: str | Path,
    *,
    mode: str = "tile",
    x: int | None = None,
    y: int | None = None,
    width: int | None = None,
    height: int | None = None,
    rows: int = 0,
    overlap: float = 0.15,
    scale: float = 2.0,
    pdf_dpi: int = 200,
    page_index: int | None = None,
    output_format: str = "jpg",
    compression_quality: int = 90,
) -> dict[str, Any]:
    """Write cropped, LANCZOS-upscaled derivatives for one image."""
    source = Path(file_path)
    output_root = Path(output_dir)
    try:
        if source.suffix.lower() not in _IMAGE_SUFFIXES | {".pdf"}:
            raise ValueError(f"Unsupported input file type: {source.suffix}")
        if mode not in {"region", "tile"}:
            raise ValueError("mode must be region or tile")
        scale = max(1.0, min(6.0, float(scale)))
        overlap = max(0.0, min(0.3, float(overlap)))
        from PIL import Image

        if source.suffix.lower() == ".pdf":
            from fichero_server.workflows.tools.prepare_images import _load_pages

            pages, _ = _load_pages(source, pdf_dpi=pdf_dpi)
            if page_index is not None:
                if not 0 <= page_index < len(pages):
                    raise ValueError(f"PDF page {page_index + 1} not found in: {source}")
                page_images = [(page_index, pages[page_index])]
            else:
                page_images = list(enumerate(pages))
        else:
            with Image.open(source) as image:
                page_images = [(None, image.copy())]

        outputs = []
        all_regions = []
        original_size = []
        for pdf_page_index, image in page_images:
            original_size = list(image.size)
            if mode == "region":
                if None in {x, y, width, height} or width <= 0 or height <= 0:
                    raise ValueError("region mode requires positive x, y, width, and height")
                if x < 0 or y < 0 or x + width > image.width or y + height > image.height:
                    raise ValueError("region is outside the source image")
                regions = [(x, y, x + width, y + height)]
            else:
                rows = int(rows)
                rows = rows if rows > 0 else max(1, math.ceil(image.height / 400))
                strip_height = math.ceil(image.height / rows)
                overlap_pixels = round(strip_height * overlap)
                regions = [
                    (
                        0,
                        max(0, index * strip_height - overlap_pixels),
                        image.width,
                        min(image.height, (index + 1) * strip_height + overlap_pixels),
                    )
                    for index in range(rows)
                ]

            ext = _extension_for_format(output_format)
            for index, region in enumerate(regions, start=1):
                cropped = image.crop(region)
                enlarged = cropped.resize(
                    (round(cropped.width * scale), round(cropped.height * scale)),
                    Image.Resampling.LANCZOS,
                )
                suffix = "region" if mode == "region" else f"tile-{index:02d}"
                page_suffix = (
                    f".page-{pdf_page_index + 1:03d}"
                    if pdf_page_index is not None
                    else ""
                )
                output_path = output_root / f"{source.stem}{page_suffix}.{suffix}.{ext}"
                _save_image(enlarged, output_path, output_format=output_format, compression_quality=compression_quality)
                outputs.append(str(output_path))
            all_regions.extend([list(region) for region in regions])
            image.close()

        return {"source": str(source), "outputs": outputs, "output_files": outputs, "details": {"original_size": original_size, "mode": mode, "scale": scale, "regions": all_regions}, "error": None}
    except Exception as exc:
        logger.warning("zoom failed for %s: %s", source, exc)
        return {"source": str(source), "outputs": [], "output_files": [], "details": {}, "error": str(exc)}


@register_tool(
    name="zoom", display_name="Zoom", description="Crop and magnify image regions or line strips.",
    category="transform", icon="plus.magnifyingglass", color="pink", uses_llm=False,
    supports_batch=True,
    input_ports=[
        PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES, required=True),
        PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False),
    ],
    output_ports=[
        PortDef(id="files", name="Files", port_type="output", data_type=DataType.FILES),
        PortDef(id="documents", name="Documents", port_type="output", data_type=DataType.JSON),
    ],
    config_schema=ZOOM_CONFIG, sort_order=27,
)
async def zoom(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    """Magnify supplied image files for downstream transcription."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]
    output_dir = inputs.get("output_dir") or str(Path(tempfile.gettempdir()) / "fichero-zoom")
    options = {key: inputs[key] for key in ZOOM_CONFIG if key in inputs and key != "output_dir"}
    # Page scoping (#4298): the paired document's `sequence` is what confines a
    # PDF to the ONE page the user selected. When a stored graph wires only the
    # `files` port (older stored copies of the ensemble preset predate #4146's
    # documents wiring, and preset_version was never bumped so they never
    # upgraded), the pairing is dropped and `page_index` stays None — this tool
    # then tiles EVERY page of the PDF and downstream vision passes bill the
    # whole document. Recover the index-aligned pairing from the upstream
    # node's recorded outputs, exactly like the vision tools do.
    documents = list(inputs.get("documents") or []) or documents_from_state_outputs(state, files)
    results = []
    for index, file_path in enumerate(files):
        document = documents[index] if index < len(documents) else None
        raw_page = document.get("sequence") if isinstance(document, dict) else None
        page_index = int(raw_page) - 1 if raw_page is not None else None
        results.append(
            zoom_image_file(file_path, output_dir, page_index=page_index, **options)
        )
    output_files = [path for result in results for path in result["outputs"]]
    output_documents = [
        documents[index]
        for index, result in enumerate(results)
        for _ in result["outputs"]
        if index < len(documents)
    ]
    errors = [result["error"] for result in results if result["error"]]
    return {"files": output_files, "documents": output_documents, "output_files": output_files, "count": len(output_files), "results": results, "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None)}
