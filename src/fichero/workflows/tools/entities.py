"""
Entity Extraction Tool

Extract named entities (people, places, dates, organizations) from text.
Saves results to Artifact and updates Document metadata.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.llm import chat, LLMConfig

logger = logging.getLogger(__name__)


@register_tool(
    name="extract_entities",
    display_name="Extract Entities",
    description="Extract named entities (people, places, dates, organizations) from text",
    category="llm",
    icon="person.text.rectangle",
    color="purple",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=[
        PortDef(id="text", name="Text", port_type="input", data_type=DataType.TEXT, required=True, description="Text to extract entities from"),
        PortDef(id="documents", name="Documents", port_type="input", data_type=DataType.JSON, required=False, description="Document metadata for saving"),
    ],
    output_ports=[
        PortDef(id="entities", name="Entities", port_type="output", data_type=DataType.JSON, description="Extracted entities by category"),
        PortDef(id="artifacts", name="Artifacts", port_type="output", data_type=DataType.JSON, description="Created artifact IDs"),
    ],
    config_schema={
        "entity_types": {
            "type": "array",
            "items": {"type": "string"},
            "default": ["people", "organizations", "locations", "dates"],
            "description": "Types of entities to extract",
        },
        "include_context": {"type": "boolean", "default": False, "description": "Include surrounding context for each entity"},
        "deduplicate": {"type": "boolean", "default": True, "description": "Remove duplicate entities"},
        "save_to_db": {"type": "boolean", "default": True, "description": "Save entities to database"},
    },
    default_output_schema={
        "type": "object",
        "properties": {
            "people": {"type": "array", "items": {"type": "string"}},
            "organizations": {"type": "array", "items": {"type": "string"}},
            "locations": {"type": "array", "items": {"type": "string"}},
            "dates": {"type": "array", "items": {"type": "string"}},
        }
    },
    sort_order=32,
)
async def extract_entities(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Extract named entities from text.

    Args:
        inputs: Resolved inputs from workflow
        state: Current workflow state
        llm_config: LLM configuration

    Returns:
        Dict with extracted entities by category
    """
    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    entity_types = inputs.get("entity_types", ["people", "organizations", "locations", "dates"])
    include_context = inputs.get("include_context", False)
    deduplicate = inputs.get("deduplicate", True)
    save_to_db = inputs.get("save_to_db", True)

    library_path = state.get("library_path", "")

    if not text:
        return {"entities": {}, "artifacts": [], "error": "No text provided"}

    prompt = _build_extraction_prompt(text, entity_types, include_context)

    try:
        response = await chat(
            messages=[{"role": "user", "content": prompt}],
            config=llm_config,
        )

        # Parse JSON response
        entities = _parse_entities_response(response, entity_types)

        # Deduplicate if requested
        if deduplicate:
            for entity_type in entities:
                if isinstance(entities[entity_type], list):
                    entities[entity_type] = list(set(entities[entity_type]))

        artifact_ids = []

        # Save to database
        if save_to_db and library_path and documents:
            for doc in documents[:1]:
                if isinstance(doc, dict) and doc.get("id"):
                    artifact_id = await _save_entities(
                        document_id=doc["id"],
                        entities=entities,
                        library_path=library_path,
                        llm_config=llm_config,
                        task_id=state.get("task_id"),
                    )
                    if artifact_id:
                        artifact_ids.append(artifact_id)

        return {
            "entities": entities,
            "artifacts": artifact_ids,
        }

    except Exception as e:
        logger.error(f"Failed to extract entities: {e}")
        return {"entities": {}, "artifacts": [], "error": str(e)}


async def _save_entities(
    document_id: str,
    entities: dict[str, Any],
    library_path: str,
    llm_config: LLMConfig,
    task_id: str | None,
) -> str | None:
    """Save entities to database as Artifact."""
    try:
        from fichero.db import db_manager
        from fichero.models import Document, Artifact

        db = db_manager.get_database(library_path)

        doc = db.get(Document, document_id)
        if not doc:
            logger.warning(f"Document not found: {document_id}")
            return None

        artifact = Artifact(
            document_id=doc.id,
            artifact_type="entities",
            data=entities,
            provider=llm_config.provider,
            model=llm_config.model,
            run_id=task_id,
        )
        db.save(artifact)
        logger.info(f"Created entities artifact {artifact.id} for document {doc.id}")

        # Update document metadata with entities
        doc.metadata["entities"] = entities
        doc.updated_at = datetime.now()
        db.save(doc)

        return artifact.id

    except Exception as e:
        logger.error(f"Failed to save entities: {e}")
        return None


def _build_extraction_prompt(text: str, entity_types: list[str], include_context: bool) -> str:
    """Build the entity extraction prompt."""
    type_descriptions = {
        "people": "names of individuals, including full names and nicknames",
        "organizations": "companies, institutions, agencies, groups",
        "locations": "places, addresses, cities, countries, geographic features",
        "dates": "dates, time periods, years, centuries",
        "events": "named events, meetings, conferences",
        "products": "product names, brands, models",
        "monetary": "monetary amounts, currencies",
    }

    types_text = "\n".join([
        f"- {t}: {type_descriptions.get(t, t)}"
        for t in entity_types
    ])

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

Text:
{text}

Return only valid JSON, no other text.
"""


def _parse_entities_response(response: str, entity_types: list[str]) -> dict[str, list]:
    """Parse the LLM response into structured entities."""
    # Try to extract JSON from response
    try:
        # Look for JSON in the response
        start = response.find("{")
        end = response.rfind("}") + 1
        if start >= 0 and end > start:
            json_str = response[start:end]
            entities = json.loads(json_str)

            # Ensure all requested types exist
            for entity_type in entity_types:
                if entity_type not in entities:
                    entities[entity_type] = []

            return entities
    except json.JSONDecodeError:
        pass

    # Fallback: return empty structure
    return {t: [] for t in entity_types}
