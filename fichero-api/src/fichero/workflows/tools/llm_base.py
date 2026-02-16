"""
LLM Tools Base Module

Shared logic for all LLM-based tools (vision, text processing, entity extraction, etc.)
Each tool is a thin wrapper that provides:
- Default prompt
- Artifact type name
- Config options

This module provides:
- Base port and config schemas (inherited by all tools)
- Output format constraints and parsing
- Reference value matching
- Context injection
- Artifact saving
- Consistent error handling

Inheritance model:
- llm_base.py: BASE_CONFIG_SCHEMA, BASE_INPUT_PORTS, BASE_OUTPUT_PORTS
- vision_base.py: VISION_CONFIG_SCHEMA = BASE + vision-specific
- Individual tools: merge their specific config with parent
"""

from __future__ import annotations

import dataclasses
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from fichero.llm import LLMConfig

from fichero.workflows.types import PortDef, DataType

logger = logging.getLogger(__name__)


# =============================================================================
# Base Port Definitions (inherited by all tools)
# =============================================================================

BASE_INPUT_PORTS = [
    PortDef(
        id="context",
        name="Context",
        port_type="input",
        data_type=DataType.TEXT,
        required=False,
        description="Previous text/transcription",
    ),
    PortDef(
        id="metadata",
        name="Metadata",
        port_type="input",
        data_type=DataType.JSON,
        required=False,
        description="Existing metadata",
    ),
    PortDef(
        id="documents",
        name="Documents",
        port_type="input",
        data_type=DataType.JSON,
        required=False,
        description="Document metadata",
    ),
]

BASE_OUTPUT_PORTS = [
    PortDef(id="text", name="Text", port_type="output", data_type=DataType.TEXT, description="Raw text response"),
    PortDef(id="value", name="Value", port_type="output", data_type=DataType.ANY, description="Parsed value"),
    PortDef(id="texts", name="Texts", port_type="output", data_type=DataType.ARRAY, description="Per-item texts"),
    PortDef(id="values", name="Values", port_type="output", data_type=DataType.ARRAY, description="Per-item values"),
    PortDef(id="results", name="Results", port_type="output", data_type=DataType.JSON, description="Full results"),
    PortDef(id="artifacts", name="Artifacts", port_type="output", data_type=DataType.JSON, description="Artifact IDs"),
]


# =============================================================================
# Base Config Schema (inherited by all tools)
# =============================================================================

BASE_CONFIG_SCHEMA = {
    # Provider selection (overrides workflow default)
    "provider_name": {
        "type": "string",
        "enum": [
            "openai", "anthropic", "google", "ollama", "lmstudio",
            "groq", "together", "deepseek", "mistral", "openrouter",
            "dashscope", "xai", "perplexity", "fireworks",
        ],
        "description": "LLM provider",
        "x-group": "primary",
    },
    "model_name": {
        "type": "string",
        "description": "Model name",
        "x-group": "primary",
    },
    # LLM parameters
    "temperature": {
        "type": "number",
        "default": 0.7,
        "min": 0,
        "max": 2,
        "description": "Creativity",
        "x-group": "advanced",
    },
    "max_tokens": {
        "type": "integer",
        "default": 2048,
        "description": "Max response",
        "x-group": "advanced",
    },
    # Output format
    "output_format": {
        "type": "string",
        "enum": ["text", "boolean", "choice", "number", "words", "list", "json"],
        "default": "text",
        "description": "Response format",
        "x-group": "output",
    },
    "choices": {
        "type": "array",
        "items": {"type": "string"},
        "description": "Valid choices",
        "x-hidden": True,
    },
    "max_words": {
        "type": "integer",
        "default": 50,
        "description": "Word limit",
        "x-group": "output",
    },
    "max_items": {
        "type": "integer",
        "default": 10,
        "description": "List max items",
        "x-group": "output",
    },
    # Reference values
    "reference_values": {
        "type": "object",
        "description": "Known values to match",
        "additionalProperties": {"type": "array", "items": {"type": "string"}},
        "x-hidden": True,
    },
    "match_mode": {
        "type": "string",
        "enum": ["prefer", "strict", "inform"],
        "default": "prefer",
        "description": "Match mode",
        "x-group": "output",
    },
    # Storage
    "metadata_field": {
        "type": "string",
        "description": "Save to field",
        "x-group": "advanced",
    },
    "save_to_db": {
        "type": "boolean",
        "default": True,
        "description": "Save to library",
        "x-group": "advanced",
    },
    "save_to_file": {
        "type": "boolean",
        "default": False,
        "description": "Export to file",
        "x-group": "advanced",
    },
    # Custom prompt override
    "prompt": {
        "type": "string",
        "description": "Custom prompt",
        "x-group": "primary",
    },
}


