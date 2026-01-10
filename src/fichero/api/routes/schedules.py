"""
Schedule API Routes.

Provides REST endpoints for workflow scheduling:
- CRUD operations for schedules
- Schedule execution control (pause, resume, trigger)
- Run history queries
"""

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from fichero.workflows.scheduler import (
    WorkflowScheduler,
    Schedule,
    ScheduleConfig,
    ScheduleType,
    ScheduleStatus,
    ScheduleRun,
    get_scheduler,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedules", tags=["schedules"])


# Request/Response Models

class ScheduleConfigRequest(BaseModel):
    """Schedule configuration request."""
    schedule_type: str = Field(..., description="Type: cron, interval, or once")
    cron_expression: Optional[str] = Field(None, description="Cron expression (e.g., '0 9 * * 1')")
    interval_seconds: Optional[int] = Field(None, description="Interval in seconds")
    run_at: Optional[datetime] = Field(None, description="One-time run datetime")
    timezone: str = Field("UTC", description="Timezone for schedule")
    start_date: Optional[datetime] = Field(None, description="Schedule start date")
    end_date: Optional[datetime] = Field(None, description="Schedule end date")
    max_runs: Optional[int] = Field(None, description="Maximum number of runs")


class CreateScheduleRequest(BaseModel):
    """Request to create a new schedule."""
    name: str = Field(..., description="Display name for the schedule")
    workflow_id: str = Field(..., description="ID of workflow to execute")
    config: ScheduleConfigRequest = Field(..., description="Schedule configuration")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Workflow inputs")
    use_batch: bool = Field(False, description="Use batch execution")
    batch_items: list[dict[str, Any]] = Field(default_factory=list, description="Batch input items")
    max_concurrent: int = Field(5, description="Max concurrent batch items")


class ScheduleResponse(BaseModel):
    """Schedule response."""
    schedule_id: str
    name: str
    workflow_id: str
    schedule_type: str
    cron_expression: Optional[str]
    interval_seconds: Optional[int]
    run_at: Optional[datetime]
    timezone: str
    status: str
    inputs: dict[str, Any]
    use_batch: bool
    batch_items: list[dict[str, Any]]
    max_concurrent: int
    created_at: datetime
    updated_at: datetime
    last_run_at: Optional[datetime]
    next_run_at: Optional[datetime]
    run_count: int
    error_message: Optional[str]

    @classmethod
    def from_schedule(cls, schedule: Schedule) -> "ScheduleResponse":
        return cls(
            schedule_id=schedule.schedule_id,
            name=schedule.name,
            workflow_id=schedule.workflow_id,
            schedule_type=schedule.config.schedule_type.value,
            cron_expression=schedule.config.cron_expression,
            interval_seconds=schedule.config.interval_seconds,
            run_at=schedule.config.run_at,
            timezone=schedule.config.timezone,
            status=schedule.status.value,
            inputs=schedule.inputs,
            use_batch=schedule.use_batch,
            batch_items=schedule.batch_items,
            max_concurrent=schedule.max_concurrent,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at,
            last_run_at=schedule.last_run_at,
            next_run_at=schedule.next_run_at,
            run_count=schedule.run_count,
            error_message=schedule.error_message,
        )


class ScheduleRunResponse(BaseModel):
    """Schedule run response."""
    run_id: str
    schedule_id: str
    started_at: datetime
    completed_at: Optional[datetime]
    status: str
    batch_id: Optional[str]
    error: Optional[str]

    @classmethod
    def from_run(cls, run: ScheduleRun) -> "ScheduleRunResponse":
        return cls(
            run_id=run.run_id,
            schedule_id=run.schedule_id,
            started_at=run.started_at,
            completed_at=run.completed_at,
            status=run.status,
            batch_id=run.batch_id,
            error=run.error,
        )


def _get_scheduler() -> WorkflowScheduler:
    """Get scheduler or raise 503 if not initialized."""
    scheduler = get_scheduler()
    if not scheduler:
        raise HTTPException(
            status_code=503,
            detail="Scheduler not initialized"
        )
    return scheduler


# Endpoints

@router.post("", response_model=ScheduleResponse)
async def create_schedule(request: CreateScheduleRequest) -> ScheduleResponse:
    """Create a new workflow schedule."""
    scheduler = _get_scheduler()

    try:
        config = ScheduleConfig(
            schedule_type=ScheduleType(request.config.schedule_type),
            cron_expression=request.config.cron_expression,
            interval_seconds=request.config.interval_seconds,
            run_at=request.config.run_at,
            timezone=request.config.timezone,
            start_date=request.config.start_date,
            end_date=request.config.end_date,
            max_runs=request.config.max_runs,
        )

        schedule = await scheduler.create_schedule(
            name=request.name,
            workflow_id=request.workflow_id,
            config=config,
            inputs=request.inputs,
            use_batch=request.use_batch,
            batch_items=request.batch_items,
            max_concurrent=request.max_concurrent,
        )

        return ScheduleResponse.from_schedule(schedule)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Failed to create schedule: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=list[ScheduleResponse])
async def list_schedules(
    status: Optional[str] = None,
    workflow_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[ScheduleResponse]:
    """List schedules with optional filtering."""
    scheduler = _get_scheduler()

    status_enum = ScheduleStatus(status) if status else None

    schedules = await scheduler.list_schedules(
        status=status_enum,
        workflow_id=workflow_id,
        limit=limit,
        offset=offset,
    )

    return [ScheduleResponse.from_schedule(s) for s in schedules]


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: str) -> ScheduleResponse:
    """Get schedule by ID."""
    scheduler = _get_scheduler()

    schedule = await scheduler.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")

    return ScheduleResponse.from_schedule(schedule)


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str) -> dict:
    """Delete a schedule."""
    scheduler = _get_scheduler()

    # Verify schedule exists
    schedule = await scheduler.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")

    await scheduler.delete_schedule(schedule_id)
    return {"message": f"Schedule {schedule_id} deleted"}


@router.post("/{schedule_id}/pause", response_model=ScheduleResponse)
async def pause_schedule(schedule_id: str) -> ScheduleResponse:
    """Pause an active schedule."""
    scheduler = _get_scheduler()

    try:
        schedule = await scheduler.pause_schedule(schedule_id)
        return ScheduleResponse.from_schedule(schedule)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{schedule_id}/resume", response_model=ScheduleResponse)
async def resume_schedule(schedule_id: str) -> ScheduleResponse:
    """Resume a paused schedule."""
    scheduler = _get_scheduler()

    try:
        schedule = await scheduler.resume_schedule(schedule_id)
        return ScheduleResponse.from_schedule(schedule)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{schedule_id}/trigger", response_model=ScheduleRunResponse)
async def trigger_schedule(schedule_id: str) -> ScheduleRunResponse:
    """Manually trigger a schedule to run now."""
    scheduler = _get_scheduler()

    try:
        run = await scheduler.trigger_now(schedule_id)
        return ScheduleRunResponse.from_run(run)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{schedule_id}/runs", response_model=list[ScheduleRunResponse])
async def get_schedule_runs(
    schedule_id: str,
    limit: int = 50,
) -> list[ScheduleRunResponse]:
    """Get run history for a schedule."""
    scheduler = _get_scheduler()

    # Verify schedule exists
    schedule = await scheduler.get_schedule(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail=f"Schedule {schedule_id} not found")

    runs = await scheduler.get_schedule_runs(schedule_id, limit=limit)
    return [ScheduleRunResponse.from_run(r) for r in runs]
