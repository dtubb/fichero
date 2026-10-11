"""Whole-project reads of the document tree, for work that walks every page once (the recipe runner's batches).

Persistence layer (#1876): the SQL lives here, behind typed functions; callers never write it.
"""

from __future__ import annotations

from typing import Any, NamedTuple


class TreeNode(NamedTuple):
    parent_id: str | None
    doc_type: str
    file_type: str


def live_tree(db: Any) -> dict[str, TreeNode]:
    """Every live document: id -> (parent id, doc type, file type). One query for the whole project."""
    rows = db.execute_fetchall(
        "SELECT id, parent_id, doc_type, COALESCE(file_type, '') FROM documents WHERE deleted_at IS NULL")
    return {r[0]: TreeNode(r[1], str(r[2]), str(r[3])) for r in rows}


def live_chunks_of(db: Any, parent_ids: list[str]) -> dict[str, list[str]]:
    """The live pages cut from each of these photographs, in the order they were cut: parent id -> chunk ids."""
    if not parent_ids:
        return {}
    marks = ", ".join("?" for _ in parent_ids)
    cut: dict[str, list[str]] = {}
    for doc_id, parent in db.execute_fetchall(
            f"SELECT id, parent_id FROM documents WHERE deleted_at IS NULL AND doc_type = 'chunk' "
            f"AND parent_id IN ({marks}) ORDER BY created_at, id", parent_ids):
        cut.setdefault(parent, []).append(doc_id)
    return cut


def trashed_ids(db: Any) -> set[str]:
    """Every document in the project's Trash (its `deleted_at` set): what knowledge reads hide behind."""
    return {row[0] for row in db.execute_fetchall("SELECT id FROM documents WHERE deleted_at IS NOT NULL") or []}
