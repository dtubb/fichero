"""What a workflow run was actually scoped to (#4384 #4396 #4397).

A run recorded which workflow executed and when, but never what it executed
ON. Two consequences, both live:

* **#4384 cannot be built.** Activity has no way to say what a run operated
  on, because nothing persisted it. No amount of UI work fixes that.
* **#4396 was invisible until its effects reached the data.** A client sent a
  whole folder when the user had picked one file; the run did exactly what it
  was asked, recorded nothing about the ask, and the over-scoping was
  discovered by noticing catalogue output on the wrong documents.

So this records the **resolved** set — what the server determined the run
would touch — alongside the requested ids, because *the discrepancy between
them is the defect*. Recording only what the client sent would faithfully
preserve the wrong answer; recording only the resolved set would lose the
evidence that they disagreed.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: Guard against a pathological selection turning a run row into a megabyte of
#: ids. Past this the count is still exact; only the id list is clipped, and
#: the clip is stated in the record rather than silently applied.
MAX_RECORDED_IDS = 5000


def resolve_run_scope(db: Any, selected_doc_ids: list[str] | None) -> dict[str, Any]:
    """Resolve a selection into the document set a run will actually touch.

    Mirrors what the source node does — a folder expands to its file/page
    descendants, a PDF expands to its pages, a leaf stays itself — so the
    recorded scope is what the run really operates on rather than a restatement
    of the request.

    Never raises: a run must not fail because its scope could not be described.
    A resolution failure is recorded AS a failure in the returned record, so an
    unexplained empty scope cannot be mistaken for an empty selection.
    """
    from fichero_server.models import Document

    requested = [str(i) for i in (selected_doc_ids or []) if i]
    record: dict[str, Any] = {
        "requested_ids": requested[:MAX_RECORDED_IDS],
        "requested_count": len(requested),
    }
    if not requested:
        record.update(resolved_ids=[], resolved_count=0, kinds={})
        return record

    resolved: list[str] = []
    seen: set[str] = set()
    kinds: dict[str, str] = {}

    def visit(doc_id: str) -> None:
        if doc_id in seen:
            return
        seen.add(doc_id)
        document = db.get(Document, doc_id)
        if document is None:
            return
        children = list(db.query(Document, parent_id=doc_id) or [])
        if children:
            for child in children:
                visit(child.id)
        else:
            # A leaf is a unit of work: a page, or a file with no pages.
            resolved.append(doc_id)

    try:
        for doc_id in requested:
            document = db.get(Document, doc_id)
            if document is not None:
                kind = getattr(document, "doc_type", None)
                kinds[doc_id] = getattr(kind, "value", None) or str(kind or "unknown")
            visit(doc_id)
    except Exception as exc:  # pragma: no cover - defensive
        # Say so. An empty scope with no explanation reads as "the run touched
        # nothing", which is a different and much more alarming claim.
        logger.warning("run scope resolution failed: %s", exc)
        record.update(
            resolved_ids=[],
            resolved_count=0,
            kinds=kinds,
            resolution_error=str(exc),
        )
        return record

    record.update(
        resolved_ids=resolved[:MAX_RECORDED_IDS],
        resolved_count=len(resolved),
        kinds=kinds,
    )
    if len(resolved) > MAX_RECORDED_IDS:
        record["resolved_ids_truncated"] = True
    return record
