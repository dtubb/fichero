from __future__ import annotations

from typing import Any


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
    """Look up a document by raw file path, tolerating absolute /files/... inputs."""
    for candidate in iter_document_lookup_paths(file_path):
        docs = db.query(document_model, path=candidate)
        if docs:
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
