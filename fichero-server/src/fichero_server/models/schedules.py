"""A workflow run on a schedule, and each time it ran, as the library keeps them (#5645,
`source.store.one-managed-database`).

`workflows.scheduler.WorkflowScheduler` keeps its schedules here, through the library's one managed `Database`, not
through connections and hand-made tables of its own. A library made before this kept them in `schedules` and
`schedule_runs`; `Database._fold_scheduler_tables` copies those rows into these models' tables once, at open, and keeps
the old tables.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now


class ScheduleRecord(BaseModel):
    """One schedule: the workflow, when it runs (cron, interval or once), its inputs, and how it stands."""

    id: str = Field(description="The schedule id (the old `schedules.schedule_id`).")
    name: str
    workflow_id: str
    schedule_type: str
    cron_expression: Optional[str] = None
    interval_seconds: Optional[int] = None
    #: Set only for a one-time schedule (`schedule_type` "once"); None for cron and interval ones, on purpose.
    run_at: Optional[datetime] = None
    timezone: str = "UTC"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    max_runs: Optional[int] = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    status: str
    use_batch: bool = False
    batch_items: list[dict[str, Any]] = Field(default_factory=list)
    max_concurrent: int = 5
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    run_count: int = 0
    error_message: Optional[str] = None


class ScheduleRunRecord(BaseModel):
    """One time a schedule ran: when, the batch it started, and how it ended."""

    id: str = Field(description="The run id (the old `schedule_runs.run_id`).")
    schedule_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "running"
    batch_id: Optional[str] = None
    error: Optional[str] = None
