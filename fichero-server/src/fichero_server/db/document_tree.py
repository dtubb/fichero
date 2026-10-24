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


def set_job_reason(db: Any, job_id: str, reason: str) -> None:
    """Say why on a job's row, whatever its state."""
    db.execute("UPDATE jobs SET reason = ? WHERE id = ?", [reason, job_id])


def release_waiting_job(db: Any, job_id: str, *, clear_reason: bool = False) -> None:
    """A parked (waiting) job is taken up now: its `run_after` goes, and its reason too when asked. Any other state is left alone."""
    sets = "run_after = NULL, reason = NULL" if clear_reason else "run_after = NULL"
    db.execute(f"UPDATE jobs SET {sets} WHERE id = ? AND state = 'waiting'", [job_id])


def clear_job_reason_if(db: Any, job_id: str, reasons: tuple[str, ...]) -> None:
    """Clear a job's reason only when it is one of `reasons` (a reason some other check wrote stays)."""
    marks = ", ".join("?" for _ in reasons)
    db.execute(f"UPDATE jobs SET reason = NULL WHERE id = ? AND reason IN ({marks})", [job_id, *reasons])


def latest_job_detail(db: Any, kind: str, subject: str) -> str | None:
    """The detail text of the newest job of this kind for this subject, or None."""
    row = db.execute_fetchone(
        "SELECT detail FROM jobs WHERE kind = ? AND subject = ? ORDER BY created_at DESC LIMIT 1", [kind, subject])
    return row[0] if row else None


def live_page_ids_mentioning(db: Any, word: str) -> list[str]:
    """The ids of live documents whose page text contains `word` (a coarse prefilter; the caller checks each)."""
    return [r[0] for r in db.execute_fetchall(
        "SELECT id FROM documents WHERE page_content LIKE ? AND deleted_at IS NULL", [f"%{word}%"])]
