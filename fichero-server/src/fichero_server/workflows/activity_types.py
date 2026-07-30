"""
Activity type definitions: enums, dataclasses, and filter.

Shared by activity_store.py and activity.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ActivityType(str, Enum):
    """Types of activity events."""

    # Workflow events
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_PAUSED = "workflow_paused"
    WORKFLOW_RESUMED = "workflow_resumed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    WORKFLOW_DELETED = "workflow_deleted"

    # Node events
    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_RETRY = "node_retry"

    # Batch events
    BATCH_CREATED = "batch_created"
    BATCH_STARTED = "batch_started"
    BATCH_COMPLETED = "batch_completed"
    BATCH_FAILED = "batch_failed"
    BATCH_PAUSED = "batch_paused"
    BATCH_RESUMED = "batch_resumed"
    BATCH_CANCELLED = "batch_cancelled"
    BATCH_ITEM_STARTED = "batch_item_started"
    BATCH_ITEM_COMPLETED = "batch_item_completed"
    BATCH_ITEM_FAILED = "batch_item_failed"

    # System events
    SYSTEM_INFO = "system_info"
    SYSTEM_WARNING = "system_warning"
    SYSTEM_ERROR = "system_error"


class ActivityLevel(str, Enum):
    """Severity level of activity."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Activity:
    """Represents a single activity event."""

    id: str
    type: ActivityType
    level: ActivityLevel
    timestamp: datetime
    message: str
    workflow_id: Optional[str] = None
    batch_id: Optional[str] = None
    thread_id: Optional[str] = None
    node_id: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        # Convert all metadata values to strings for Swift client compatibility
        string_metadata = {
            k: str(v) if v is not None else None for k, v in self.metadata.items()
        }
        # Handle both enum and string values for type/level
        type_value = self.type.value if isinstance(self.type, ActivityType) else self.type
        level_value = self.level.value if isinstance(self.level, ActivityLevel) else self.level
        return {
            "id": self.id,
            "type": type_value,
            "level": level_value,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "workflow_id": self.workflow_id,
            "batch_id": self.batch_id,
            "thread_id": self.thread_id,
            "node_id": self.node_id,
            "metadata": string_metadata,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Activity":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            type=ActivityType(data["type"]),
            level=ActivityLevel(data["level"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            message=data["message"],
            workflow_id=data.get("workflow_id"),
            batch_id=data.get("batch_id"),
            thread_id=data.get("thread_id"),
            node_id=data.get("node_id"),
            metadata=data.get("metadata", {}),
            duration_ms=data.get("duration_ms"),
            error=data.get("error"),
        )


@dataclass
class ActivityStats:
    """Aggregated activity statistics."""

    total_activities: int
    activities_by_type: dict[str, int]
    activities_by_level: dict[str, int]
    error_count: int
    warning_count: int
    avg_workflow_duration_ms: Optional[float]
    success_rate: float
    period_start: datetime
    period_end: datetime


class ActivityFilter:
    """Filter criteria for querying activities."""

    def __init__(
        self,
        types: Optional[list[ActivityType]] = None,
        levels: Optional[list[ActivityLevel]] = None,
        workflow_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
        search: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ):
        self.types = types
        self.levels = levels
        self.workflow_id = workflow_id
        self.batch_id = batch_id
        self.thread_id = thread_id
        self.since = since
        self.until = until
        self.search = search
        self.limit = limit
        self.offset = offset


@dataclass
class WorkflowRun:
    """Typed representation of a workflow execution."""

    thread_id: str
    workflow_id: str
    workflow_name: str
    python_code: str
    execution_log: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    duration_ms: int | None
    error: str | None
    workflow_snapshot: dict[str, Any] | None
    node_name_map: dict[str, Any] | None
    progress_timeline: dict[str, Any] | None
    diagram_mermaid: str | None
    # What the run was actually scoped to (#4384/#4396): the server's
    # RESOLVED document set plus the ids that were requested. None for
    # runs recorded before the column existed.
    resolved_scope: dict[str, Any] | None = None


@dataclass
class CacheEntry:
    """Represents a cached node execution result."""

    cache_key: str
    result: dict[str, Any]
    created_at: datetime
    workflow_id: str
    node_id: str
    tool: str
    file_path: str | None = None
    ttl_seconds: int | None = None
