"""Workflow tool alias for programmatic book structure detection (#1279)."""

from __future__ import annotations

from typing import Any

from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.book_structure import book_structure
from fichero_server.workflows.types import DataType, PortDef, State


@register_tool(
    name="detect_structure",
    display_name="Detect Structure",
    description="Detect chapters, sections, and subsections for a book PDF",
    category="source",
    icon="list.bullet.indent",
    color="gray",
    uses_llm=False,
    supports_batch=False,
    input_ports=[
        PortDef(
            id="documents",
            name="Documents",
            port_type="input",
            data_type=DataType.JSON,
            required=False,
            description="Document metadata from the source selector",
        ),
    ],
    output_ports=[
        PortDef(
            id="structure",
            name="Structure",
            port_type="output",
            data_type=DataType.JSON,
            description="Nested chapter/section/subsection structure",
        ),
    ],
    sort_order=4,
)
async def detect_structure(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    """Detect and persist a source PDF's Document.structure tree."""
    return await book_structure(inputs, state, llm_config)