# =============================================================================
# Schema Merge Helpers
# =============================================================================

def merge_config_schema(*schemas: dict) -> dict:
    """Merge multiple config schemas, later ones override earlier.

    Usage:
        TOOL_CONFIG = merge_config_schema(BASE_CONFIG_SCHEMA, VISION_CONFIG_SCHEMA, MY_TOOL_CONFIG)
    """
    result = {}
    for schema in schemas:
        result.update(schema)
    return result


def merge_ports(*port_lists: list[PortDef]) -> list[PortDef]:
    """Merge port lists, avoiding duplicates by id. Later ports override earlier.

    Usage:
        input_ports = merge_ports(BASE_INPUT_PORTS, [files_port])
    """
    seen: dict[str, PortDef] = {}
    for ports in port_lists:
        for p in ports:
            seen[p.id] = p
    return list(seen.values())


def extract_base_config(inputs: dict[str, Any]) -> dict[str, Any]:
    """Extract all BASE_CONFIG values from inputs dict.

    Useful for passing to process_text/process_vision.
    """
    return {
        "temperature": inputs.get("temperature"),
        "max_tokens": inputs.get("max_tokens"),
        "output_format": inputs.get("output_format", "text"),
        "output_options": {
            "choices": inputs.get("choices"),
            "max_words": inputs.get("max_words"),
            "max_items": inputs.get("max_items"),
        },
        "reference_values": inputs.get("reference_values"),
        "match_mode": inputs.get("match_mode", "prefer"),
        "context": inputs.get("context"),
        "input_metadata": inputs.get("metadata"),
        "save_to_db": inputs.get("save_to_db", True),
        "metadata_field": inputs.get("metadata_field"),
    }


# =============================================================================
# Tool Configuration
# =============================================================================

@dataclass
class LLMToolConfig:
    """Configuration for an LLM tool."""

    # What this tool produces
    artifact_type: str

    # Whether to update Document.page_content (makes it searchable)
    update_page_content: bool = False

    # Whether to trigger re-embedding after update
    trigger_embedding: bool = False

    # Default metadata field to update (None = don't update metadata)
    metadata_field: str | None = None


# =============================================================================
# Output Format Handling
# =============================================================================

def build_output_constraint(
    output_format: str,
    output_options: dict | None = None,
) -> str:
    """Build output format instructions for the prompt.

    Args:
        output_format: One of: text, boolean, choice, number, words, list, json
        output_options: Format-specific options:
            - choices: list of valid options (for "choice")
            - max_words: word limit (for "words")
            - max_items: list length (for "list")
            - schema: JSON schema description (for "json")

    Returns:
        Instruction string to append to prompt
    """
    options = output_options or {}

    if output_format == "boolean":
        return "\n\nRespond with exactly: yes or no"

    elif output_format == "choice":
        choices = options.get("choices", [])
        if choices:
            choices_str = ", ".join(f'"{c}"' for c in choices)
            return f"\n\nRespond with exactly one of: {choices_str}"
        return ""

    elif output_format == "number":
        return "\n\nRespond with a single number only."

    elif output_format == "words":
        max_words = options.get("max_words", 50)
        return f"\n\nLimit your response to {max_words} words or fewer."

    elif output_format == "list":
        max_items = options.get("max_items", 10)
        separator = options.get("separator", ",")
        return f"\n\nReturn a {separator}-separated list of up to {max_items} items."

    elif output_format == "json":
        schema = options.get("schema", "")
        if schema:
            return f"\n\nReturn valid JSON matching: {schema}"
        return "\n\nReturn valid JSON only."

    # Default: no constraint
    return ""


