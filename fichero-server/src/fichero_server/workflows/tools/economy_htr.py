"""Economy HTR: free Apple Vision line boxes + a cheap local HTR backend.

The ensemble paleography preset burns 15+ frontier-model calls per page. This
tool is the cheap middle of the economy pipeline (#lane/paleography 2026-08-25):

    Apple Vision line geometry (free, on-device)
      -> per-line strip crops (PIL, padded, upscaled)
      -> ONE local HTR backend per line (no paid API calls)
      -> canonical ``records`` port for an optional single cleanup pass

Backends (config ``backend``):
- ``apple``  — Apple Vision's own recognized text per line. Zero extra models;
  the floor/baseline every other backend must beat.
- ``trocr``  — any local TrOCR-family line model via ``transformers``
  (default: TRIDIS v1, MIT, trained on Old Spanish CODEA + medieval cursiva;
  needs ``transformers<5`` — v1 loads under 4.x, and v2's packaging is broken).
- ``kraken`` — kraken CLI with a CC-BY model (e.g. CATMuS Medieval) doing its
  own baseline segmentation on the full page image. Uses kraken's segmenter
  rather than Apple Vision boxes because kraken recognizers are trained
  against their own baseline geometry.

``transformers``/``kraken`` are NOT fichero dependencies; both backends
lazy-import and return a typed per-file error naming the missing piece —
never a silent fallback to a different backend (prefer-raise policy).

ponytail: images only — a PDF input errors and points at prepare_images;
add PDF page rendering here if a real workflow needs it.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools._doc_lookup import documents_from_state_outputs
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}

# TRIDIS v1, not v2: v2's hub packaging is internally inconsistent (input
# embeddings sized for RoBERTa's 50265-piece vocab, output head for an
# 8000-piece one) and cannot be loaded as published (bench, 2026-08-25).
DEFAULT_TROCR_MODEL = "magistermilitum/tridis_HTR"

ECONOMY_HTR_CONFIG = {
    "backend": {
        "type": "string",
        "enum": ["apple", "trocr", "kraken"],
        "default": "apple",
        "description": "Line HTR engine: apple=Vision text (free floor), trocr=local transformers line model, kraken=kraken CLI full-page.",
    },
    "model": {
        "type": "string",
        "default": DEFAULT_TROCR_MODEL,
        "description": "trocr backend: HF model id or local path (TrOCR family).",
    },
    "kraken_model_path": {
        "type": "string",
        "default": "",
        "description": "kraken backend: path to a .mlmodel (e.g. catmus-medieval.mlmodel).",
    },
    "language": {"type": "string", "default": "es"},
    "pad_x": {"type": "number", "default": 0.01, "minimum": 0.0, "maximum": 0.1},
    "pad_y": {"type": "number", "default": 0.35, "minimum": 0.0, "maximum": 1.0,
              "description": "Vertical padding as a fraction of line height (ascenders/descenders)."},
    "scale": {"type": "number", "default": 2.0, "minimum": 1.0, "maximum": 4.0},
    "batch_size": {"type": "integer", "default": 8, "minimum": 1, "maximum": 64},
    "min_line_confidence": {"type": "number", "default": 0.0, "minimum": 0.0, "maximum": 1.0},
    "keep_crops_dir": {"type": "string", "default": "",
                       "description": "Debug: write the line crops here instead of a temp dir."},
}


def crop_line_strips(
    image_path: str | Path,
    line_boxes: list[Any],
    *,
    pad_x: float = 0.01,
    pad_y: float = 0.35,
    scale: float = 2.0,
    out_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Crop one padded, LANCZOS-upscaled strip per Apple Vision line box.

    ``line_boxes`` carry top-left-origin NORMALIZED ``bbox`` [x, y, w, h]
    (VisionOCRBox). Returns [{"index", "bbox", "text", "path"}] in the given
    (reading) order; boxes whose padded rect collapses to nothing are skipped.
    """
    from PIL import Image

    source = Path(image_path)
    target_dir = Path(out_dir) if out_dir else Path(tempfile.mkdtemp(prefix="economy-htr-"))
    target_dir.mkdir(parents=True, exist_ok=True)

    crops: list[dict[str, Any]] = []
    with Image.open(source) as image:
        width, height = image.size
        for index, box in enumerate(line_boxes):
            x, y, w, h = box.bbox
            left = max(0, round((x - pad_x) * width))
            right = min(width, round((x + w + pad_x) * width))
            top = max(0, round((y - h * pad_y) * height))
            bottom = min(height, round((y + h * (1 + pad_y)) * height))
            if right - left < 2 or bottom - top < 2:
                continue
            strip = image.crop((left, top, right, bottom))
            strip = strip.resize(
                (round(strip.width * scale), round(strip.height * scale)),
                Image.Resampling.LANCZOS,
            ).convert("RGB")
            path = target_dir / f"{source.stem}.line-{index:03d}.png"
            strip.save(path, format="PNG")
            crops.append(
                {"index": index, "bbox": list(box.bbox), "text": box.text, "path": str(path)}
            )
    return crops


