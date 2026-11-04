"""The worker address table (dev-workflows.run.worker-address): which pane and session a task's worker is at, one generation per
restart. The SQL lives here, behind two typed functions, so `workflows/worker_process.py` holds none (the #1876 rule)."""
from __future__ import annotations

from typing import Any

_DDL = ("CREATE TABLE IF NOT EXISTS worker_addresses (task TEXT PRIMARY KEY, generation INTEGER NOT NULL, "
        "job_id TEXT NOT NULL, kind TEXT NOT NULL, pane TEXT NOT NULL, session_dir TEXT NOT NULL)")
COLUMNS = ("generation", "job_id", "kind", "pane", "session_dir")


def set_address(db: Any, task: str, job_id: str, kind: str, pane: str, session_dir: str) -> int:
    """Rewrite the task's address as the next generation; that generation back."""
    db.execute(_DDL)
    prev = db.execute_fetchone("SELECT generation FROM worker_addresses WHERE task = ?", [task])
    gen = (prev[0] if prev else 0) + 1
    db.execute("DELETE FROM worker_addresses WHERE task = ?", [task])
    db.execute("INSERT INTO worker_addresses VALUES (?, ?, ?, ?, ?, ?)", [task, gen, job_id, kind, pane, session_dir])
    return gen


def address(db: Any, task: str) -> dict[str, Any] | None:
    db.execute(_DDL)
    r = db.execute_fetchone("SELECT generation, job_id, kind, pane, session_dir FROM worker_addresses WHERE task = ?", [task])
    return dict(zip(COLUMNS, r)) if r else None