def parse_output(text: str, output_format: str, output_options: dict | None = None) -> Any:
    """Parse output according to format.

    Returns the appropriate Python type based on format.
    """
    text = text.strip()
    options = output_options or {}

    if output_format == "boolean":
        lower = text.lower()
        if lower in ("yes", "true", "1"):
            return True
        elif lower in ("no", "false", "0"):
            return False
        return text  # Return original if can't parse

    elif output_format == "number":
        try:
            # Remove common prefixes/suffixes
            cleaned = text.strip("$%").replace(",", "")
            if "." in cleaned:
                return float(cleaned)
            return int(cleaned)
        except ValueError:
            return text

    elif output_format == "list":
        separator = options.get("separator", ",")
        # Split by separator and clean up
        items = [item.strip() for item in text.split(separator)]
        return [item for item in items if item]

    elif output_format == "json":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            # Try array
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            return text

    # Default: return as-is
    return text


# =============================================================================
# Reference Value Matching
# =============================================================================

def build_reference_section(
    reference_values: dict[str, list] | None = None,
    match_mode: str = "prefer",
) -> str:
    """Build reference value instructions for the prompt.

    Args:
        reference_values: Dict of field names to lists of known values
            e.g., {"names": ["John Smith", "Jane Doe"], "categories": ["A", "B"]}
        match_mode: How to use reference values:
            - "prefer": Prefer these values but allow new ones
            - "strict": Only use these values
            - "inform": Just for context, don't constrain

    Returns:
        Instruction string to add to prompt
    """
    if not reference_values:
        return ""

    sections = []

    for field_name, values in reference_values.items():
        if not values:
            continue

        values_str = ", ".join(f'"{v}"' for v in values[:20])  # Limit to 20
        if len(values) > 20:
            values_str += f" (and {len(values) - 20} more)"

        if match_mode == "strict":
            sections.append(f"For {field_name}, only use these exact values: {values_str}")
        elif match_mode == "prefer":
            sections.append(f"For {field_name}, prefer these known values if they match: {values_str}")
        else:  # inform
            sections.append(f"Known {field_name} for reference: {values_str}")

    if not sections:
        return ""

    return "\n\nReference values:\n" + "\n".join(f"- {s}" for s in sections)


def match_to_reference(
    value: str,
    reference_values: list[str],
    fuzzy: bool = True,
) -> str | None:
    """Match a value to reference values.

    Args:
        value: The value to match
        reference_values: List of known values
        fuzzy: Whether to use fuzzy matching

    Returns:
        Matched reference value, or None if no match
    """
    if not reference_values:
        return None

    value_lower = value.lower().strip()

    # Exact match first
    for ref in reference_values:
        if ref.lower().strip() == value_lower:
            return ref

    if not fuzzy:
        return None

    # Fuzzy matching: check if value is contained in or contains a reference
    for ref in reference_values:
        ref_lower = ref.lower().strip()
        if value_lower in ref_lower or ref_lower in value_lower:
            return ref

    return None


def apply_reference_matching(
    result: Any,
    reference_values: dict[str, list] | None,
    fuzzy: bool = True,
) -> Any:
    """Apply reference value matching to a result.

    If result is a dict, tries to match string values against reference lists.
    If result is a list, tries to match each item.

    Args:
        result: The result to process
        reference_values: Dict of field names to reference lists
        fuzzy: Whether to use fuzzy matching

    Returns:
        Result with matched values where applicable
    """
    if not reference_values:
        return result

    if isinstance(result, dict):
        matched = {}
        for key, value in result.items():
            if key in reference_values and isinstance(value, str):
                match = match_to_reference(value, reference_values[key], fuzzy)
                matched[key] = match if match else value
            elif key in reference_values and isinstance(value, list):
                matched[key] = [
                    match_to_reference(v, reference_values[key], fuzzy) or v
                    for v in value
                    if isinstance(v, str)
                ]
            else:
                matched[key] = value
        return matched

    elif isinstance(result, list):
        # Try to match against any reference list
        all_refs = []
        for refs in reference_values.values():
            all_refs.extend(refs)

        return [
            match_to_reference(v, all_refs, fuzzy) or v
            for v in result
            if isinstance(v, str)
        ]

    elif isinstance(result, str):
        # Try to match against all reference values
        for refs in reference_values.values():
            match = match_to_reference(result, refs, fuzzy)
            if match:
                return match

    return result


