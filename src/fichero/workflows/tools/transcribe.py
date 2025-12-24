"""
Transcribe Tool

Extracts text from images using vision LLM.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.llm import vision, LLMConfig

logger = logging.getLogger(__name__)


@register_tool(
    name="transcribe",
    display_name="Transcribe",
    description="Extract text from images using vision LLM",
    category="vision",
    icon="text.viewfinder",
    color="blue",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=[
        PortDef(id="files", name="Files", port_type="input", data_type=DataType.FILES, required=True, description="Image files to transcribe"),
    ],
    output_ports=[
        PortDef(id="text", name="Text", port_type="output", data_type=DataType.TEXT, description="Combined transcribed text"),
        PortDef(id="texts", name="Texts", port_type="output", data_type=DataType.ARRAY, description="Array of individual transcriptions"),
        PortDef(id="structured", name="Structured", port_type="output", data_type=DataType.JSON, description="Full results with file info"),
    ],
    config_schema={
        "language": {"type": "string", "default": "en", "description": "Language hint for transcription"},
        "return_boxes": {"type": "boolean", "default": False, "description": "Return bounding boxes for text regions"},
        "prompt": {"type": "string", "description": "Custom prompt (overrides default)"},
    },
    default_output_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Combined transcribed text"},
            "texts": {"type": "array", "items": {"type": "string"}, "description": "Individual texts per file"},
        }
    },
)
async def transcribe(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract text from images using vision LLM.

    Args:
        inputs: Resolved inputs from workflow
            - files: List of image file paths
            - language: Language hint (default: "en")
            - return_boxes: Whether to return bounding boxes
            - prompt: Custom prompt override
        state: Current workflow state (for context)
        llm_config: LLM configuration for vision call

    Returns:
        Dict with transcribed text and optional bounding boxes
    """
    # Get resolved inputs (already resolved by builder from $.paths)
    files = inputs.get("files") or state.get("input_files", [])
    language = inputs.get("language", "en")
    return_boxes = inputs.get("return_boxes", False)
    prompt_override = inputs.get("prompt")

    # Ensure files is a list
    if isinstance(files, str):
        files = [files]

    if not files:
        return {"text": "", "texts": [], "error": "No input files provided"}

    # Build prompt
    if prompt_override:
        prompt = prompt_override
    else:
        prompt = _build_transcription_prompt(language, return_boxes)

    # Process images
    results = []
    texts = []

    for file_path in files:
        try:
            # Convert file to base64 data URI
            image_uri = _file_to_data_uri(file_path)

            # Call vision LLM
            text = await vision(
                images=[image_uri],
                prompt=prompt,
                config=llm_config,
            )

            results.append({
                "file": file_path,
                "text": text,
            })
            texts.append(text)

        except Exception as e:
            logger.error(f"Failed to transcribe {file_path}: {e}")
            results.append({
                "file": file_path,
                "text": "",
                "error": str(e),
            })
            texts.append("")

    # Return structured output
    return {
        "text": "\n\n".join(texts),       # Combined text
        "texts": texts,                     # Individual texts (for [*] access)
        "results": results,                 # Full results with file info
        "boxes": None,                      # TODO: Parse boxes if return_boxes
    }


def _build_transcription_prompt(language: str, return_boxes: bool) -> str:
    """Build the transcription prompt."""
    prompt = f"""Extract and transcribe all text from this image.

Language: {language}

Instructions:
- Preserve the original text layout and structure
- Include all visible text, including headers, labels, and annotations
- If text is handwritten, transcribe as accurately as possible
- If text is unclear, indicate with [unclear]
- Maintain paragraph breaks and list formatting
"""

    if return_boxes:
        prompt += """
Additionally, provide bounding box coordinates for each text region in JSON format:
{
    "text": "transcribed text here",
    "boxes": [
        {"text": "...", "x": 0, "y": 0, "width": 100, "height": 20},
        ...
    ]
}
"""
    else:
        prompt += "\nOutput only the transcribed text."

    return prompt


def _file_to_data_uri(file_path: str) -> str:
    """Convert a file to a base64 data URI."""
    path = Path(file_path)

    # Determine MIME type
    suffix = path.suffix.lower()
    mime_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".tiff": "image/tiff",
        ".tif": "image/tiff",
        ".bmp": "image/bmp",
    }
    mime_type = mime_types.get(suffix, "image/jpeg")

    # Read and encode
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return f"data:{mime_type};base64,{data}"
