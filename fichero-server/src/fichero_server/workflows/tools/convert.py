"""
Convert Tool

Converts images to structured text formats (HTML, SVG, Markdown).
Inherits from vision_base.py - excellent for recreating document content.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fichero_server.workflows.types import State
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import BASE_OUTPUT_PORTS, merge_config_schema
from fichero_server.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VISION_CONFIG_SCHEMA,
    VisionToolConfig,
    process_vision,
)
from fichero_server.llm import LLMConfig
from fichero_server.security.xml_security import parse_xml_string

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VisionToolConfig(
    artifact_type="conversion",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
)

CONVERT_CONFIG = {
    "target_format": {
        "type": "string",
        "enum": ["markdown", "html", "svg", "latex", "csv"],
        "default": "markdown",
        "description": "Output format",
    },
    "preserve_layout": {
        "type": "boolean",
        "default": True,
        "description": "Keep original layout",
    },
    "include_styles": {
        "type": "boolean",
        "default": False,
        "description": "Include CSS/styling",
    },
}


# =============================================================================
# Output Sanitization / Validation (#4329)
# =============================================================================

# The whole output wrapped in a single code fence — models add this despite
# the "no code fences" instruction.
_FENCE_RE = re.compile(r"^```[a-zA-Z0-9_+-]*[ \t]*\n(.*)\n?```\s*$", re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b.*?</script\s*>", re.IGNORECASE | re.DOTALL)
_EVENT_ATTR_RE = re.compile(
    r"\s+on[a-zA-Z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE
)
_JS_URL_RE = re.compile(
    r"(href|xlink:href|src)\s*=\s*([\"'])\s*javascript:[^\"']*\2", re.IGNORECASE
)


def sanitize_converted_markup(text: str, target_format: str) -> str:
    """Sanitize + validate model-generated markup BEFORE it is saved/rendered.

    The converted artifact renders in WebKit (#4329), so:
      * strip a whole-output code fence (models add one despite instructions);
      * for html/svg: remove `<script>` blocks, inline `on*=` handlers, and
        `javascript:` URLs — renditions are documents, never active content;
      * for svg: require a well-formed `<svg>` XML document — malformed output
        raises (fail loud, per-file) instead of persisting a broken artifact.
    """
    out = (text or "").strip()
    fenced = _FENCE_RE.match(out)
    if fenced:
        out = fenced.group(1).strip()

    if target_format in ("html", "svg"):
        out = _SCRIPT_RE.sub("", out)
        out = _EVENT_ATTR_RE.sub("", out)
        out = _JS_URL_RE.sub(r"\1=\2#\2", out)

    if target_format == "svg":
        if "<svg" not in out[:500].lower():
            raise ValueError(
                "Convert produced no <svg> root for target_format=svg; "
                "refusing to save a non-SVG rendition"
            )
        try:
            parse_xml_string(out)
        except Exception as exc:
            raise ValueError(
                f"Convert produced malformed SVG (not well-formed XML: {exc}); "
                "refusing to save an unrenderable rendition"
            ) from exc

    return out


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(
    target_format: str, preserve_layout: bool, include_styles: bool
) -> str:
    """Build the conversion prompt."""
    layout_instruction = ""
    if preserve_layout:
        layout_instruction = "\n\nIMPORTANT: Faithfully reproduce the original layout, spacing, and visual structure. Match positions, alignment, and proportions as closely as possible."

    style_text = ""
    if include_styles and target_format in ("html", "svg"):
        style_text = "\nInclude styling (colors, fonts, spacing) to match the original appearance."

    format_instructions = {
        "markdown": f"""Convert this image to Markdown format.
- Use proper heading levels (# ## ###)
- Use tables for tabular data
- Use lists for enumerated items
- Use code blocks for code/technical content
- Use > for quotes or callouts{layout_instruction}{style_text}""",
        "html": f"""Convert this image to semantic HTML that reproduces the original layout.
- Use proper heading tags (h1-h6)
- Use <table> for tabular data
- Use <ul>/<ol> for lists
- Use <figure> for images/diagrams
- Use <blockquote> for quotes
- Use CSS positioning/flexbox to match the spatial layout{layout_instruction}{style_text}""",
        "svg": f"""Recreate this image as SVG (Scalable Vector Graphics).
- Reproduce the exact visual layout and positioning
- Use appropriate SVG elements (rect, circle, path, text, g, etc.)
- Set viewBox to match the original dimensions/aspect ratio
- Use colors and fonts that match the original
- Position elements to match their exact locations in the original
- Represent text as <text> elements at correct positions{layout_instruction}{style_text}""",
        "latex": f"""Convert this image to LaTeX format.
- Use proper document structure
- Use \\section, \\subsection for headings
- Use tabular environment for tables
- Use itemize/enumerate for lists
- Use math mode for equations{layout_instruction}""",
        "csv": """Extract tabular data from this image as CSV.
- Use comma as separator
- Quote fields containing commas
- First row should be headers if visible
- One row per line""",
    }

    base_prompt = format_instructions.get(
        target_format, format_instructions["markdown"]
    )

    return f"""{base_prompt}

Output ONLY the {target_format.upper()} content, no explanations or code fences."""


def build_convert_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    target_format = config.get("target_format", "markdown")
    preserve_layout = config.get("preserve_layout", True)
    include_styles = config.get("include_styles", False)
    return _build_prompt(target_format, preserve_layout, include_styles)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="convert",
    display_name="Convert",
    description="Convert image to text format",
    category="vision",
    icon="doc.richtext",
    color="mint",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, CONVERT_CONFIG),
    default_prompt=_build_prompt("markdown", True, False),
    prompt_builder=build_convert_prompt,
    sort_order=20,
)
async def convert(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Convert images to structured text formats."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get convert-specific config
    target_format = inputs.get("target_format", "markdown")
    preserve_layout = inputs.get("preserve_layout", True)
    include_styles = inputs.get("include_styles", False)

    # Build prompt
    prompt = inputs.get("prompt") or _build_prompt(
        target_format, preserve_layout, include_styles
    )

    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        # Vision-specific
        vision_mode="llm",
        # #4329: a rendition is GENERATED from the page image by the model —
        # never satisfied by the pre-extracted text passthrough.
        force_ocr=True,
        # Sanitize/validate the markup before save (strip fences + scripts;
        # SVG must be well-formed XML) and stamp the format on the artifact so
        # the preview picks the right renderer.
        postprocess_text=lambda t: sanitize_converted_markup(t, target_format),
        artifact_data={"target_format": target_format},
        max_image_dimension=inputs.get(
            "max_image_dimension", 2048
        ),  # Full res for conversion
        # Inherited from BASE_CONFIG
        temperature=inputs.get("temperature", 0.2),  # Low temp for accuracy
        max_tokens=inputs.get("max_tokens", 4096),  # Conversions can be long
        output_format=inputs.get("output_format", "text"),  # Raw text output
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field"),
    )