# =============================================================================
# Context Building
# =============================================================================

def build_context_section(
    context: str | None = None,
    input_metadata: dict | None = None,
    previous_outputs: dict | None = None,
) -> str:
    """Build context section for prompt.

    Args:
        context: Previous text/transcription
        input_metadata: Existing metadata to include
        previous_outputs: Dict of previous tool outputs (e.g., {"transcribe": "...", "describe": "..."})

    Returns:
        Context section to prepend to prompt
    """
    parts = []

    if input_metadata:
        meta_str = json.dumps(input_metadata, indent=2)
        parts.append(f"Document metadata:\n{meta_str}")

    if previous_outputs:
        for tool_name, output in previous_outputs.items():
            if output:
                parts.append(f"Previous {tool_name} result:\n{output}")

    if context:
        parts.append(f"Document text:\n{context}")

    if not parts:
        return ""

    return f"""Context:
{chr(10).join(parts)}

---

"""


# =============================================================================
# Database Operations
# =============================================================================

async def save_artifact(
    document_id: str | None,
    file_path: str | None,
    content: str,
    data: dict | None,
    library_path: str,
    llm_config: LLMConfig,
    task_id: str | None,
    tool_config: LLMToolConfig,
    *,
    metadata_field: str | None = None,
    custom_metadata: dict | None = None,
) -> str | None:
    """Save LLM result to database.

    Creates an Artifact and optionally updates Document fields.

    Args:
        document_id: Document ID (if known)
        file_path: File path (if no document_id)
        content: Text content for artifact
        data: Structured data for artifact (optional)
        library_path: Path to library database
        llm_config: LLM config (for recording provider/model)
        task_id: Workflow task ID
        tool_config: Tool-specific configuration
        metadata_field: Override where to save in metadata
        custom_metadata: Additional key-value pairs to save

    Returns:
        Artifact ID if saved, None otherwise
    """
    try:
        from fichero.db import db_manager
        from fichero.models import Document, Artifact, Status

        if not library_path:
            return None

        db = db_manager.get_database(library_path)

        # Find document
        doc = None
        if document_id:
            doc = db.get(Document, document_id)
        if not doc and file_path:
            docs = db.query(Document, path=file_path)
            if docs:
                doc = docs[0]

        if not doc:
            logger.warning("Document not found for artifact save: id=%s path=%s", document_id, file_path)
            return None

        # Create Artifact
        artifact = Artifact(
            document_id=doc.id,
            artifact_type=tool_config.artifact_type,
            content=content,
            data=data,
            provider=llm_config.provider if hasattr(llm_config, 'provider') else None,
            model=llm_config.model if hasattr(llm_config, 'model') else None,
            run_id=task_id,
        )
        db.save(artifact)
        logger.info(f"Created {tool_config.artifact_type} artifact {artifact.id}")

        # Update Document.page_content if configured
        if tool_config.update_page_content:
            doc.page_content = content
            doc.status = Status.completed
            doc.updated_at = datetime.now()
            db.save(doc)

            if tool_config.trigger_embedding:
                db.embed(doc)
                logger.info(f"Updated page_content and embedding for {doc.id}")

        # Update metadata field (override or from tool_config)
        final_metadata_field = metadata_field or tool_config.metadata_field
        if final_metadata_field:
            # For text, truncate; for data, store as-is
            if data:
                doc.metadata[final_metadata_field] = data
            else:
                doc.metadata[final_metadata_field] = content[:1000]
            doc.updated_at = datetime.now()

        # Add custom metadata if provided
        if custom_metadata:
            for key, value in custom_metadata.items():
                doc.metadata[key] = value
            doc.updated_at = datetime.now()

        # Save if any metadata was updated
        if final_metadata_field or custom_metadata:
            db.save(doc)

        return artifact.id

    except Exception as e:
        logger.error(f"Failed to save artifact: {e}")
        return None


