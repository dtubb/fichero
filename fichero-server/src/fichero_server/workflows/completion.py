"""Persist per-document completion at the workflow boundary (#1282).

Content-producing tool nodes (transcription, LLM content) mark the documents
they touch as ``Status.processing`` while a workflow runs, NOT ``completed`` —
a page isn't "done" just because transcription finished while later pipeline
steps (NER / Extract All Entities / KG) are still queued. The workflow / batch
boundary owns the terminal flip to ``completed``: once the whole run (or batch
item) finishes, every document that run actually processed — and its page
children — is marked completed, and only then does the UI show the green check.

Scoping to the run's OWN documents (rather than a global "all processing"
sweep) keeps parallel batch items from completing each other's still-in-progress
pages. The source / files node already resolves each input — and expands PDF
parents / folders into their page children — into
``outputs[node_id]["documents"]`` as ``model_dump()`` dicts, so the run's
document set is recoverable from the final state alone.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _normalize_workflow_run(workflow_run: Any) -> dict[str, Any] | None:
    """Return a JSON-safe provenance entry for a workflow run."""
    if not isinstance(workflow_run, dict):
        return None

    entry: dict[str, Any] = {}
    for key in (
        "thread_id",
        "batch_id",
        "item_index",
        "workflow_id",
        "workflow_name",
        "provider",
        "model",
        "result",
        "started_at",
        "completed_at",
    ):
        value = workflow_run.get(key)
        if value is None:
            continue
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        entry[key] = value

    return entry or None


def collect_processed_document_ids(final_state: Any) -> set[str]:
    """Extract the document ids a workflow run actually processed.

    Reads the resolved ``documents`` lists that source / files nodes emit into
    ``final_state["outputs"][node_id]``, plus any top-level ``documents`` /
    ``parallel_document`` carried by single-document (non-fan-out) runs.
    """
    ids: set[str] = set()
    if not isinstance(final_state, dict):
        return ids

    def _add(doc: Any) -> None:
        if isinstance(doc, dict):
            doc_id = doc.get("id")
            doc_type = doc.get("doc_type")
            parent_id = doc.get("parent_id")
        else:
            doc_id = getattr(doc, "id", None)
            doc_type = getattr(doc, "doc_type", None)
            parent_id = getattr(doc, "parent_id", None)
        if isinstance(doc_id, str) and doc_id:
            ids.add(doc_id)
        # For page children emitted by sources.py per-page fan-out, the
        # parent file doc is never in the documents list — include it so
        # complete_run_documents can flip the parent to completed (#2219).
        if doc_type == "page" and isinstance(parent_id, str) and parent_id:
            ids.add(parent_id)

    outputs = final_state.get("outputs")
    if isinstance(outputs, dict):
        for node_output in outputs.values():
            if isinstance(node_output, dict):
                for doc in node_output.get("documents", []) or []:
                    _add(doc)

    # Single-doc / non-fan-out runs may carry documents at the top level.
    for doc in final_state.get("documents", []) or []:
        _add(doc)
    _add(final_state.get("parallel_document"))

    return ids


def complete_run_documents(
    db: Any,
    document_ids: set[str],
    workflow_run: Any | None = None,
) -> int:
    """Advance the run's documents (and their page children) to ``completed``.

    Only documents currently in ``Status.processing`` are advanced. Documents a
    content tool never touched (e.g. a KG-only run over already-transcribed
    docs, which stay ``completed``) keep whatever status they had. Returns the
    number of documents updated (for logging / tests).
    """
    if not document_ids:
        return 0

    from fichero_server.models import Document, Status

    workflow_run_entry = _normalize_workflow_run(workflow_run)

    updated = 0
    changed_ids: list[str] = []

    def _complete(doc: Any, explicit: bool = False) -> None:
        nonlocal updated
        if doc is None:
            return

        changed = False
        current_status = getattr(doc, "status", None)
        if current_status == Status.processing:
            doc.status = Status.completed
            changed = True
        elif explicit and current_status == Status.pending:
            # A parent file doc targeted via per-page fan-out is never touched
            # by save_artifact (which only sees page child IDs), so its status
            # stays pending even though all its children were processed (#2219).
            doc.status = Status.completed
            changed = True

        if workflow_run_entry is not None:
            existing_runs = list(getattr(doc, "workflow_runs", []) or [])
            if workflow_run_entry not in existing_runs:
                existing_runs.append(workflow_run_entry)
                doc.workflow_runs = existing_runs
                changed = True

        if changed:
            db.save(doc)
            updated += 1
            doc_id = getattr(doc, "id", None)
            if doc_id:
                changed_ids.append(doc_id)

    for doc_id in document_ids:
        try:
            _complete(db.get(Document, doc_id), explicit=True)
            # Page children (PDF pages) may have been set to processing during
            # the run even when only the parent id surfaced in the outputs. The
            # processing guard leaves untouched siblings (e.g. unprocessed
            # folder members still pending) alone.
            for child in db.query(Document, parent_id=doc_id):
                _complete(child)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "complete_run_documents: %s failed: %s", doc_id, exc
            )

    if updated:
        logger.info(
            "Workflow completion: marked %d document(s) completed", updated
        )

    # Broadcast the terminal status to the library change-stream so the UI's
    # green-check / completed badge updates live, not on next reload (#2518).
    # Centralised here — both the main runner and the batch path call this — so
    # the completed-status emit can't be added to one caller and forgotten on
    # the other. Best-effort: a broadcast failure must never fail the run.
    if changed_ids:
        try:
            from pathlib import Path

            from fichero_server.api.change_stream import emit_change

            run_id = (
                workflow_run_entry.get("thread_id") if workflow_run_entry else None
            )
            emit_change(
                str(Path(db.path).parent),
                type="document.updated",
                document_ids=changed_ids,
                run_id=run_id,
                actor="workflow",
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "complete_run_documents: change-stream emit failed "
                "(documents persisted; UI will refresh on reload): %s",
                exc,
            )

    return updated
