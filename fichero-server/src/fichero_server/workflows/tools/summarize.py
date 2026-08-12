"""
Summarize Tools

Generate summaries at different levels:
- summarize_file: Summarize a single document
- summarize_folder: Summarize all documents in a folder
- summarize_collection: Summarize an entire collection

All inherit from llm_base.py for shared config and processing.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import State, PortDef, DataType
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.llm_base import (
    BASE_INPUT_PORTS,
    BASE_OUTPUT_PORTS,
    BASE_CONFIG_SCHEMA,
    merge_config_schema,
    merge_ports,
    LLMToolConfig,
    process_text,
)
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = LLMToolConfig(
    artifact_type="summary",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="summary",
)

# Summarize-specific config (added to BASE_CONFIG_SCHEMA)
SUMMARIZE_CONFIG = {
    "style": {
        "type": "string",
        "enum": ["brief", "detailed", "bullets"],
        "default": "brief",
        "description": "Style",
    },
    "max_length": {
        "type": "integer",
        "default": 200,
        "description": "Max words",
    },
}

# Input ports for summarize_file
SUMMARIZE_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Text to summarize",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================


def _get_style_instructions(style: str, max_length: int) -> str:
    """Get style-specific instructions."""
    instructions = {
        "brief": f"Provide a brief summary in 1-2 sentences (max {max_length} words).",
        "detailed": f"Provide a detailed summary covering main points (max {max_length} words).",
        "bullets": f"Provide a bullet-point summary with key takeaways (max {max_length} words).",
    }
    return instructions.get(style, instructions["brief"])


def _build_summary_prompt(style: str, max_length: int) -> str:
    """Build the summary prompt."""
    return f"""Summarize the following text.

{_get_style_instructions(style, max_length)}"""


def build_summarize_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    style = config.get("style", "brief")
    max_length = config.get("max_length", 200)
    return _build_summary_prompt(style, max_length)


# =============================================================================
# Summarize File (single document)
# =============================================================================


@register_tool(
    name="summarize_file",
    parallelism="elementwise",
    display_name="Summarize File",
    description="Generate a summary of a single document's content",
    category="llm",
    icon="doc.text",
    color="purple",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=SUMMARIZE_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, SUMMARIZE_CONFIG),
    default_prompt=_build_summary_prompt("brief", 200),
    prompt_builder=build_summarize_prompt,
    sort_order=30,
)
async def summarize_file(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Summarize a single document."""

    # Get inputs
    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get summarize-specific config
    style = inputs.get("style", "brief")
    max_length = inputs.get("max_length", 200)

    # Build prompt
    prompt = inputs.get("prompt") or _build_summary_prompt(style, max_length)

    # Override tool config for file-specific summary type
    tool_config = LLMToolConfig(
        artifact_type="summary_file",
        update_page_content=False,
        trigger_embedding=False,
        metadata_field="summary",
    )

    # Process with shared logic
    result = await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=tool_config,
        documents=documents,
        # Inherited from BASE_CONFIG
        temperature=inputs.get("temperature"),
        max_tokens=inputs.get("max_tokens"),
        output_format=inputs.get("output_format", "text"),
        output_options={
            "choices": inputs.get("choices"),
            "max_words": inputs.get("max_words") or max_length,
            "max_items": inputs.get("max_items"),
        },
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "summary",
        chunk_size_chars=inputs.get("chunk_size_chars"),
    )

    # Map to expected output format
    return {
        "summary": result.get("text", ""),
        "text": result.get("text", ""),
        "value": result.get("value"),
        "texts": result.get("texts", []),
        "values": result.get("values", []),
        "results": result.get("results", []),
        "artifacts": result.get("artifacts", []),
        "error": result.get("error"),
    }


# =============================================================================
# Summarize Folder
# =============================================================================

# Folder-specific config
FOLDER_CONFIG = {
    "style": {
        "type": "string",
        "enum": ["brief", "detailed", "bullets"],
        "default": "detailed",
        "description": "Style",
    },
    "max_length": {
        "type": "integer",
        "default": 500,
        "description": "Max words",
    },
    "include_themes": {
        "type": "boolean",
        "default": True,
        "description": "Include themes",
    },
}

FOLDER_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="texts",
            name="Texts",
            port_type="input",
            data_type=DataType.ARRAY,
            required=True,
            description="Array of text contents",
        ),
        PortDef(
            id="folder_id",
            name="Folder ID",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Folder document ID",
        ),
    ],
    BASE_INPUT_PORTS,
)


