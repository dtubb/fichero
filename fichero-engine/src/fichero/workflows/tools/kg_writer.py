"""Explicit KG persistence workflow node."""

from __future__ import annotations

from typing import Any

from fichero.db import db_manager
from fichero.llm import LLMConfig
from fichero.workflows.registry import register_tool
from fichero.workflows.tools.extractors import _SECTIONS, _write_kg_rows
from fichero.workflows.types import DataType, PortDef, State


KG_WRITER_INPUT_PORTS = [
    PortDef(
        id="kg_payload",
        name="KG Payload",
        port_type="input",
        data_type=DataType.JSON,
        required=True,
        description="Write bundle emitted by extract_all",
    )
]


@register_tool(
    name="kg_writer",
    display_name="Write KG",
    description="Persist KG rows from an explicit upstream write bundle",
    category="llm",
    icon="square.and.arrow.down",
    color="brown",
    uses_llm=False,
    supports_batch=False,
    supports_structured_output=False,
    input_ports=KG_WRITER_INPUT_PORTS,
    output_ports=[],
    sort_order=36,
)
async def kg_writer(
    inputs: dict[str, Any],
    state: State,
    llm_config: LLMConfig,
) -> dict[str, Any]:
    payload = inputs.get("kg_payload") or []
    if not isinstance(payload, list) or not payload:
        return {
            "text": "",
            "value": [],
            "cached": False,
            "error": "No KG payload provided",
        }

    library_path = state.get("library_path", "")
    if not library_path:
        return {
            "text": "",
            "value": [],
            "cached": False,
            "error": "No library_path in workflow state",
        }

    db = db_manager.get_database(library_path)
    for record in payload:
        if not isinstance(record, dict):
            continue
        section_name = record.get("section_name")
        section = next(
            (s for s in _SECTIONS if s.get("name") == section_name),
            None,
        )
        if section is None:
            continue
        _write_kg_rows(
            db,
            section,
            record.get("items") or [],
            str(record.get("target_doc_id") or ""),
            page_label=record.get("page_label"),
            source_excerpt=record.get("source_excerpt"),
            provider=record.get("provider") or getattr(llm_config, "provider", None),
            model=record.get("model") or getattr(llm_config, "model", None),
            grounding_text=record.get("grounding_text"),
        )

    return {
        "text": "",
        "value": payload,
        "cached": False,
    }

