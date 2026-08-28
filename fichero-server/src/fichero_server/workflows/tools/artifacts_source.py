"""Artifacts Source — run a step on what a previous step WROTE.

Every workflow's source resolves to files, so a run always starts from the
image and each tool decides internally what to read. That makes one obvious
thing impossible: translating the *reviewed transcription* rather than the
page (Daniel, 2026-08-28: "we would do the translation on the transcription
review, but there's no easy way to see that"). No source node could express
it, so the bar could not offer it either.

This is that source. Point it at an artifact type and it emits those
artifacts' text as records, so any text tool downstream operates on the
artifact instead of the pixels.
"""

from __future__ import annotations

import logging
from typing import Any

from fichero_server.workflows.types import PortDef, DataType
from fichero_server.workflows.registry import register_tool

logger = logging.getLogger(__name__)


@register_tool(
    name="artifacts_source",
    display_name="Artifacts Source",
    description=(
        "Emit a document's existing artifacts as text — a transcription, a "
        "review, a translation — so a downstream tool runs on what an earlier "
        "step produced instead of on the page image. Pick the artifact type; "
        "the newest of that type wins unless you ask for all."
    ),
    category="source",
    icon="doc.text.magnifyingglass",
    color="purple",
    uses_llm=False,
    supports_batch=False,
    input_ports=[],
    output_ports=[
        PortDef(
            id="records",
            name="Records",
            port_type="output",
            data_type=DataType.ARRAY,
            description="One {doc_id, text} per artifact, in document order.",
        ),
        PortDef(
            id="text",
            name="Text",
            port_type="output",
            data_type=DataType.TEXT,
            description="All emitted artifact text, joined — for single-input tools.",
        ),
        PortDef(
            id="documents",
            name="Documents",
            port_type="output",
            data_type=DataType.JSON,
            description=(
                "The documents whose artifacts were emitted, so results link "
                "back to the right page."
            ),
        ),
        PortDef(
            id="count",
            name="Count",
            port_type="output",
            data_type=DataType.NUMBER,
            description="How many artifacts were emitted.",
        ),
    ],
    config_schema={
        "artifact_type": {
            "type": "string",
            "default": "transcription",
            "description": (
                "Which artifact to read — e.g. transcription, "
                "transcription_review, translation."
            ),
        },
        "which": {
            "type": "string",
            "enum": ["latest", "all"],
            "default": "latest",
            "description": (
                "latest: the newest artifact of that type per document — the "
                "usual intent, since a third review supersedes the first. "
                "all: every one, for comparison."
            ),
        },
        "step_name": {
            "type": "string",
            "default": "",
            "description": (
                "Optional: only artifacts written by this step. Names the "
                "PASS when several share a type — the final review rather "
                "than the first."
            ),
        },
    },
    sort_order=6,
)
async def artifacts_source_tool(
    inputs: dict[str, Any],
    state: dict[str, Any],
    llm_config: Any,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Emit the selected documents' artifacts of one type as text records."""
    from fichero_server.db import db_manager
    from fichero_server.models import Artifact, Document

    empty: dict[str, Any] = {"records": [], "text": "", "documents": [], "count": 0}

    library_path = state.get("library_path")
    if not library_path:
        logger.warning("artifacts_source: no library_path in state")
        return empty
    selected_doc_ids = state.get("selected_doc_ids") or []
    if not selected_doc_ids:
        logger.warning("artifacts_source: nothing selected")
        return empty

    config = config or {}
    artifact_type = str(config.get("artifact_type") or "transcription").strip()
    which = str(config.get("which") or "latest").strip()
    step_name = str(config.get("step_name") or "").strip()

    db = db_manager.get_database(library_path)
    records: list[dict[str, Any]] = []
    documents: list[dict[str, Any]] = []

    for doc_id in selected_doc_ids:
        document = db.get(Document, doc_id)
        if document is None:
            continue
        rows = db.query(Artifact, document_id=doc_id, artifact_type=artifact_type)
        if step_name:
            rows = [row for row in rows if (row.step_name or "") == step_name]
        if not rows:
            # Say which document had nothing rather than emitting a silent
            # gap: a chain that translated four of five pages must not look
            # complete.
            logger.info(
                "artifacts_source: %s has no %s artifact", doc_id, artifact_type
            )
            continue
        # Newest last so "latest" is the tail; created_at can be None on old
        # rows, which sort first rather than crashing the comparison.
        rows.sort(key=lambda row: (row.created_at is not None, row.created_at))
        chosen = rows[-1:] if which == "latest" else rows
        for row in chosen:
            text = (row.content or "").strip()
            if not text:
                continue
            records.append({"doc_id": doc_id, "text": text})
            documents.append(
                document.model_dump()
                if hasattr(document, "model_dump")
                else dict(document)
            )

    return {
        "records": records,
        "text": "\n\n".join(record["text"] for record in records),
        "documents": documents,
        "count": len(records),
    }
