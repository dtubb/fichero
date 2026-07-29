"""Explicit KG persistence workflow node."""

from __future__ import annotations

from typing import Any

from fichero_server.db import db_manager
from fichero_server.llm import LLMConfig
from fichero_server.workflows.registry import register_tool
from fichero_server.workflows.tools.progress import emit_progress_event
from fichero_server.workflows.tools.extractors import _SECTIONS, _write_kg_rows
from fichero_server.workflows.types import DataType, PortDef, State


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
    progress_callback = inputs.get("__progress_callback")
    if not isinstance(payload, list) or not payload:
        # extract_all writes KG inline when persist_kg is ON; when persist_kg
        # is off (catalogue preset default) the downstream kg_writer node
        # receives the payload and persists it here. Empty payload means
        # no-op rather than failure (#1285).
        return {"text": "", "value": [], "cached": False}

    library_path = state.get("library_path", "")
    if not library_path:
        return {
            "text": "",
            "value": [],
            "cached": False,
            "error": "No library_path in workflow state",
        }

    db = db_manager.get_database(library_path)
    total = len(payload)
    for index, record in enumerate(payload, start=1):
        phase = f"KG writer record {index}/{total}"
        await emit_progress_event(
            progress_callback,
            "file_start",
            "",
            phase,
            index,
            total,
            message=f"KG writer processing record {index}/{total}",
        )
        if not isinstance(record, dict):
            await emit_progress_event(
                progress_callback,
                "file_complete",
                "",
                phase,
                index,
                total,
                message=f"KG writer skipped non-object record {index}/{total}",
            )
            continue
        section_name = record.get("section_name")
        section = next(
            (s for s in _SECTIONS if s.get("name") == section_name),
            None,
        )
        target_doc_id = str(record.get("target_doc_id") or "").strip()
        if not target_doc_id:
            await emit_progress_event(
                progress_callback,
                "file_complete",
                "",
                phase,
                index,
                total,
                message="KG writer skipped record with empty target_doc_id",
            )
            continue
        if section is None:
            await emit_progress_event(
                progress_callback,
                "file_complete",
                "",
                phase,
                index,
                total,
                message=f"KG writer skipped unknown section {section_name!r}",
            )
            continue
        _write_kg_rows(
            db,
            section,
            record.get("items") or [],
            target_doc_id,
            page_label=record.get("page_label"),
            source_excerpt=record.get("source_excerpt"),
            provider=record.get("provider") or getattr(llm_config, "provider", None),
            model=record.get("model") or getattr(llm_config, "model", None),
            grounding_text=record.get("grounding_text"),
        )
        await emit_progress_event(
            progress_callback,
            "file_complete",
            "",
            phase,
            index,
            total,
            message=(
                f"KG writer wrote record {index}/{total}: "
                f"{len(record.get('items') or [])} items"
            ),
        )

    return {
        "text": "",
        "value": payload,
        "cached": False,
    }