async def save_to_file(
    content: str,
    data: dict | None,
    library_path: str,
    document_id: str | None,
    file_path: str | None,
    tool_config: LLMToolConfig,
    output_format: str = "text",
) -> str | None:
    """Save LLM result to a file in the library package.

    Writes output to: {library_path}/storage/outputs/{id[:2]}/{id}_{type}.{ext}

    Args:
        content: Text content to save
        data: Structured data (saved as JSON if present)
        library_path: Path to library package
        document_id: Document ID for naming
        file_path: Source file path (fallback for naming)
        tool_config: Tool configuration (for artifact_type)
        output_format: Determines file extension

    Returns:
        Path to saved file, or None on failure
    """
    try:
        if not library_path:
            logger.warning("Cannot save to file: no library_path")
            return None

        # Determine document identifier for filename
        doc_id = document_id
        if not doc_id and file_path:
            # Use source filename as fallback
            doc_id = Path(file_path).stem

        if not doc_id:
            logger.warning("Cannot save to file: no document_id or file_path")
            return None

        # Determine extension
        if data or output_format == "json":
            ext = "json"
        elif output_format in ("list", "words"):
            ext = "txt"
        else:
            ext = "txt"

        # Build output path
        output_dir = Path(library_path) / "storage" / "outputs" / doc_id[:2]
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{doc_id}_{tool_config.artifact_type}.{ext}"

        # Write content
        if ext == "json" and data:
            output_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            output_file.write_text(content)

        logger.info(f"Saved {tool_config.artifact_type} to file: {output_file}")
        return str(output_file)

    except Exception as e:
        logger.error(f"Failed to save to file: {e}")
        return None


# =============================================================================
# Error Handling
# =============================================================================

@dataclass
class LLMResult:
    """Result from LLM processing with error handling."""

    text: str = ""
    value: Any = None
    error: str | None = None
    artifact_id: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None


def create_error_result(
    error: str | Exception,
    file_path: str | None = None,
) -> dict[str, Any]:
    """Create a standard error result dict.

    Args:
        error: Error message or exception
        file_path: Optional file path for context

    Returns:
        Error result dict
    """
    error_msg = str(error)

    result = {
        "text": "",
        "value": None,
        "error": error_msg,
    }

    if file_path:
        result["file"] = file_path

    logger.error(f"LLM processing error: {error_msg}")
    return result


