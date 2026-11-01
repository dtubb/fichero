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


def node_document_ids(nodes: Any) -> list[str]:
    """Every id a recipe's nodes name in their `inputs` and `config` (a folder source names its folder there), as the write check reads
    an action's params. A node's own `id` is not one (#6325)."""
    from fichero_server.security import authz

    return authz.target_ids_from_params({"nodes": [{"inputs": n.get("inputs") or {}, "config": n.get("config") or {}} for n in nodes or [] if isinstance(n, dict)]})


#: Tools that write to a path the recipe names, and sources that read the library by a word or a name instead of by a page.
_PATH_WRITING_TOOLS = frozenset({"export_documents", "write_file"})
_LIBRARY_WIDE_SOURCES = frozenset({"search", "collection", "artifacts_source", "annotations_source"})


def recipe_hazard(nodes: Any) -> str | None:
    """Why a caller whose reads differ page by page may not start this recipe, or None. A source that names no page (a search, a folder
    by name, a whole collection) reads whatever matches, denied pages included; a tool that writes to a path copies it off the project.
    What a recipe's other nodes read is whatever its sources give them (#6325, H1)."""
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        tool, inputs, config = node.get("tool"), node.get("inputs") or {}, node.get("config") or {}
        if tool in _PATH_WRITING_TOOLS:
            return f"A recipe with a {tool} step writes to a path on the Mac: the owner's to run."
        if tool in _LIBRARY_WIDE_SOURCES or (tool == "folder" and not (inputs.get("folder_id") or config.get("folder_id"))):
            return f"A recipe with a {tool} source reads by a word or a name, not by pages you may read."
    return None


def run_document_ids(run: Any) -> list[str]:
    """Every document id a run's record names: the scope it resolved, the inputs it was started with and the ids its recipe's nodes name.
    The pages its state, history and answers rest on, so they are shown (or the run is acted on) only to a caller who reads (writes) them all (#6325)."""
    from fichero_server.security import authz

    scope = getattr(run, "resolved_scope", None) or {}
    snapshot = getattr(run, "workflow_snapshot", None) or {}
    ids = [str(i) for key in ("requested_ids", "resolved_ids") for i in scope.get(key) or []]
    ids += authz.target_ids_from_params({"inputs": snapshot.get("inputs") or {}})
    ids += node_document_ids(snapshot.get("nodes"))
    return list(dict.fromkeys(i for i in ids if i))


def resolve_run_scope(
    db: Any,
    selected_doc_ids: list[str] | None,
    *,
    expand_folders: bool = True,
) -> dict[str, Any]:
    """Resolve a selection into the document set a run will actually touch.

    Mirrors what the source node does — a folder expands to its file/page
    descendants, a PDF expands to its pages, a leaf stays itself — so the
    recorded scope is what the run really operates on rather than a restatement
    of the request.

    ``expand_folders`` mirrors the source resolver's flag: when False a
    directly-selected folder is one resolved unit (the "This folder" scope),
    not its descendants, so the recorded scope agrees with what actually ran
    (Daniel, 2026-09-06).

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
                kind_value = getattr(kind, "value", None) or str(kind or "unknown")
                kinds[doc_id] = kind_value
                # "This folder": a directly-selected folder is the unit itself,
                # not its descendants — record it so the scope agrees with the
                # run's source resolver (both gated by expand_folders).
                if not expand_folders and kind_value == "folder":
                    if doc_id not in seen:
                        seen.add(doc_id)
                        resolved.append(doc_id)
                    continue
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
