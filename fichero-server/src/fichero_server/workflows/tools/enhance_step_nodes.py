"""Enhancement steps as workflow nodes: `stain_flatten_images` and `ruled_lines_images` (`image.enhance.stain-flattening`,
`image.enhance.ruled-lines`, #6195).

Each node's pixels are the step's `run` in `media.enhance`, the function the editor's chain row also calls; the node's config
is built from the step's `Params`. A run writes an `enhanced` rendition whose `steps` row names the step and the settings
given, and appends the step's operation to the document's edit chain so the preview shows it. Sources are never written.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.media.enhance import STEPS, node_config
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
_FORMATS = {"jpg": "JPEG", "jpeg": "JPEG", "png": "PNG", "tiff": "TIFF", "webp": "WEBP"}
_OUTPUT_CONFIG = {
    "output_format": {"type": "string", "enum": ["jpg", "png", "tiff", "webp"], "default": "jpg", "description": "Derived image format."},
    "compression_quality": {"type": "integer", "default": 90, "minimum": 1, "maximum": 100, "description": "JPEG/WebP compression quality."},
    "output_dir": {"type": "string", "default": "", "description": "Optional output directory. Defaults to a temp directory."},
}


def _chosen(step: str, given: dict[str, Any]) -> dict[str, Any]:
    return {k: given[k] for k in STEPS[step].params.model_fields if given.get(k) is not None}


def step_image_file(step: str, file_path: str | Path, output_dir: str | Path, *, output_format: str = "jpg",
                    compression_quality: int = 90, **given: Any) -> dict[str, Any]:
    """Apply one enhancement step to one image into a derived output file."""
    source = Path(file_path)
    fmt = (output_format or "jpg").lower().lstrip(".")
    try:
        if fmt not in _FORMATS:
            raise ValueError(f"Unsupported output format: {output_format}")
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")
        from PIL import Image

        chosen = _chosen(step, given)
        spec = STEPS[step]
        with Image.open(source) as image:
            original_size = list(image.size)
            prepared, account = spec.run(image.copy(), spec.params(**chosen))
            output_path = Path(output_dir) / f"{source.stem}.{'jpg' if fmt == 'jpeg' else fmt}"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            save_kwargs: dict[str, Any] = {"format": _FORMATS[fmt]}
            if _FORMATS[fmt] in {"JPEG", "WEBP"}:
                save_kwargs["quality"] = max(1, min(100, int(compression_quality)))
            (flatten_for_opaque_format(prepared) if _FORMATS[fmt] == "JPEG" else prepared).save(output_path, **save_kwargs)
        return {
            "source": str(source), "outputs": [str(output_path)], "output_files": [str(output_path)],
            "details": {"original_size": original_size, "prepared_size": list(prepared.size), "account": account, "params": chosen},
            "steps": [{"step": step, "params": chosen, "card": {"method": account.get("method", step), "model_id": None}}],
            "error": None,
        }
    except Exception as exc:
        logger.warning("%s failed for %s: %s", step, source, exc)
        return {"source": str(source), "outputs": [], "output_files": [], "details": {}, "error": str(exc)}


def _register(tool: str, step: str, op: str, display: str, description: str, icon: str, sort_order: int) -> None:
    fields = list(STEPS[step].params.model_fields)

    async def node(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
        files = inputs.get("files") or state.get("input_files", [])
        if isinstance(files, str):
            files = [files]
        output_dir = inputs.get("output_dir") or str(run_scratch_dir(state, tool.replace("_", "-")))
        given = {k: inputs.get(k) for k in fields}
        results = [
            step_image_file(step, file_path, output_dir, output_format=inputs.get("output_format", "jpg"),
                            compression_quality=inputs.get("compression_quality", 90), **given)
            for file_path in files
        ]
        image_edit_operations = append_image_edit_operations(
            inputs, state, lambda _doc: {"op": op, "page": int(inputs.get("page", 1)), "params": _chosen(step, given)})
        rendition_report = persist_workflow_renditions(inputs, state, role="enhanced", results=results)
        output_files = [path for result in results for path in result.get("outputs", [])]
        no_effect = describe_no_effect(files, output_files, rendition_report)
        if no_effect:
            logger.warning("%s: %s", tool, no_effect)
        errors = [result["error"] for result in results if result.get("error")]
        return {
            "output_files": output_files, "renditions": rendition_report.get("renditions") or [],
            "rendition_report": rendition_report, "no_effect": no_effect, "files": output_files,
            "count": len(output_files), "results": results, "image_edit_operations": image_edit_operations,
            "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None),
        }

    node.__name__ = tool
    register_tool(
        name=tool, display_name=display, description=description, category="transform", icon=icon, color="orange",
        uses_llm=False, supports_batch=True,
        input_ports=[
            PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES, required=True, description="Image files to adjust."),
            PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False,
                    description="Document metadata for preview-editor edit-chain updates."),
        ],
        output_ports=[PortDef(id="output_files", name="Adjusted Files", port_type="output", data_type=DataType.FILES,
                              description="Derived image files.")],
        config_schema={**node_config(STEPS[step].params), **_OUTPUT_CONFIG}, sort_order=sort_order,
    )(node)
    globals()[tool] = node


_register("stain_flatten_images", "stain-flatten", "stain_flatten", "Flatten Stains",
          "Even out stains and shadows by dividing the page by a closing of its lightness, without modifying source files.",
          "drop.halffull", 28)
_register("ruled_lines_images", "ruled-lines", "ruled_lines", "Quiet Ruled Lines",
          "Fill thin, long green, blue or red ruling from the surrounding paper and keep the ink, without modifying source files.",
          "text.alignleft", 29)
