from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def iter_document_lookup_paths(file_path: str | None) -> tuple[str, ...]:
    """Return the path forms that may match a stored Document.path."""
    if not file_path:
        return ()

    path_str = str(file_path)
    candidates: list[str] = [path_str]

    if "/files/" in path_str:
        rel_path = "files/" + path_str.split("/files/", 1)[1]
        if rel_path not in candidates:
            candidates.append(rel_path)

    return tuple(candidates)


def find_document_by_path(
    db: Any,
    document_model: type[Any],
    file_path: str | None,
) -> Any:
    """Look up a document by raw file path, tolerating absolute /files/... inputs.

    When a path matches more than one document the choice is ambiguous — picking
    one silently is exactly the #2430 class of bug (an artifact routed to the
    wrong document). We can't know which duplicate the caller meant, so we don't
    hide it: log a loud warning naming the candidates (#2507) and still return
    the first match to preserve behaviour. Escalate to skip/raise later if the
    ambiguity proves to be a real corruption source.
    """
    for candidate in iter_document_lookup_paths(file_path):
        docs = db.query(document_model, path=candidate)
        if docs:
            if len(docs) > 1:
                logger.warning(
                    "find_document_by_path: %d documents share path %r — "
                    "resolving to the first (%s); the rest are ambiguous: %s",
                    len(docs),
                    candidate,
                    getattr(docs[0], "id", "?"),
                    [getattr(d, "id", "?") for d in docs[1:]],
                )
            return docs[0]
    return None


def register_path_mapping(
    path_to_doc: dict[str, Any],
    key: str,
    doc_id: Any,
) -> None:
    """Record ``key -> doc_id`` in a path map, loud on a conflicting overwrite.

    The per-tool ``path_to_doc`` maps drive artifact routing. Two documents
    sharing a path would silently overwrite (last-wins) and could route a later
    save to the wrong document — the #2430 class of bug. We can't tell which the
    caller meant, so we keep last-wins behaviour but log a warning naming both
    ids when an existing key is overwritten with a *different* id (#2507).
    """
    existing = path_to_doc.get(key)
    if existing is not None and existing != doc_id:
        logger.warning(
            "path_to_doc: path %r already mapped to %s — overwriting with %s "
            "(ambiguous duplicate paths; downstream artifact routing may pick "
            "the wrong document)",
            key,
            existing,
            doc_id,
        )
    path_to_doc[key] = doc_id


def resolve_path_to_doc(path_to_doc: dict[str, Any], file_path: str | None) -> Any:
    """Look up a doc id in a path->id map, tolerating absolute vs relative keys.

    The map may be keyed by either the absolute on-disk path or the
    library-relative ``files/...`` path depending on the caller. ``file_path``
    is normalised to both forms so a lookup succeeds regardless of which form
    the map was built with (#2188).
    """
    for candidate in iter_document_lookup_paths(file_path):
        if candidate in path_to_doc:
            return path_to_doc[candidate]
    return None


def documents_from_state_outputs(
    state: dict[str, Any] | Any, files: Any
) -> list[Any]:
    """Recover the index-aligned ``documents`` list for ``files`` from an
    upstream node's recorded outputs (#4298).

    Vision tools scope their work per-document: for a page-scoped run the
    source node emits ``files=[parent.pdf]`` paired with ``documents=[page]``,
    and the page's ``sequence`` is what confines the vision pass to that ONE
    page. When a workflow graph wires only the ``files`` port into the tool
    (older stored copies of presets, hand-built workflows), the pairing is
    lost — the tool sees a bare PDF path and falls into the whole-PDF branch,
    processing (and billing) EVERY page of a document the user selected one
    page of.

    The pairing is still present in the LangGraph state: every completed
    node's full output dict lives in ``state["outputs"][node_id]``. This scans
    for a node whose ``files`` output is exactly the list this tool received
    and returns its ``documents``. Returns ``[]`` when no aligned producer is
    found (behaviour unchanged: the tool proceeds document-less).
    """
    if not files:
        return []
    wanted = [files] if isinstance(files, str) else list(files)
    outputs = state.get("outputs") or {}
    if not isinstance(outputs, dict):
        return []
    for node_output in outputs.values():
        if not isinstance(node_output, dict):
            continue
        out_files = node_output.get("files")
        docs = node_output.get("documents")
        if not docs or not isinstance(out_files, list):
            continue
        if out_files == wanted and len(docs) == len(wanted):
            logger.info(
                "documents port unwired — recovered %d aligned document(s) "
                "from upstream node outputs (#4298)",
                len(docs),
            )
            return list(docs)
    return []
