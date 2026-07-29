"""
Diagram Tool

Parses diagrams, flowcharts, and organizational charts into structured data.
Inherits from vision_base.py - returns JSON representing the diagram structure.
"""

from __future__ import annotations

import logging
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

logger = logging.getLogger(__name__)


# =============================================================================
# Tool-Specific Configuration
# =============================================================================

TOOL_CONFIG = VisionToolConfig(
    artifact_type="diagram",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    metadata_field="diagram",
)

DIAGRAM_CONFIG = {
    "diagram_type": {
        "type": "string",
        "enum": [
            "flowchart",
            "org_chart",
            "network",
            "timeline",
            "mind_map",
            "generic",
        ],
        "default": "generic",
        "description": "Diagram type",
    },
    "include_labels": {
        "type": "boolean",
        "default": True,
        "description": "Extract text labels",
    },
}


# =============================================================================
# Prompt Building
# =============================================================================


def _build_prompt(diagram_type: str, include_labels: bool) -> str:
    """Build the diagram parsing prompt."""
    type_instructions = {
        "flowchart": """Parse this flowchart/process diagram.
Identify:
- Nodes (steps, decisions, start/end points)
- Connections (arrows, flow direction)
- Decision branches (yes/no, conditions)""",
        "org_chart": """Parse this organizational/hierarchy chart.
Identify:
- Nodes (people, roles, departments)
- Parent-child relationships
- Hierarchy levels""",
        "network": """Parse this network/relationship diagram.
Identify:
- Nodes (entities, servers, components)
- Connections (links, relationships)
- Connection types (bidirectional, one-way)""",
        "timeline": """Parse this timeline/sequence diagram.
Identify:
- Events (with dates/times if shown)
- Sequential order
- Duration/spans if indicated""",
        "mind_map": """Parse this mind map/concept diagram.
Identify:
- Central topic
- Branches and sub-branches
- Relationships between concepts""",
        "generic": """Parse this diagram.
Identify:
- All nodes/elements
- All connections/relationships between them
- Any labels or annotations""",
    }

    base = type_instructions.get(diagram_type, type_instructions["generic"])
    labels_text = (
        "\n- Extract all text labels exactly as written" if include_labels else ""
    )

    return f"""{base}{labels_text}

Return as JSON:
{{
    "diagram_type": "<detected type>",
    "nodes": [
        {{"id": "<n1>", "label": "<text>", "type": "<step/decision/start/end/entity/etc>"}}
    ],
    "connections": [
        {{"from": "<node_id>", "to": "<node_id>", "label": "<connection label if any>"}}
    ],
    "summary": "<brief description of what the diagram shows>"
}}

Return ONLY valid JSON."""


def build_diagram_prompt(config: dict) -> str:
    """Build prompt from config (exposed to UI)."""
    diagram_type = config.get("diagram_type", "generic")
    include_labels = config.get("include_labels", True)
    return _build_prompt(diagram_type, include_labels)


# =============================================================================
# Tool Registration
# =============================================================================


@register_tool(
    name="diagram",
    display_name="Diagram",
    description="Parse diagrams and flowcharts",
    category="vision",
    icon="chart.dots.scatter",
    color="cyan",
    uses_llm=True,
    supports_batch=True,
    supports_structured_output=True,
    input_ports=VISION_INPUT_PORTS,
    output_ports=BASE_OUTPUT_PORTS,
    config_schema=merge_config_schema(VISION_CONFIG_SCHEMA, DIAGRAM_CONFIG),
    default_prompt=_build_prompt("generic", True),
    prompt_builder=build_diagram_prompt,
    sort_order=25,
)
async def diagram(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Parse diagrams into structured data."""

    files = inputs.get("files") or state.get("input_files", [])
    documents = inputs.get("documents", [])
    context = inputs.get("context")
    input_metadata = inputs.get("metadata")

    diagram_type = inputs.get("diagram_type", "generic")
    include_labels = inputs.get("include_labels", True)

    prompt = inputs.get("prompt") or _build_prompt(diagram_type, include_labels)

    return await process_vision(
        files=files,
        documents=documents,
        prompt=prompt,
        llm_config=llm_config,
        library_path=state.get("library_path", ""),
        task_id=state.get("task_id"),
        tool_config=TOOL_CONFIG,
        vision_mode="llm",
        max_image_dimension=inputs.get("max_image_dimension", 2048),
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
        metadata_field=inputs.get("metadata_field"),
    )