_TROCR_CACHE: dict[str, tuple[Any, Any, str]] = {}


def _load_trocr(model_id: str) -> tuple[Any, Any, str]:
    """Load and cache a TrOCR-family processor/model pair on MPS or CPU."""
    if model_id in _TROCR_CACHE:
        return _TROCR_CACHE[model_id]
    try:
        import torch
        from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    except ImportError as exc:
        raise RuntimeError(
            "economy_htr trocr backend needs the 'transformers' and 'torch' "
            f"packages (not fichero dependencies): {exc}"
        ) from exc
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    processor = TrOCRProcessor.from_pretrained(model_id)
    model = VisionEncoderDecoderModel.from_pretrained(model_id).to(device).eval()
    _TROCR_CACHE[model_id] = (processor, model, device)
    return _TROCR_CACHE[model_id]


def trocr_transcribe_lines(
    crop_paths: list[str], model_id: str, batch_size: int = 8
) -> list[str]:
    """Run a local TrOCR-family model over line crops, batched, in order."""
    import torch
    from PIL import Image

    processor, model, device = _load_trocr(model_id)
    texts: list[str] = []
    for start in range(0, len(crop_paths), batch_size):
        images = [Image.open(p).convert("RGB") for p in crop_paths[start:start + batch_size]]
        pixel_values = processor(images=images, return_tensors="pt").pixel_values.to(device)
        with torch.no_grad():
            generated = model.generate(pixel_values, max_new_tokens=128)
        texts.extend(processor.batch_decode(generated, skip_special_tokens=True))
        for image in images:
            image.close()
    return [t.strip() for t in texts]


