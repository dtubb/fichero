"""Background task type definitions — enums and dataclasses."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class TaskType(str, Enum):
    """Type of background task."""

    REINDEX = "reindex"  # Reindex documents in LanceDB
    METRICS = "metrics"  # Recompute library metrics
    REPAIR = "repair"  # Repair corrupted data
    VECTOR_REPAIR = "vector_repair"  # Repair LanceDB vector index
    KG_METRICS = (
        "kg_metrics"  # Recompute knowledge graph metrics (claims, links, entities)
    )


class TaskStatus(str, Enum):
    """Status of a background task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskConfig:
    """Configuration for a background task."""

    task_type: TaskType
    # Task-specific options
    options: dict[str, Any] = field(default_factory=dict)
    # Priority (lower = higher priority)
    priority: int = 0
    # Timeout in seconds (None = no timeout)
    timeout_seconds: Optional[int] = None


@dataclass
class TaskProgress:
    """Progress information for a running task."""

    current: int = 0
    total: int = 0
    percent: float = 0.0
    message: str = ""
    updated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "message": self.message,
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class TaskResult:
    """Result of a completed task."""

    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "message": self.message,
            "details": self.details,
            "error": self.error,
        }


@dataclass
class BackgroundTask:
    """Represents a background task."""

    task_id: str
    task_type: TaskType
    name: str
    status: TaskStatus
    config: TaskConfig
    progress: TaskProgress = field(default_factory=TaskProgress)
    result: Optional[TaskResult] = None
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "name": self.name,
            "status": self.status.value,
            "progress": self.progress.to_dict(),
            "result": self.result.to_dict() if self.result else None,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat()
            if self.completed_at
            else None,
            "error_message": self.error_message,
        }
