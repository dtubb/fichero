"""
Extract Tool (Multi-Output Vision)

Single LLM call that extracts multiple fields at once.
Inherits from vision_base.py but has custom extraction logic.
More efficient than running separate tools for tags, description, classification, etc.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.workflows.tools._doc_lookup import register_path_mapping
from fichero.workflows.tools.llm_base import (
    BASE_OUTPUT_PORTS,
    merge_config_schema,
    merge_ports,
    build_context_section,
    save_file_artifact as save_artifact,
)
from fichero.workflows.tools.vision_base import (
    VISION_INPUT_PORTS,
    VISION_CONFIG_SCHEMA,
    VisionToolConfig,
    file_to_data_uri,
)
from fichero.llm import vision, LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VisionToolConfig(
    artifact_type="extraction",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
)

# Extract-specific config
EXTRACT_CONFIG = {
    "fields": {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Field name (e.g., doc_type, tags)",
                },
                "prompt": {"type": "string", "description": "What to extract"},
                "type": {
                    "type": "string",
                    "enum": ["string", "array", "boolean", "number"],
                },
            },
        },
        "description": "Fields to extract",
        "default": [
            {"name": "description", "prompt": "Brief description", "type": "string"},
            {"name": "tags", "prompt": "5-10 keyword tags", "type": "array"},
        ],
    },
}

# Custom output ports for extract (includes data port)
EXTRACT_OUTPUT_PORTS = merge_ports(
    [
        PortDef(
            id="data",
            name="Data",
            port_type="output",
            data_type=DataType.JSON,
            description="Parsed extraction",
        ),
    ],
    BASE_OUTPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================


def _build_extraction_prompt(
    fields: list[dict], context: str | None, input_metadata: dict | None
) -> str:
    """Build a prompt that extracts multiple fields in one call."""

    # Build context section
    context_section = build_context_section(context, input_metadata)

    # Build field instructions
    field_instructions = []
    output_schema = {}

    for field in fields:
        name = field.get("name", "value")
        prompt = field.get("prompt", f"Extract {name}")
        field_type = field.get("type", "string")

        field_instructions.append(f'- "{name}": {prompt}')

        # Build JSON schema for this field
        if field_type == "array":
            output_schema[name] = {"type": "array", "items": {"type": "string"}}
        elif field_type == "boolean":
            output_schema[name] = {"type": "boolean"}
        elif field_type == "number":
            output_schema[name] = {"type": "number"}
        else:
            output_schema[name] = {"type": "string"}

    fields_text = "\n".join(field_instructions)
    schema_text = json.dumps(output_schema, indent=2)

    return f"""{context_section}Analyze this image and extract the following information:

{fields_text}

Return your response as valid JSON matching this schema:
{schema_text}

Return ONLY the JSON object, no other text."""


def _parse_json_response(response: str, *, file_label: str | None = None) -> dict:
    """Parse JSON from LLM response."""
    try:
        # Try direct parse
        return json.loads(response)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from response
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(response[start:end])
    except json.JSONDecodeError:
        pass

    # Return empty dict if parsing fails
    logger.warning(
        "extract: could not parse JSON from model output for %s",
        file_label or "<unknown>",
    )
    return {}


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="extract",
    display_name="Extract",
    description="Extract multiple fields in one call",
    category="vision",
    icon="rectangle.and.text.magnifyingglass",
    color="purple",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=EXTRACT_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, EXTRACT_CONFIG),
    sort_order=16,
)
async def extract(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract multiple fields from images in one LLM call."""

    # Get inputs
    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get extract-specific config
    fields = inputs.get(
        "fields",
        [
            {"name": "description", "prompt": "Brief description", "type": "string"},
            {"name": "tags", "prompt": "5-10 keyword tags", "type": "array"},
        ],
    )
    save_to_db = inputs.get("save_to_db", True)
    max_image_dimension = inputs.get("max_image_dimension", 2048)
    temperature = inputs.get("temperature")
    max_tokens = inputs.get("max_tokens")

    if isinstance(files, str):
        files = [files]

    if not files:
        logger.warning("extract: no input files — all selected IDs may be stale/invalid")
        return {
            "text": "",
            "data": {},
            "value": None,
            "values": [],
            "results": [],
            "artifacts": [],
        }

    if not fields:
        return {
            "text": "",
            "data": {},
            "value": None,
            "values": [],
            "results": [],
            "artifacts": [],
            "error": "No fields configured",
        }

    # Override LLMConfig with user values if provided
    effective_config = llm_config
    if temperature is not None or max_tokens is not None:
        effective_config = dataclasses.replace(
            llm_config,
            temperature=temperature
            if temperature is not None
            else llm_config.temperature,
            max_tokens=max_tokens if max_tokens is not None else llm_config.max_tokens,
        )

    # Build path -> document_id mapping
    path_to_doc = {}
    if documents:
        for doc in documents:
            if isinstance(doc, dict) and doc.get("path"):
                register_path_mapping(path_to_doc, doc["path"], doc.get("id"))

    # Build prompt
    prompt = _build_extraction_prompt(fields, context, input_metadata)

    library_path = state.get("library_path", "")
    task_id = state.get("task_id")

    results = []
    all_data = []
    texts = []
    artifact_ids = []

    for file_path in files:
        try:
            # Convert image
            image_uri = file_to_data_uri(file_path, max_dimension=max_image_dimension)

            # Call vision LLM
            response = await vision(
                images=[image_uri],
                prompt=prompt,
                config=effective_config,
            )

            # Parse JSON response
            data = _parse_json_response(response, file_label=file_path)

            result = {
                "file": file_path,
                "text": response,
                "value": data,
            }

            # Save artifact and update metadata
            if save_to_db and library_path and data:
                artifact_id = await save_artifact(
                    file_path=file_path,
                    content=response,
                    document_id=path_to_doc.get(file_path),
                    library_path=library_path,
                    llm_config=effective_config,
                    task_id=task_id,
                    tool_config=TOOL_CONFIG,
                    custom_metadata=data,  # Save all extracted fields to metadata
                )
                if artifact_id:
                    result["artifact_id"] = artifact_id
                    artifact_ids.append(artifact_id)

            results.append(result)
            all_data.append(data)
            texts.append(response)

        except Exception as e:
            logger.error(f"Extraction failed for {file_path}: {e}")
            results.append(
                {"file": file_path, "text": "", "value": {}, "error": str(e)}
            )
            all_data.append({})
            texts.append("")

    # Combine data from all files
    combined_data = all_data[0] if len(all_data) == 1 else all_data

    return {
        "text": "\n\n".join(texts),
        "data": combined_data,
        "value": combined_data,
        "values": all_data,
        "texts": texts,
        "results": results,
        "artifacts": artifact_ids,
    }