def kraken_transcribe_page(image_path: str, model_path: str) -> str:
    """Full-page kraken CLI run: baseline segmentation + recognition."""
    if not model_path:
        raise RuntimeError(
            "economy_htr kraken backend needs kraken_model_path "
            "(e.g. catmus-medieval.mlmodel from zenodo.org/records/12743230)"
        )
    if not Path(model_path).exists():
        raise RuntimeError(f"kraken model not found: {model_path}")
    kraken_bin = shutil.which("kraken")
    if not kraken_bin:
        raise RuntimeError(
            "economy_htr kraken backend needs the 'kraken' CLI on PATH "
            "(pip install kraken; not a fichero dependency)"
        )
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as handle:
        out_path = handle.name
    result = subprocess.run(
        [kraken_bin, "-i", str(image_path), out_path, "segment", "-bl", "ocr", "-m", model_path],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(f"kraken failed ({result.returncode}): {result.stderr.strip()[:500]}")
    text = Path(out_path).read_text(encoding="utf-8")
    Path(out_path).unlink(missing_ok=True)
    return text.strip()


def economy_htr_file(
    file_path: str,
    *,
    backend: str = "apple",
    model: str = DEFAULT_TROCR_MODEL,
    kraken_model_path: str = "",
    language: str = "es",
    pad_x: float = 0.01,
    pad_y: float = 0.35,
    scale: float = 2.0,
    batch_size: int = 8,
    min_line_confidence: float = 0.0,
    keep_crops_dir: str = "",
) -> dict[str, Any]:
    """Transcribe one image; returns {text, lines, backend, error}."""
    source = Path(file_path)
    try:
        if source.suffix.lower() == ".pdf":
            raise ValueError(
                "economy_htr takes images only — run prepare_images / split the "
                "PDF into page images first"
            )
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")

        if backend == "kraken":
            text = kraken_transcribe_page(str(source), kraken_model_path)
            return {"source": str(source), "text": text, "lines": [], "backend": backend, "error": None}

        from fichero_server.workflows.tools.vision_base import (
            apple_vision_ocr_with_geometry,
        )

        geometry = apple_vision_ocr_with_geometry(str(source), language)
        line_boxes = [
            box
            for box in geometry.line_boxes
            if (box.confidence is None or box.confidence >= min_line_confidence)
        ]
        if not line_boxes:
            return {"source": str(source), "text": "", "lines": [], "backend": backend,
                    "error": "Apple Vision found no text lines"}

        if backend == "apple":
            lines = [{"index": i, "bbox": list(b.bbox), "text": b.text} for i, b in enumerate(line_boxes)]
            return {"source": str(source), "text": "\n".join(b.text for b in line_boxes),
                    "lines": lines, "backend": backend, "error": None}

        if backend == "trocr":
            crops = crop_line_strips(
                source, line_boxes, pad_x=pad_x, pad_y=pad_y, scale=scale,
                out_dir=keep_crops_dir or None,
            )
            texts = trocr_transcribe_lines([c["path"] for c in crops], model, batch_size)
            lines = []
            for crop, text in zip(crops, texts):
                lines.append({"index": crop["index"], "bbox": crop["bbox"],
                              "text": text, "apple_text": crop["text"],
                              "crop": crop["path"] if keep_crops_dir else None})
            if not keep_crops_dir and crops:
                shutil.rmtree(Path(crops[0]["path"]).parent, ignore_errors=True)
            return {"source": str(source), "text": "\n".join(ln["text"] for ln in lines),
                    "lines": lines, "backend": backend, "error": None}

        raise ValueError(f"Unknown backend: {backend}")
    except Exception as exc:
        logger.warning("economy_htr failed for %s: %s", source, exc)
        return {"source": str(source), "text": "", "lines": [], "backend": backend, "error": str(exc)}


@register_tool(
    name="economy_htr",
    display_name="Economy HTR",
    description="Free Apple Vision line boxes + a cheap local HTR backend (no paid API calls).",
    category="vision",
    icon="text.viewfinder",
    color="mint",
    uses_llm=False,
    supports_batch=True,
    input_ports=[
        PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES, required=True),
        PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False),
    ],
    output_ports=[
        PortDef(id="text", name="Text", port_type="output", data_type=DataType.TEXT),
        PortDef(id="records", name="Records", port_type="output", data_type=DataType.JSON),
        PortDef(id="files", name="Files", port_type="output", data_type=DataType.FILES),
        PortDef(id="documents", name="Documents", port_type="output", data_type=DataType.JSON),
    ],
    config_schema=ECONOMY_HTR_CONFIG,
    sort_order=28,
)
async def economy_htr(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    """Per-file economy HTR with the standard error isolation + records port."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]
    options = {key: inputs[key] for key in ECONOMY_HTR_CONFIG if key in inputs}
    documents = list(inputs.get("documents") or []) or documents_from_state_outputs(state, files)

    results = [economy_htr_file(file_path, **options) for file_path in files]

    records = []
    for index, result in enumerate(results):
        document = documents[index] if index < len(documents) else None
        doc_id = document.get("id") if isinstance(document, dict) else None
        if doc_id and result["text"]:
            records.append({"doc_id": doc_id, "text": result["text"]})

    errors = [r["error"] for r in results if r["error"]]
    return {
        "text": "\n\n".join(r["text"] for r in results if r["text"]),
        "texts": [r["text"] for r in results],
        "records": records,
        "results": results,
        # pass the originals through so a cleanup node can see the images
        "files": list(files),
        "documents": documents,
        "output_files": list(files),
        "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None),
    }
