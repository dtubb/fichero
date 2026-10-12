"""A batch of workflow runs, as the library keeps it (#5645, `source.store.one-managed-database`).

`execution.batch.BatchManager` keeps its batches here, through the library's one managed `Database`, not through
connections and hand-made tables of its own. A library made before this kept them in `batches` and `batch_items`;
`Database._fold_batch_tables` copies those rows into these models' tables once, at open, and keeps the old tables.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class BatchRecord(BaseModel):
    """One batch: the workflow it runs over its items, and how it stands."""

    id: str = Field(description="The batch id (the old `batches.batch_id`).")
    workflow_id: str
    status: str
    max_concurrent: int = 5
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class BatchItemRecord(BaseModel):
    """One item of a batch: one workflow run, by its thread, with its inputs and how it ended."""

    id: str = Field(description="`<batch id>:<thread id>`, the old table's two-part key as one.")
    batch_id: str
    thread_id: str
    item_index: int
    inputs: dict[str, Any] = Field(default_factory=dict)
    status: str
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @staticmethod
    def key(batch_id: str, thread_id: str) -> str:
        return f"{batch_id}:{thread_id}"
