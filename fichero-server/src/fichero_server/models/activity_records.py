"""Activity events and workflow runs, as the library keeps them (#5645, `source.store.one-managed-database`).

`workflows.activity_store.ActivityStore` keeps them here, through the library's one managed `Database`, not through
connections and hand-made tables of its own; the ordered, paged and partial reads and writes are in
`db.activity_records`. A library made before this kept them in `activities` and `workflow_runs`;
`Database._fold_activity_tables` copies those rows into these models' tables once, at open, in chunks, and keeps the
old tables. The store still hands its callers the `Activity` and `WorkflowRun` it always did.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ActivityEventRecord(BaseModel):
    """One activity event: what happened, when, and in which workflow, batch, run and node."""

    id: str
    type: str
    level: str
    timestamp: datetime
    message: str
    workflow_id: Optional[str] = None
    batch_id: Optional[str] = None
    thread_id: Optional[str] = None
    node_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None


class WorkflowRunRecord(BaseModel):
    """One workflow run: what ran, its code and log, how far it got, and how it ended. Its id is the run's thread
    id, which is also its row's id in the `jobs` table."""

    id: str = Field(description="The run's thread id (the old `workflow_runs.thread_id`).")
    workflow_id: str
    workflow_name: str
    python_code: Optional[str] = None
    execution_log: Optional[str] = None
    status: str = "running"
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None
    workflow_snapshot: Optional[dict[str, Any]] = None
    node_name_map: Optional[dict[str, Any]] = None
    progress_timeline: Optional[dict[str, Any]] = None
    diagram_mermaid: Optional[str] = None
    resolved_scope: Optional[dict[str, Any]] = None
    run_usage: Optional[dict[str, Any]] = None
    estimated_cost: Optional[float] = None
