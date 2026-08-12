"""
Entity Extraction Tool

Extract named entities (people, places, dates, organizations) from text.
Inherits from llm_base.py for shared config and processing.
"""

from __future__ import annotations

import logging
import unicodedata
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
    parse_output,
)
from fichero_server.llm import LLMConfig

logger = logging.getLogger(__name__)


def _normalize_entity_name(value: Any) -> str:
    """Normalize entity labels for stable deduplication."""
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(folded.casefold().split())


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = LLMToolConfig(
    artifact_type="entities",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="entities",
)

# Entities-specific config (added to BASE_CONFIG_SCHEMA)
ENTITIES_CONFIG = {
    "entity_types": {
        "type": "array",
        "items": {"type": "string"},
        "default": ["people", "organizations", "locations", "dates"],
        "description": "Entity types",
    },
    "include_context": {
        "type": "boolean",
        "default": False,
        "description": "Show context",
    },
    "deduplicate": {
        "type": "boolean",
        "default": True,
        "description": "Remove duplicates",
    },
}

# Input ports for entities
ENTITIES_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Text to extract entities from",
        )
    ],
    BASE_INPUT_PORTS,
)

# Output ports include entities-specific output
ENTITIES_OUTPUT_PORTS = merge_ports(
    [
        PortDef(
            id="entities",
            name="Entities",
            port_type="output",
            data_type=DataType.JSON,
            description="Extracted entities by category",
        )
    ],
    BASE_OUTPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================

TYPE_DESCRIPTIONS = {
    "people": "names of individuals, including full names and nicknames",
    "organizations": "companies, institutions, agencies, groups",
    "locations": "places, addresses, cities, countries, geographic features",
    "dates": "dates, time periods, years, centuries",
    "events": "named events, meetings, conferences",
    "products": "product names, brands, models",
    "monetary": "monetary amounts, currencies",
}


def _build_extraction_prompt(entity_types: list[str], include_context: bool) -> str:
    """Build the entity extraction prompt."""
    types_text = "\n".join(
        [f"- {t}: {TYPE_DESCRIPTIONS.get(t, t)}" for t in entity_types]
    )

    context_instruction = ""
    if include_context:
        context_instruction = """
For each entity, include a brief context snippet showing where it appears.
Format: {"entity": "name", "context": "...surrounding text..."}
"""

    return f"""Extract named entities from the following text.

Entity types to extract:
{types_text}

{context_instruction}

Return the results as valid JSON with entity types as keys and arrays of entities as values.
Example format:
{{
    "people": ["John Smith", "Jane Doe"],
    "organizations": ["Acme Corp"],
    "locations": ["New York", "Paris"],
    "dates": ["January 1920", "1945"]
}}

Return only valid JSON, no other text."""


def build_entities_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    entity_types = config.get(
        "entity_types", ["people", "organizations", "locations", "dates"]
    )
    include_context = config.get("include_context", False)
    return _build_extraction_prompt(entity_types, include_context)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="extract_entities",
    parallelism="elementwise",
    display_name="Extract Entities",
    description="Extract named entities (people, places, dates, organizations) from text",
    category="llm",
    icon="person.text.rectangle",
    color="purple",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=ENTITIES_INPUT_PORTS,
    output_ports=ENTITIES_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, ENTITIES_CONFIG),
    default_prompt=_build_extraction_prompt(
        ["people", "organizations", "locations", "dates"], False
    ),
    prompt_builder=build_entities_prompt,
    sort_order=33,
)
async def extract_entities(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract named entities from text."""

    # Get inputs
    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    # Get entities-specific config
    entity_types = inputs.get(
        "entity_types", ["people", "organizations", "locations", "dates"]
    )
    include_context = inputs.get("include_context", False)
    deduplicate = inputs.get("deduplicate", True)

    if not text:
        return {
            "entities": {},
            "text": "",
            "value": None,
            "texts": [],
            "values": [],
            "results": [],
            "artifacts": [],
            "error": "No text provided",
        }

    # Build prompt
    prompt = inputs.get("prompt") or _build_extraction_prompt(
        entity_types, include_context
    )

    # Process with shared logic - use json output format
    result = await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        # Inherited from BASE_CONFIG
        temperature=inputs.get("temperature"),
        max_tokens=inputs.get("max_tokens"),
        output_format="json",  # Always JSON for entities
        output_options={
            "choices": inputs.get("choices"),
            "max_words": inputs.get("max_words"),
            "max_items": inputs.get("max_items"),
        },
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "entities",
    )

    # Get parsed entities
    entities = result.get("value", {})

    # If value is a string (parsing failed), try to parse it
    if isinstance(entities, str):
        entities = parse_output(entities, "json") or {}

    # Ensure it's a dict
    if not isinstance(entities, dict):
        entities = {}

    max_items = inputs.get("max_items")
    try:
        max_items = int(max_items) if max_items is not None else None
    except (TypeError, ValueError):
        max_items = None
    if max_items is not None and max_items <= 0:
        max_items = None

    # Ensure all requested types exist
    for entity_type in entity_types:
        if entity_type not in entities:
            entities[entity_type] = []

    # Deduplicate if requested
    if deduplicate:
        for entity_type in entities:
            if isinstance(entities[entity_type], list):
                # Preserve order while deduplicating
                seen = set()
                unique = []
                for item in entities[entity_type]:
                    if isinstance(item, dict):
                        item_key = (
                            item.get("name")
                            or item.get("entity")
                            or item.get("canonical_name")
                            or item.get("value")
                            or str(item)
                        )
                    else:
                        item_key = item
                    item_key = _normalize_entity_name(item_key)
                    if item_key not in seen:
                        seen.add(item_key)
                        unique.append(item)
                entities[entity_type] = unique

    if max_items is not None:
        for entity_type in list(entities):
            items = entities.get(entity_type)
            if isinstance(items, list) and len(items) > max_items:
                logger.warning(
                    "extract_entities: truncated %s from %d to %d items",
                    entity_type,
                    len(items),
                    max_items,
                )
                entities[entity_type] = items[:max_items]

    return {
        "entities": entities,
        "text": result.get("text", ""),
        "value": entities,
        "texts": result.get("texts", []),
        "values": [entities],
        "results": result.get("results", []),
        "artifacts": result.get("artifacts", []),
        "error": result.get("error"),
    }
