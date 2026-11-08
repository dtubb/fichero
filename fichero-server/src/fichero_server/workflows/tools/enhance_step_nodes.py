"""Enhancement steps as workflow nodes: `stain_flatten_images`, `ruled_lines_images` and `bleed_through_images` (`image.enhance.stain-flattening`,
`image.enhance.ruled-lines`, #6195; `bleed_through_images`, `image.enhance.bleed-through-suppression`, #6196).

Each node's pixels are the step's `run` in `media.enhance`, the function the editor's chain row also calls; the node's config
is built from the step's `Params`. A run writes an `enhanced` rendition whose `steps` row names the step and the settings
given, and appends the step's operation to the document's edit chain so the preview shows it. Sources are never written.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from pydantic import BaseModel, Field

from fichero_server.media.enhance import STEPS, StepSpec, node_config
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


class _FlipParams(BaseModel):
    direction: str = Field("horizontal", pattern="^(horizontal|vertical)$", description="Mirror left to right, or top to bottom.")


class _NoParams(BaseModel):
    pass


def _by_chain_op(op_for: Any) -> Any:
    """A step whose pixels are an editor operation (`media.image_ops.apply_operation`): the node and the chain row run one function."""
    def run(image: Any, params: BaseModel) -> tuple[Any, dict[str, Any]]:
        from fichero_server.media.image_ops import apply_operation

        op = op_for(params)
        return apply_operation(image, {"op": op, "params": params.model_dump()}), {"method": op}
    return run


#: The nodes for operations that are not enhancement steps: the same registry shape, so `_register` serves both.
SPECS: dict[str, StepSpec] = {
    **STEPS,
    "flip": StepSpec("flip", _FlipParams, _by_chain_op(lambda p: f"flip_{p.direction}")),
    "grayscale": StepSpec("grayscale", _NoParams, _by_chain_op(lambda p: "grayscale")),
    "auto-levels": StepSpec("auto-levels", _NoParams, _by_chain_op(lambda p: "auto_levels")),
}


def _chosen(step: str, given: dict[str, Any]) -> dict[str, Any]:
    return {k: given[k] for k in SPECS[step].params.model_fields if given.get(k) is not None}


def step_image_file(step: str, file_path: str | Path, output_dir: str | Path, *, output_format: str = "jpg",
                    compression_quality: int = 90, verso: str | Path | None = None, **given: Any) -> dict[str, Any]:
    """Apply one enhancement step to one image into a derived output file. `verso` is the other side of the leaf, read by
    bleed-through method b."""
    source = Path(file_path)
    fmt = (output_format or "jpg").lower().lstrip(".")
    try:
        if fmt not in _FORMATS:
            raise ValueError(f"Unsupported output format: {output_format}")
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")
        from PIL import Image

        chosen = _chosen(step, given)
        spec = SPECS[step]
        with Image.open(source) as image:
            original_size = list(image.size)
            extra: dict[str, Any] = {}
            if step == "bleed-through" and chosen.get("method") == "b":
                if verso is None:
                    raise ValueError(f"bleed-through method b needs the verso of {source.name}")
                with Image.open(verso) as opened:
                    extra["verso"] = opened.convert("RGB")
            prepared, account = spec.run(image.copy(), spec.params(**chosen), **extra)
            if account.get("applied") is False and account.get("reason"):
                raise ValueError(f"{step}: {account['reason']}")
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


def _register(tool: str, step: str, op: Any, display: str, description: str, icon: str, sort_order: int,
              versos: bool = False, role: str = "enhanced") -> None:
    fields = list(SPECS[step].params.model_fields)

    async def node(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
        files = inputs.get("files") or state.get("input_files", [])
        if isinstance(files, str):
            files = [files]
        output_dir = inputs.get("output_dir") or str(run_scratch_dir(state, tool.replace("_", "-")))
        given = {k: inputs.get(k) for k in fields}
        verso_files = inputs.get("versos") or []
        if isinstance(verso_files, str):
            verso_files = [verso_files]
        results = [
            step_image_file(step, file_path, output_dir, output_format=inputs.get("output_format", "jpg"),
                            compression_quality=inputs.get("compression_quality", 90),
                            verso=verso_files[index] if index < len(verso_files) else None, **given)
            for index, file_path in enumerate(files)
        ]
        chosen = _chosen(step, given)
        # `op` is the editor's chain name; a step with no chain row of its own (yellowing and sharpness run inside Auto Enhance) is None
        row_op = op(chosen) if callable(op) else op
        image_edit_operations = append_image_edit_operations(
            inputs, state, lambda _doc: None if row_op is None else
            {"op": row_op, "page": int(inputs.get("page", 1)), "params": {} if step == "flip" else chosen})
        rendition_report = persist_workflow_renditions(inputs, state, role=role, results=results)
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
            *([PortDef(id="versos", name="Versos", port_type="input", data_type=DataType.FILES, required=False,
                       description="The other side of each file, in the same order (bleed-through method b).")] if versos else []),
        ],
        output_ports=[PortDef(id="output_files", name="Adjusted Files", port_type="output", data_type=DataType.FILES,
                              description="Derived image files.")],
        config_schema={**node_config(SPECS[step].params), **_OUTPUT_CONFIG}, sort_order=sort_order,
    )(node)
    globals()[tool] = node


_register("stain_flatten_images", "stain-flatten", "stain_flatten", "Flatten Stains",
          "Even out stains and shadows by dividing the page by a closing of its lightness, without modifying source files.",
          "drop.halffull", 28)
_register("ruled_lines_images", "ruled-lines", "ruled_lines", "Quiet Ruled Lines",
          "Fill thin, long green, blue or red ruling from the surrounding paper and keep the ink, without modifying source files.",
          "text.alignleft", 29)
_register("bleed_through_images", "bleed-through", "bleed_through", "Suppress Show-Through",
          "Push the faint mirrored writing of the other side to paper and keep the ink; method b also reads the verso, without modifying source files.",
          "doc.on.doc", 30, versos=True)
_register("binarise_images", "binarise", "binarise", "Binarise",
          "Black and white by Otsu or an adaptive threshold, written as a separate binarised rendition, without modifying source files.",
          "circle.lefthalf.filled", 32, role="binarised")
_register("yellowing_images", "yellowing", None, "Remove Yellowing",
          "Take the yellow cast out of the paper and keep the ink, written as an enhanced rendition, without modifying source files.",
          "sun.max", 31)
_register("sharpen_images", "sharpen", None, "Sharpen",
          "An unsharp mask on the lightness, written as an enhanced rendition, without modifying source files.",
          "scope", 33)
_register("flip_images", "flip", lambda chosen: f"flip_{chosen.get('direction', 'horizontal')}", "Flip",
          "Mirror each page left to right or top to bottom, without modifying source files.",
          "arrow.left.and.right.righttriangle.left.righttriangle.right", 34)
_register("grayscale_images", "grayscale", "grayscale", "Grayscale",
          "Take the colour out of each page, without modifying source files.", "circle.lefthalf.filled.righthalf.striped.horizontal", 35)
_register("auto_levels_images", "auto-levels", "auto_levels", "Auto Levels",
          "Stretch each page's lightness to the full range, without modifying source files.", "slider.horizontal.3", 36)
