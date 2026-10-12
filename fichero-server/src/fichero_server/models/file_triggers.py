"""A watched folder that starts a workflow, and each time it did, as the library keeps them (#5645,
`source.store.one-managed-database`).

`workflows.file_watcher.FileWatcherManager` keeps its triggers here, through the library's one managed `Database`, not
through connections and hand-made tables of its own. A library made before this kept them in `file_triggers` and
`trigger_executions`; `Database._fold_watcher_tables` copies those rows into these models' tables once, at open,
and keeps the old tables.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now


class FileTriggerRecord(BaseModel):
    """One file trigger: the folder it watches, what it reacts to, the workflow it starts, and how it stands."""

    id: str = Field(description="The trigger id (the old `file_triggers.trigger_id`).")
    name: str
    workflow_id: str
    watch_path: str
    recursive: bool = True
    events: list[str] = Field(default_factory=lambda: ["created"])
    filter_mode: str = "glob"
    filter_pattern: Optional[str] = None
    filter_extensions: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    debounce_seconds: float = 1.0
    batch_delay_seconds: float = 5.0
    inputs_template: dict[str, Any] = Field(default_factory=dict)
    status: str
    use_batch: bool = True
    max_concurrent: int = 5
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_triggered_at: Optional[datetime] = None
    trigger_count: int = 0
    error_message: Optional[str] = None


class TriggerExecutionRecord(BaseModel):
    """One time a trigger fired: the files it was handed, the batch it started, and how it ended."""

    id: str = Field(description="The execution id (the old `trigger_executions.execution_id`).")
    trigger_id: str
    triggered_at: datetime
    file_paths: list[str] = Field(default_factory=list)
    batch_id: Optional[str] = None
    status: str = "running"
    error: Optional[str] = None
    completed_at: Optional[datetime] = None
