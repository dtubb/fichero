"""
Catalogue Tool

Generates structured library/archival catalogue entries.
Maps to the "library_catalogue_entry" step in Generic_Catalogue.jsonl.
Takes context from previous pipeline steps (entities, timeline, tags, summary).
Inherits from llm_base.py - returns JSON matching archival description standards.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero.workflows.types import State, PortDef, DataType
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.llm_base import (
    BASE_INPUT_PORTS,
    BASE_OUTPUT_PORTS,
    BASE_CONFIG_SCHEMA,
    merge_config_schema,
    merge_ports,
    LLMToolConfig,
    process_text,
)
from fichero.llm import LLMConfig

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = LLMToolConfig(
    artifact_type="catalogue",
    update_page_content=False,
    trigger_embedding=False,
    metadata_field="catalogue",
)

CATALOGUE_CONFIG = {
    "standard": {
        "type": "string",
        "enum": ["generic", "isad_g", "dublin_core", "marc"],
        "default": "generic",
        "description": "Catalogue standard",
    },
    "output_language": {
        "type": "string",
        "default": "English",
        "description": "Output language",
    },
}

CATALOGUE_INPUT_PORTS = merge_ports(
    [
        PortDef(
            id="text",
            name="Text",
            port_type="input",
            data_type=DataType.TEXT,
            required=True,
            description="Source text, transcription, or accumulated context",
        )
    ],
    BASE_INPUT_PORTS,
)


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(standard: str, output_language: str) -> str:
    """Build the catalogue entry prompt."""
    standard_instructions = {
        "generic": """Create a structured library catalogue entry with these fields:
- title: Brief descriptive title based on document content
- description: What the documents contain (150 words max)
- subject_keywords: Semicolon-separated keywords
- people: List of people mentioned
- places: List of locations mentioned
- organizations: List of organizations mentioned
- date_coverage: Date range (start/end in YYYY-MM-DD or YYYY)
- document_type: Type of documents (correspondence, legal, reports, etc.)""",
        "isad_g": """Create a catalogue entry following ISAD(G) archival description standard:
- reference_code: Leave blank (to be assigned)
- title: Formal archival title
- dates: Date range of materials
- level_of_description: item/file/series
- extent: Physical description
- creator: Who created the records
- scope_and_content: What the records contain
- conditions_of_access: Leave as "Open" unless stated otherwise
- language: Language(s) of materials""",
        "dublin_core": """Create a catalogue entry following Dublin Core metadata standard:
- dc_title: Resource title
- dc_creator: Creator/author
- dc_subject: Subject keywords
- dc_description: Description of content
- dc_date: Date or date range
- dc_type: Resource type (Text, Image, etc.)
- dc_format: Physical format
- dc_language: Language
- dc_coverage: Spatial/temporal coverage""",
        "marc": """Create a catalogue entry with MARC-like fields:
- title_245: Main title
- author_100: Main author/creator
- subjects_650: Subject headings (semicolon-separated)
- date_260: Publication/creation date
- description_520: Summary note
- physical_300: Physical description
- notes_500: General notes
- geographic_651: Geographic subjects""",
    }

    instructions = standard_instructions.get(standard, standard_instructions["generic"])

    return f"""Using all available information (transcription, entities, timeline, tags, summary, metadata, visual descriptions), create a structured catalogue entry.

{instructions}

Focus on documenting WHAT IS IN THE DOCUMENTS, not analysis or interpretation.
Write all output in {output_language}.

Return as JSON with the fields described above.
Return ONLY valid JSON."""


def build_catalogue_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    standard = config.get("standard", "generic")
    output_language = config.get("output_language", "English")
    return _build_prompt(standard, output_language)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="catalogue",
    display_name="Catalogue",
    description="Generate catalogue entry",
    category="llm",
    icon="books.vertical",
    color="brown",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=CATALOGUE_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(BASE_CONFIG_SCHEMA, CATALOGUE_CONFIG),
    default_prompt=_build_prompt("generic", "English"),
    prompt_builder=build_catalogue_prompt,
    sort_order=9,
)
async def catalogue(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Generate structured catalogue entry."""

    text = inputs.get("text", "")
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    standard = inputs.get("standard", "generic")
    output_language = inputs.get("output_language", "English")

    prompt = inputs.get("prompt") or _build_prompt(standard, output_language)

    return await process_text(
        text=text,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        documents=documents,
        temperature=inputs.get("temperature", 0.2),
        max_tokens=inputs.get("max_tokens", 4096),
        output_format=inputs.get("output_format", "json"),
        output_options={},
        reference_values=inputs.get("reference_values"),
        match_mode=inputs.get("match_mode", "prefer"),
        context=context,
        input_metadata=input_metadata,
        save_to_db=inputs.get("save_to_db", True),
        save_to_file_flag=inputs.get("save_to_file", False),
        metadata_field=inputs.get("metadata_field") or "catalogue",
    )
