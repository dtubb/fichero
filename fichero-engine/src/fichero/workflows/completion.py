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
        else:
            doc_id = getattr(doc, "id", None)
        if isinstance(doc_id, str) and doc_id:
            ids.add(doc_id)

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


def complete_run_documents(db: Any, document_ids: set[str]) -> int:
    """Advance the run's documents (and their page children) to ``completed``.

    Only documents currently in ``Status.processing`` are advanced. Documents a
    content tool never touched (e.g. a KG-only run over already-transcribed
    docs, which stay ``completed``) keep whatever status they had. Returns the
    number of documents updated (for logging / tests).
    """
    if not document_ids:
        return 0

    from fichero.models import Document, Status

    updated = 0

    def _complete(doc: Any) -> None:
        nonlocal updated
        if doc is not None and getattr(doc, "status", None) == Status.processing:
            doc.status = Status.completed
            db.save(doc)
            updated += 1

    for doc_id in document_ids:
        try:
            _complete(db.get(Document, doc_id))
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
    return updated
