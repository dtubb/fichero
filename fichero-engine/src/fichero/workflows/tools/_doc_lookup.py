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
