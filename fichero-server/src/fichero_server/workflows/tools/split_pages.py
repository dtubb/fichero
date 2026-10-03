"""Split pages: find the document in a photograph and cut an open spread at its gutter.

The `split-pages` job's built-in card (`prep.find-the-page`, `prep.split-at-the-gutter`, #5382).
Unlike `split_images` (a fixed grid, kept for regular grids), it cuts where the pages actually
meet: Apple Vision's document outline first, then the darkest column in the outline's middle
band, with a confidence (see `media/page_split.py` for the measured reasons). A closed notebook is
never cut; an unclear gutter is proposed for review, not cut. Pages come out in reading order as
child items of the photograph, each with its own rendition and `region_in_parent`, the same shape
the in-app split and `split_images` write. The source file is never changed.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.media import page_split
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.image_edit_chains import describe_no_effect, persist_workflow_child_regions
from fichero_server.workflows.tools.run_scratch import run_scratch_dir
from fichero_server.workflows.tools.split_images import (
    _IMAGE_SUFFIXES,
    _extension_for_format,
    _same_format_as,
    _save_image,
)
from fichero_server.workflows.types import DataType, PortDef, State

logger = logging.getLogger(__name__)

SPLIT_PAGES_CONFIG = {
    "direction": {
        "type": "string",
        "enum": ["ltr", "rtl"],
        "default": "ltr",
        "description": "Reading direction: the order the pages of a spread come out in.",
    },
    "use_apple_vision": {
        "type": "boolean",
        "default": True,
        "description": "Find the document with Apple Vision's outline; off, the whole image is the document.",
    },
    "min_confidence": {
        "type": "number",
        "default": page_split.MIN_GUTTER_CONFIDENCE,
        "minimum": 0.0,
        "maximum": 1.0,
        "description": "Below this gutter confidence a spread is proposed for review, not cut.",
    },
    "output_format": {
        "type": "string",
        "enum": ["jpg", "png", "tiff", "webp"],
        "description": "Format of the cut pages. Default: the source's own (a JPEG photo stays JPEG).",
    },
    "compression_quality": {"type": "integer", "default": 90, "minimum": 1, "maximum": 100,
                            "description": "JPEG/WebP compression quality."},
    "output_dir": {"type": "string", "default": "", "description": "Optional output directory."},
}


def split_pages_file(file_path: str | Path, output_dir: str | Path, *, direction: str = "ltr",
                     use_apple_vision: bool = True, min_confidence: float = page_split.MIN_GUTTER_CONFIDENCE,
                     output_format: str | None = None, compression_quality: int = 90,
                     outline: page_split.Outline | None = None) -> dict[str, Any]:
    """Cut one photograph into its page(s). `outline` overrides detection (tests, a person's correction).

    The image is read in its own pixel frame (no EXIF turn), the frame a child's `region_in_parent`
    is measured against, as `split_images` does."""
    source, output_root = Path(file_path), Path(output_dir)
    try:
        if source.suffix.lower() not in _IMAGE_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {source.suffix}")
        from PIL import Image
        import numpy as np

        with Image.open(source) as opened:
            image = opened.copy()
        if outline is None and use_apple_vision:
            outline = page_split.detect_document_outline(str(source))
        outline = outline or page_split.whole_frame(image.width, image.height)
        plan = page_split.split_plan_for_image(np.asarray(image.convert("L")), outline,
                                               direction=direction, min_confidence=min_confidence)
        fmt = output_format or _same_format_as(source)
        ext = _extension_for_format(fmt)
        output_root.mkdir(parents=True, exist_ok=True)
        parts, outputs = [], []
        for index, (x, y, w, h) in enumerate(plan["pages"], start=1):
            output = output_root / f"{source.stem}_page_{index:02d}.{ext}"
            _save_image(image.crop((x, y, x + w, y + h)), output, output_format=fmt,
                        compression_quality=compression_quality)
            outputs.append(str(output))
            parts.append({"part": index, "bbox": [x, y, w, h], "source_size": [image.width, image.height],
                          "output_file": str(output), "decision": plan["decision"]})
        return {"source": str(source), "outputs": outputs, "output_files": outputs, "parts": parts,
                "details": plan, "error": None}
    except Exception as exc:
        logger.warning("split_pages failed for %s: %s", source, exc)
        return {"source": str(source), "outputs": [], "output_files": [], "parts": [], "details": {},
                "error": str(exc)}


@register_tool(
    name="split_pages",
    display_name="Split Pages",
    description="Find the document in a photograph and cut an open book or notebook at its gutter "
    "into pages, in reading order; a closed cover or single page is kept whole, an unclear gutter "
    "is proposed for review. Sources are never changed.",
    category="transform",
    icon="book.pages",
    color="orange",
    uses_llm=False,
    supports_batch=True,
    input_ports=[PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES,
                         required=True, description="Photographs of documents.")],
    output_ports=[
        PortDef(id="output_files", name="Pages", port_type="output", data_type=DataType.FILES,
                description="The cut pages."),
        PortDef(id="parts", name="Parts", port_type="output", data_type=DataType.JSON,
                description="Each page's box in its photograph, and the decision for each photograph."),
    ],
    config_schema=SPLIT_PAGES_CONFIG,
    sort_order=32,
)
async def split_pages(inputs: dict[str, Any], state: State, llm_config: LLMConfig) -> dict[str, Any]:
    """Split each input photograph into its pages and attach them as child items."""
    files = inputs.get("files") or state.get("input_files", [])
    if isinstance(files, str):
        files = [files]
    output_dir = inputs.get("output_dir") or str(run_scratch_dir(state, "split-pages"))
    use_vision = bool(inputs.get("use_apple_vision", True))

    results = []
    for file_path in files:
        outline = None
        if use_vision:
            # Through the engine-wide Apple Vision gate and deadline (#5392): a stuck call fails
            # this photograph, not the run.
            from fichero_server.workflows.tools.vision_base import _apple_vision_call

            try:
                outline = await _apple_vision_call(page_split.detect_document_outline, str(file_path))
            except Exception as exc:  # the photo falls back to its whole frame, said so in details
                logger.warning("split_pages: no outline for %s (%s)", file_path, exc)
        results.append(split_pages_file(
            file_path, output_dir, direction=inputs.get("direction", "ltr"), use_apple_vision=False,
            min_confidence=float(inputs.get("min_confidence", page_split.MIN_GUTTER_CONFIDENCE)),
            output_format=inputs.get("output_format"),
            compression_quality=inputs.get("compression_quality", 90), outline=outline))

    # Only a real cut becomes child pages: a cover or a proposal is not a new page of the photograph.
    cut = [{**r, "parts": [p for p in r["parts"] if p["decision"] == "split"]} for r in results]
    child_report = persist_workflow_child_regions(inputs, state, results=cut, part_key="parts",
                                                  role="split_page", method="split-pages", name="page")
    output_files = [p["output_file"] for r in cut for p in r["parts"]]
    no_effect = describe_no_effect(files, output_files, {
        "renditions": child_report["children"],
        "already_children": child_report.get("already_children", 0),
        "skipped_reason": child_report.get("skipped_reason"),
    })
    decisions = [{"source": r["source"], **r["details"]} for r in results if r["details"]]
    errors = [r["error"] for r in results if r.get("error")]
    return {
        "output_files": output_files,
        "files": output_files,
        "count": len(output_files),
        "children": child_report["children"],
        "child_report": child_report,
        "no_effect": no_effect,
        "parts": [p for r in cut for p in r["parts"]],
        "decisions": decisions,
        "needs_review": [d["source"] for d in decisions if d.get("needs_review")],
        "results": results,
        "error": errors[0] if len(errors) == 1 else (f"{len(errors)} files failed" if errors else None),
    }
