"""The Activity pane's read-only SQL over the jobs, runs and checkpoints tables (#6588): the persistence layer's own
statements, behind typed functions on the library's managed `Database` (`Database.execute*`, under its lock), so the
workflows and importers that name what a row works on do not carry SQL.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Sequence

from fichero_server.db import activity_records as records


def stage_rows(db: Any, kinds: Sequence[str], since: Optional[datetime]) -> list[tuple[str, str, str]]:
    """(kind, state, subject) of every live job of these kinds, created at or after `since` when given."""
    marks = ", ".join("?" for _ in kinds)
    where = f"kind IN ({marks}) AND deleted_at IS NULL" + (" AND created_at >= ?" if since is not None else "")
    return db.execute_fetchall(f"SELECT kind, state, subject FROM jobs WHERE {where}",
                               [*kinds, *([since] if since is not None else [])])


def running_job_kinds(db: Any) -> list[str]:
    """The kind of every job running now, one entry per job."""
    return [kind for (kind,) in db.execute_fetchall("SELECT kind FROM jobs WHERE state = 'running'")]


def run_workflow_name(db: Any, run_id: str) -> Optional[str]:
    """A workflow run's workflow name, else its workflow id; None when no such run is recorded."""
    row = db.execute_fetchone(f"SELECT workflow_name, workflow_id FROM {records.RUNS} WHERE id = ?", [run_id])
    return (row[0] or row[1]) if row else None


def job_times(db: Any, job_id: str) -> Optional[tuple[Any, Any, Any, Any]]:
    """(state, created_at, started_at, finished_at) of a job; None when there is none."""
    row = db.execute_fetchone("SELECT state, created_at, started_at, finished_at FROM jobs WHERE id = ?", [job_id])
    return tuple(row) if row else None


def parent_kind_and_id(db: Any, job_id: str) -> Optional[tuple[str, str]]:
    """(parent's id, parent's kind) of a job; None when it has no parent."""
    row = db.execute_fetchone("SELECT p.id, p.kind FROM jobs c JOIN jobs p ON p.id = c.parent_id WHERE c.id = ?",
                              [job_id])
    return (row[0], row[1]) if row else None


def has_root_checkpoint(db: Any, thread_id: str) -> bool:
    """Whether a run has a checkpoint to go on from; raises when the checkpoint table does not exist yet."""
    return db.execute_fetchone("SELECT 1 FROM checkpoints WHERE thread_id = ? AND checkpoint_ns = '' LIMIT 1",
                               [thread_id]) is not None
