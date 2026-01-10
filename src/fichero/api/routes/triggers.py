"""
File Trigger API Routes.

Provides REST endpoints for file system triggers:
- CRUD operations for triggers
- Trigger control (pause, resume)
- Execution history queries
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fichero.workflows.file_watcher import (
    FileWatcherManager,
    FileTrigger,
    TriggerConfig,
    TriggerEvent,
    TriggerStatus,
    FilterMode,
    TriggerExecution,
    get_file_watcher,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/triggers", tags=["triggers"])


# Request/Response Models

class TriggerConfigRequest(BaseModel):
    """Trigger configuration request."""
    watch_path: str = Field(..., description="Directory to watch")
    recursive: bool = Field(True, description="Watch subdirectories")
    events: list[str] = Field(
        default=["created"],
        description="Events to trigger on: created, modified, deleted, moved, any"
    )
    filter_mode: str = Field("glob", description="Filter mode: glob, regex, extension")
    filter_pattern: Optional[str] = Field(None, description="Pattern for glob/regex filter")
    filter_extensions: list[str] = Field(default_factory=list, description="Extensions for extension filter")
    exclude_patterns: list[str] = Field(default_factory=list, description="Patterns to exclude")
    debounce_seconds: float = Field(1.0, description="Debounce rapid events")
    batch_delay_seconds: float = Field(5.0, description="Wait before batching events")


class CreateTriggerRequest(BaseModel):
    """Request to create a new file trigger."""
    name: str = Field(..., description="Display name for the trigger")
    workflow_id: str = Field(..., description="ID of workflow to execute")
    config: TriggerConfigRequest = Field(..., description="Trigger configuration")
    inputs_template: dict[str, Any] = Field(
        default_factory=lambda: {"file_path": "{file_path}"},
        description="Template for workflow inputs with placeholders"
    )
    use_batch: bool = Field(True, description="Batch multiple files")
    max_concurrent: int = Field(5, description="Max concurrent batch items")


class TriggerResponse(BaseModel):
    """Trigger response."""
    trigger_id: str
    name: str
    workflow_id: str
    watch_path: str
    recursive: bool
    events: list[str]
    filter_mode: str
    filter_pattern: Optional[str]
    filter_extensions: list[str]
    exclude_patterns: list[str]
    debounce_seconds: float
    batch_delay_seconds: float
    inputs_template: dict[str, Any]
    status: str
    use_batch: bool
    max_concurrent: int
    created_at: datetime
    updated_at: datetime
    last_triggered_at: Optional[datetime]
    trigger_count: int
    error_message: Optional[str]

    @classmethod
    def from_trigger(cls, trigger: FileTrigger) -> "TriggerResponse":
        return cls(
            trigger_id=trigger.trigger_id,
            name=trigger.name,
            workflow_id=trigger.workflow_id,
            watch_path=trigger.config.watch_path,
            recursive=trigger.config.recursive,
            events=[e.value for e in trigger.config.events],
            filter_mode=trigger.config.filter_mode.value,
            filter_pattern=trigger.config.filter_pattern,
            filter_extensions=trigger.config.filter_extensions,
            exclude_patterns=trigger.config.exclude_patterns,
            debounce_seconds=trigger.config.debounce_seconds,
            batch_delay_seconds=trigger.config.batch_delay_seconds,
            inputs_template=trigger.inputs_template,
            status=trigger.status.value,
            use_batch=trigger.use_batch,
            max_concurrent=trigger.max_concurrent,
            created_at=trigger.created_at,
            updated_at=trigger.updated_at,
            last_triggered_at=trigger.last_triggered_at,
            trigger_count=trigger.trigger_count,
            error_message=trigger.error_message,
        )


class TriggerExecutionResponse(BaseModel):
    """Trigger execution response."""
    execution_id: str
    trigger_id: str
    triggered_at: datetime
    file_paths: list[str]
    batch_id: Optional[str]
    status: str
    error: Optional[str]
    completed_at: Optional[datetime]

    @classmethod
    def from_execution(cls, execution: TriggerExecution) -> "TriggerExecutionResponse":
        return cls(
            execution_id=execution.execution_id,
            trigger_id=execution.trigger_id,
            triggered_at=execution.triggered_at,
            file_paths=execution.file_paths,
            batch_id=execution.batch_id,
            status=execution.status,
            error=execution.error,
            completed_at=execution.completed_at,
        )


def _get_watcher() -> FileWatcherManager:
    """Get file watcher or raise 503 if not initialized."""
    watcher = get_file_watcher()
    if not watcher:
        raise HTTPException(
            status_code=503,
            detail="File watcher not initialized"
        )
    return watcher


# Endpoints

@router.post("", response_model=TriggerResponse)
async def create_trigger(request: CreateTriggerRequest) -> TriggerResponse:
    """Create a new file trigger."""
    watcher = _get_watcher()

    try:
        config = TriggerConfig(
            watch_path=request.config.watch_path,
            recursive=request.config.recursive,
            events=[TriggerEvent(e) for e in request.config.events],
            filter_mode=FilterMode(request.config.filter_mode),
            filter_pattern=request.config.filter_pattern,
            filter_extensions=request.config.filter_extensions,
            exclude_patterns=request.config.exclude_patterns,
            debounce_seconds=request.config.debounce_seconds,
            batch_delay_seconds=request.config.batch_delay_seconds,
        )

        trigger = await watcher.create_trigger(
            name=request.name,
            workflow_id=request.workflow_id,
            config=config,
            inputs_template=request.inputs_template,
            use_batch=request.use_batch,
            max_concurrent=request.max_concurrent,
        )

        return TriggerResponse.from_trigger(trigger)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to create trigger: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[TriggerResponse])
async def list_triggers(
    status: Optional[str] = None,
    workflow_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TriggerResponse]:
    """List file triggers with optional filtering."""
    watcher = _get_watcher()

    status_enum = TriggerStatus(status) if status else None

    triggers = await watcher.list_triggers(
        status=status_enum,
        workflow_id=workflow_id,
        limit=limit,
        offset=offset,
    )

    return [TriggerResponse.from_trigger(t) for t in triggers]


@router.get("/{trigger_id}", response_model=TriggerResponse)
async def get_trigger(trigger_id: str) -> TriggerResponse:
    """Get trigger by ID."""
    watcher = _get_watcher()

    trigger = await watcher.get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail=f"Trigger {trigger_id} not found")

    return TriggerResponse.from_trigger(trigger)


@router.delete("/{trigger_id}")
async def delete_trigger(trigger_id: str) -> dict:
    """Delete a file trigger."""
    watcher = _get_watcher()

    # Verify trigger exists
    trigger = await watcher.get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail=f"Trigger {trigger_id} not found")

    await watcher.delete_trigger(trigger_id)
    return {"message": f"Trigger {trigger_id} deleted"}


@router.post("/{trigger_id}/pause", response_model=TriggerResponse)
async def pause_trigger(trigger_id: str) -> TriggerResponse:
    """Pause an active file trigger."""
    watcher = _get_watcher()

    try:
        trigger = await watcher.pause_trigger(trigger_id)
        return TriggerResponse.from_trigger(trigger)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{trigger_id}/resume", response_model=TriggerResponse)
async def resume_trigger(trigger_id: str) -> TriggerResponse:
    """Resume a paused file trigger."""
    watcher = _get_watcher()

    try:
        trigger = await watcher.resume_trigger(trigger_id)
        return TriggerResponse.from_trigger(trigger)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{trigger_id}/executions", response_model=list[TriggerExecutionResponse])
async def get_trigger_executions(
    trigger_id: str,
    limit: int = 50,
) -> list[TriggerExecutionResponse]:
    """Get execution history for a trigger."""
    watcher = _get_watcher()

    # Verify trigger exists
    trigger = await watcher.get_trigger(trigger_id)
    if not trigger:
        raise HTTPException(status_code=404, detail=f"Trigger {trigger_id} not found")

    executions = await watcher.get_trigger_executions(trigger_id, limit=limit)
    return [TriggerExecutionResponse.from_execution(e) for e in executions]