def validate_inputs(
    required: dict[str, Any],
    optional: dict[str, tuple[Any, Any]] | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Validate and normalize inputs.

    Args:
        required: Dict of required input names to values
        optional: Dict of optional input names to (value, default) tuples

    Returns:
        Tuple of (validated inputs dict, error message or None)
    """
    validated = {}

    # Check required inputs
    for name, value in required.items():
        if value is None or value == "" or value == []:
            return {}, f"Missing required input: {name}"
        validated[name] = value

    # Apply defaults for optional inputs
    if optional:
        for name, (value, default) in optional.items():
            validated[name] = value if value is not None else default

    return validated, None


# =============================================================================
# Shared Text Processing
# =============================================================================

async def process_text(
    text: str,
    prompt: str,
    llm_config: LLMConfig,
    library_path: str,
    task_id: str | None,
    tool_config: LLMToolConfig,
    documents: list[dict] | None = None,
    *,
    # LLM parameters (from BASE_CONFIG_SCHEMA)
    temperature: float | None = None,
    max_tokens: int | None = None,
    # Output format (from BASE_CONFIG_SCHEMA)
    output_format: str = "text",
    output_options: dict | None = None,
    # Reference values (from BASE_CONFIG_SCHEMA)
    reference_values: dict[str, list] | None = None,
    match_mode: str = "prefer",
    # Context (from BASE_CONFIG_SCHEMA)
    context: str | None = None,
    input_metadata: dict | None = None,
    # Storage (from BASE_CONFIG_SCHEMA)
    save_to_db: bool = True,
    save_to_file_flag: bool = False,
    metadata_field: str | None = None,
    custom_metadata: dict | None = None,
) -> dict[str, Any]:
    """Shared text processing for all LLM text tools.

    This is the core function for summarize, entities, and other text-based tools.
    Mirrors process_vision() but for text-only inputs.

    Args:
        text: Input text to process
        prompt: The prompt template (will be enhanced with context/format constraints)
        llm_config: LLM configuration
        library_path: Path to library database
        task_id: Workflow task ID
        tool_config: Tool-specific configuration
        documents: Document metadata for saving artifacts
        temperature: Override LLM temperature
        max_tokens: Override LLM max tokens
        output_format: Expected output format
        output_options: Format-specific options (choices, max_words, etc.)
        reference_values: Known values to match against
        match_mode: How to use reference values
        context: Additional context text
        input_metadata: Existing metadata to include in prompt
        save_to_db: Whether to save results
        save_to_file_flag: Whether to export results to a file
        metadata_field: Override metadata field
        custom_metadata: Additional metadata to save

    Returns:
        Dict with text, value, results, artifacts, error, output_files
    """
    from fichero.llm import chat, LLMConfig

    if not text:
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "output_files": [],
            "error": "No text provided",
        }

    # Override LLMConfig with user values if provided
    effective_config = llm_config
    if temperature is not None or max_tokens is not None:
        effective_config = dataclasses.replace(
            llm_config,
            temperature=temperature if temperature is not None else llm_config.temperature,
            max_tokens=max_tokens if max_tokens is not None else llm_config.max_tokens,
        )

    # Build context section
    context_section = build_context_section(context, input_metadata)

    # Build reference section
    ref_section = build_reference_section(reference_values, match_mode)

    # Build output constraint
    output_constraint = build_output_constraint(output_format, output_options)

    # Combine prompt
    final_prompt = f"{context_section}{prompt}{ref_section}{output_constraint}"

    # Add the input text
    full_prompt = f"{final_prompt}\n\nText:\n{text}"

    try:
        # Call LLM
        response = await chat(
            [{"role": "user", "content": full_prompt}],
            config=effective_config,
        )

        # Parse output
        parsed = parse_output(response, output_format, output_options)

        # Apply reference matching
        if reference_values:
            parsed = apply_reference_matching(parsed, reference_values)

        result = {
            "text": response,
            "value": parsed,
        }

        # Save to database
        artifact_ids = []
        if save_to_db and library_path and documents:
            for doc in documents[:1]:  # Save to first document
                if isinstance(doc, dict) and doc.get("id"):
                    artifact_id = await save_artifact(
                        document_id=doc["id"],
                        file_path=doc.get("path"),
                        content=response,
                        data=parsed if isinstance(parsed, dict) else None,
                        library_path=library_path,
                        llm_config=effective_config,
                        task_id=task_id,
                        tool_config=tool_config,
                        metadata_field=metadata_field,
                        custom_metadata=custom_metadata,
                    )
                    if artifact_id:
                        artifact_ids.append(artifact_id)
                        result["artifact_id"] = artifact_id

        # Save to file
        output_files = []
        if save_to_file_flag and library_path:
            doc_id = None
            file_path_for_save = None
            if documents:
                first_doc = documents[0] if documents else None
                if isinstance(first_doc, dict):
                    doc_id = first_doc.get("id")
                    file_path_for_save = first_doc.get("path")

            output_path = await save_to_file(
                content=response,
                data=parsed if isinstance(parsed, dict) else None,
                library_path=library_path,
                document_id=doc_id,
                file_path=file_path_for_save,
                tool_config=tool_config,
                output_format=output_format,
            )
            if output_path:
                output_files.append(output_path)
                result["output_file"] = output_path

        return {
            "text": response,
            "value": parsed,
            "texts": [response],
            "values": [parsed],
            "results": [result],
            "artifacts": artifact_ids,
            "output_files": output_files,
        }

    except Exception as e:
        logger.error(f"Text processing failed: {e}")
        return {
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "output_files": [],
            "error": str(e),
        }
