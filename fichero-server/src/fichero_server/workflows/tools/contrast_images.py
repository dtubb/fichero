"""Contrast images: the `contrast` enhancement step as a workflow node (`image.enhance.three-doors-one-function`, #6194).

The pixels are `media.enhance.contrast.run`, the function the editor's contrast row and the chain render also call; the node
config is built from `contrast.Params`. With no CLAHE field and no `factor` given the node is the CLAHE step at the
`handwritten` profile (the step's defaults), which is how a recipe runs it by itself. Sources are never written.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.media.enhance import contrast as contrast_step
from fichero_server.media.enhance import node_config
from fichero_server.media.image_flatten import flatten_for_opaque_format
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.image_edit_chains import (
    append_image_edit_operations,
    describe_no_effect,
    persist_workflow_renditions,
)
from fichero_server.workflows.tools.run_scratch import run_scratch_dir
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
_ALLOWED_FORMATS = {"jpg", "jpeg", "png", "tiff", "webp"}

CONTRAST_IMAGES_CONFIG = {
    **node_config(contrast_step.Params),
    "output_format": {"type": "string", "enum": ["jpg", "png", "tiff", "webp"], "default": "jpg", "description": "Derived image format."},
    "compression_quality": {"type": "integer", "default": 90, "minimum": 1, "maximum": 100, "description": "JPEG/WebP compression quality."},
    "output_dir": {"type": "string", "default": "", "description": "Optional output directory. Defaults to a temp directory."},
}


def _step_params(given: dict[str, Any]) -> dict[str, Any]:
    """The params the step is called with: the fields the config names and the person set. `factor` alone is the old PIL
    contrast; with nothing set the node is the CLAHE step at its `handwritten` profile."""
    chosen = {k: given[k] for k in contrast_step.Params.model_fields if given.get(k) is not None}
    if not chosen:
        chosen["profile"] = "handwritten"
    return chosen


def _normalise_format(output_format: str) -> str:
    fmt = (output_format or "jpg").lower().lstrip(".")
    if fmt not in _ALLOWED_FORMATS:
        raise ValueError(f"Unsupported output format: {output_format}")
    return "jpeg" if fmt == "jpg" else fmt


def contrast_image_file(
    file_path: str | Path,
    output_dir: str | Path,
    *,
    output_format: str = "jpg",
    compression_quality: int = 90,
    **given: Any,
) -> dict[str, Any]:
    """Apply the contrast step to one image into a derived output file; `given` are the step's params."""
    source = Path(file_path)
    fmt = _normalise_format(output_format)
    ext = "jpg" if fmt == "jpeg" else fmt
    try:
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")
        from PIL import Image

        chosen = _step_params(given)
        with Image.open(source) as image:
            original_size = list(image.size)
            params = contrast_step.Params(**chosen)
            prepared, account = contrast_step.run(image.copy(), params)
            output_path = Path(output_dir) / f"{source.stem}.{ext}"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            save_kwargs: dict[str, Any] = {"format": "JPEG" if fmt == "jpeg" else fmt.upper()}
            if fmt in {"jpeg", "webp"}:
                save_kwargs["quality"] = max(1, min(100, int(compression_quality)))
            (flatten_for_opaque_format(prepared) if fmt == "jpeg" else prepared).save(output_path, **save_kwargs)
        return {
            "source": str(source), "outputs": [str(output_path)], "output_files": [str(output_path)],
            "details": {"original_size": original_size, "prepared_size": list(prepared.size), "output_format": ext,
                        "account": account, "params": chosen},
            "error": None,
        }
    except Exception as exc:
        logger.warning("contrast_images failed for %s: %s", source, exc)
        return {"source": str(source), "outputs": [], "output_files": [], "details": {}, "error": str(exc)}


@register_tool(
    name="contrast_images",
    display_name="Contrast Images",
    description="Even out the light on a page with local contrast (CLAHE on the lightness channel), without modifying source files.",
    category="transform",
    icon="wand.and.rays",
    color="orange",
    uses_llm=False,
    supports_batch=True,
    input_ports=[
        PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES, required=True,
                description="Image files to adjust."),
        PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False,
                description="Document metadata for preview-editor edit-chain updates."),
    ],
    output_ports=[
        PortDef(id="output_files", name="Adjusted Files", port_type="output", data_type=DataType.FILES,
                description="Contrast-adjusted derived image files."),
    ],
    config_schema=CONTRAST_IMAGES_CONFIG,
    sort_order=27,
)
async def contrast_images(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    """Apply the contrast step to the input images."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]
    output_dir = inputs.get("output_dir") or str(run_scratch_dir(state, "contrast-images"))
    results = [
        contrast_image_file(
            file_path, output_dir,
            output_format=inputs.get("output_format", "jpg"),
            compression_quality=inputs.get("compression_quality", 90),
            **{k: inputs.get(k) for k in contrast_step.Params.model_fields},
        )
        for file_path in files
    ]
    image_edit_operations = append_image_edit_operations(
        inputs, state,
        lambda _doc: {"op": "contrast", "page": int(inputs.get("page", 1)),
                      "params": _step_params({k: inputs.get(k) for k in contrast_step.Params.model_fields})},
    )
    rendition_report = persist_workflow_renditions(inputs, state, role="enhanced", results=results)
    output_files = [path for result in results for path in result.get("outputs", [])]
    no_effect = describe_no_effect(files, output_files, rendition_report)
    if no_effect:
        logger.warning("contrast_images: %s", no_effect)
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