@register_tool(
    name="summarize_folder",
    display_name="Summarize Folder",
    description="Generate a summary of all documents in a folder",
    category="llm",
    icon="folder",
    color="purple",
    uses_llm=True,
    supports_structured_output=True,
    input_ports=FOLDER_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, FOLDER_CONFIG),
    sort_order=31,
)
async def summarize_folder(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Summarize all documents in a folder."""

    texts = inputs.get("texts", [])
    folder_id = inputs.get("folder_id", "")
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")
    style = inputs.get("style", "detailed")
    max_length = inputs.get("max_length", 500)
    include_themes = inputs.get("include_themes", True)

    if not texts:
        return {
            "summary": "",
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "error": "No texts provided",
        }

    # Combine texts with separators
    combined = "\n\n---\n\n".join([t for t in texts if t])

    prompt = f"""Summarize the following collection of {len(texts)} documents.

{_get_style_instructions(style, max_length)}

{"Identify common themes, patterns, or connections between documents." if include_themes else ""}"""

    # Create documents list for folder
    documents = [{"id": folder_id}] if folder_id else []

    # Override tool config for folder-specific summary type
    tool_config = LLMToolConfig(
        artifact_type="summary_folder",
        update_page_content=False,
        trigger_embedding=False,
        metadata_field="summary",
    )

    # Process with shared logic
    result = await process_text(
        text=combined,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=tool_config,
        documents=documents,
        temperature=inputs.get("temperature"),
        max_tokens=inputs.get("max_tokens"),
        output_format=inputs.get("output_format", "text"),
        output_options={
            "choices": inputs.get("choices"),
            "max_words": inputs.get("max_words") or max_length,
            "max_items": inputs.get("max_items"),
        },
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "summary",
        chunk_size_chars=inputs.get("chunk_size_chars"),
    )

    return {
        "summary": result.get("text", ""),
        "text": result.get("text", ""),
        "value": result.get("value"),
        "texts": result.get("texts", []),
        "values": result.get("values", []),
        "results": result.get("results", []),
        "artifacts": result.get("artifacts", []),
        "document_count": len(texts),
        "error": result.get("error"),
    }


# =============================================================================
# Summarize Collection
# =============================================================================

# Collection-specific config
COLLECTION_CONFIG = {
    "style": {
        "type": "string",
        "enum": ["executive", "detailed", "narrative"],
        "default": "executive",
        "description": "Style",
    },
    "max_length": {
        "type": "integer",
        "default": 1000,
        "description": "Max words",
    },
    "include_statistics": {
        "type": "boolean",
        "default": True,
        "description": "Include stats",
    },
}

COLLECTION_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="folder_summaries",
            name="Folder Summaries",
            port_type="input",
            data_type=DataType.ARRAY,
            required=False,
            description="Summaries from folders",
        ),
        PortDef(
            id="texts",
            name="Texts",
            port_type="input",
            data_type=DataType.ARRAY,
            required=False,
            description="Or raw texts",
        ),
        PortDef(
            id="collection_id",
            name="Collection ID",
            port_type="input",
            data_type=DataType.TEXT,
            required=False,
            description="Collection document ID",
        ),
    ],
    BASE_INPUT_PORTS,
)


@register_tool(
    name="summarize_collection",
    display_name="Summarize Collection",
    description="Generate a high-level summary of an entire collection",
    category="llm",
    icon="archivebox",
    color="purple",
    uses_llm=True,
    supports_structured_output=True,
    input_ports=COLLECTION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, COLLECTION_CONFIG),
    sort_order=32,
)
async def summarize_collection(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Summarize an entire collection."""

    folder_summaries = inputs.get("folder_summaries", [])
    texts = inputs.get("texts", [])
    collection_id = inputs.get("collection_id", "")
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")
    style = inputs.get("style", "executive")
    max_length = inputs.get("max_length", 1000)
    include_statistics = inputs.get("include_statistics", True)

    # Use folder summaries if available, otherwise raw texts
    content_items = folder_summaries if folder_summaries else texts

    if not content_items:
        return {
            "summary": "",
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "error": "No content provided",
        }

    combined = "\n\n---\n\n".join([str(t) for t in content_items if t])

    style_instructions = {
        "executive": "Provide an executive summary suitable for quick review. Focus on key findings and overall themes.",
        "detailed": "Provide a comprehensive summary covering all major topics and their relationships.",
        "narrative": "Provide a narrative summary that tells the story of this collection.",
    }

    prompt = f"""Summarize this collection of documents.

{style_instructions.get(style, style_instructions["executive"])}

Maximum length: {max_length} words.

{"Include statistics about the collection (e.g., number of documents, date ranges, main topics)." if include_statistics else ""}"""

    # Create documents list for collection
    documents = [{"id": collection_id}] if collection_id else []

    # Override tool config for collection-specific summary type
    tool_config = LLMToolConfig(
        artifact_type="summary_collection",
        update_page_content=False,
        trigger_embedding=False,
        metadata_field="summary",
    )

    # Process with shared logic
    result = await process_text(
        text=combined,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=tool_config,
        documents=documents,
        temperature=inputs.get("temperature"),
        max_tokens=inputs.get("max_tokens"),
        output_format=inputs.get("output_format", "text"),
        output_options={
            "choices": inputs.get("choices"),
            "max_words": inputs.get("max_words") or max_length,
            "max_items": inputs.get("max_items"),
        },
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "summary",
        chunk_size_chars=inputs.get("chunk_size_chars"),
    )

    return {
        "summary": result.get("text", ""),
        "text": result.get("text", ""),
        "value": result.get("value"),
        "texts": result.get("texts", []),
        "values": result.get("values", []),
        "results": result.get("results", []),
        "artifacts": result.get("artifacts", []),
        "source_count": len(content_items),
        "error": result.get("error"),
    }
