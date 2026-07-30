"""Helpers for workflow tools that should feed the image preview editor."""

from __future__ import annotations

from fichero_server.core.timeutil import utc_now
from typing import Any, Callable

from fichero_server.db import db_manager
from fichero_server.models import Document, ImageEditChain
from fichero_server.workflows.types import State


def _candidate_document_ids(inputs: dict[str, Any], state: State) -> list[str]:
    ids: list[str] = []
    for source in (inputs.get("documents"), state.get("documents")):
        for doc in source or []:
            if isinstance(doc, dict) and isinstance(doc.get("id"), str):
                ids.append(doc["id"])
    for doc_id in state.get("selected_doc_ids") or []:
        if isinstance(doc_id, str):
            ids.append(doc_id)

    seen: set[str] = set()
    unique: list[str] = []
    for doc_id in ids:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        unique.append(doc_id)
    return unique


def append_image_edit_operations(
    inputs: dict[str, Any],
    state: State,
    build_operation: Callable[[Document], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Persist edit-chain operations for workflow-selected documents.

    Workflow image tools still return derived files for pipeline chaining, but
    the preview editor only reflects operations stored in ImageEditChain rows.
    This helper bridges selected-document workflow runs into that editor state.
    """
    library_path = state.get("library_path") or inputs.get("library_path")
    if not library_path:
        return []

    db = db_manager.get_database(library_path)
    records: list[dict[str, Any]] = []
    for doc_id in _candidate_document_ids(inputs, state):
        doc = db.get(Document, doc_id)
        if doc is None:
            continue
        operation = build_operation(doc)
        operation.setdefault("created_at", utc_now().isoformat())

        rows = list(db.query(ImageEditChain, document_id=doc.id))
        if rows:
            chain = rows[0]
            chain.operations.append(operation)
            chain.updated_at = utc_now()
        else:
            chain = ImageEditChain(document_id=doc.id, operations=[operation])
        db.save(chain)
        records.append({"document_id": doc.id, "operation": operation})
    return records
