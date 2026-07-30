"""
Activity Tracking API Routes.

Endpoints for monitoring workflow and batch activity:
- Query historical activities
- Real-time activity streaming via SSE (the ONE live transport — see the
  tombstone where /ws used to be)
- Activity statistics and metrics

NOTE: All activity data is stored per-library in the library's database file.
Routes require the X-Fichero-Library-Path header.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from fichero_server.core.timeutil import utc_now
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from fichero_server.api.auth import action_context
from fichero_server.api.change_stream import ChangeEvent, _change_hub
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.db import Database
from fichero_server.workflows.activity import (
    Activity,
    ActivityFilter,
    ActivityLevel,
    ActivityStats,
    ActivityType,
    get_activity_tracker,
)
from fichero_server.models import ActivityListResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/activity", tags=["activity"])
_KEEPALIVE_TIMEOUT = 10.0


def _parse_iso_to_naive_utc(value: str) -> datetime:
    """Parse ISO-8601 timestamps and normalize to naive UTC for DuckDB."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


# Pydantic models for API


class ActivityResponse(BaseModel):
    """Response model for an activity event."""

    id: str
    type: str
    level: str
    timestamp: str
    message: str
    workflow_id: Optional[str] = None
    batch_id: Optional[str] = None
    thread_id: Optional[str] = None
    node_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    duration_ms: Optional[float] = None
    error: Optional[str] = None

    @classmethod
    def from_activity(cls, activity: Activity) -> "ActivityResponse":
        # Convert metadata values to strings for Swift client compatibility
        string_metadata = {
            k: str(v) if v is not None else None for k, v in activity.metadata.items()
        }
        return cls(
            id=activity.id,
            type=activity.type.value,
            level=activity.level.value,
            timestamp=activity.timestamp.isoformat(),
            message=activity.message,
            workflow_id=activity.workflow_id,
            batch_id=activity.batch_id,
            thread_id=activity.thread_id,
            node_id=activity.node_id,
            metadata=string_metadata,
            duration_ms=activity.duration_ms,
            error=activity.error,
        )


def _change_event_to_activity_response(event: ChangeEvent) -> ActivityResponse:
    return ActivityResponse(
        id=f"change-{event.event_id or uuid4().hex}",
        type=ActivityType.SYSTEM_INFO.value,
        level=ActivityLevel.INFO.value,
        timestamp=event.ts,
        message=f"{event.type} changed",
        metadata={
            "change_type": event.type,
            "actor": event.actor,
            "run_id": event.run_id,
            "origin_window": event.origin_window,
            "origin_user": event.origin_user,
            "ts": event.ts,
            "change_metadata": json.dumps(event.metadata),
            "document_ids": json.dumps(event.document_ids),
            "entity_ids": json.dumps(event.entity_ids),
            "claim_ids": json.dumps(event.claim_ids),
            "artifact_ids": json.dumps(event.artifact_ids),
            "citation_ids": json.dumps(event.citation_ids),
            "reference_ids": json.dumps(event.reference_ids),
            "interpretation_ids": json.dumps(event.interpretation_ids),
        },
    )


class CleanupResponse(BaseModel):
    deleted: int
    older_than: str


class ActivityCleanupParams(BaseModel):
    days: int = Field(ge=1, le=365)


class ActivityStatsResponse(BaseModel):
    """Response model for activity statistics."""

    total_activities: int
    activities_by_type: dict[str, int]
    activities_by_level: dict[str, int]
    error_count: int
    warning_count: int
    avg_workflow_duration_ms: Optional[float] = None
    success_rate: float
    period_start: str
    period_end: str

    @classmethod
    def from_stats(cls, stats: ActivityStats) -> "ActivityStatsResponse":
        return cls(
            total_activities=stats.total_activities,
            activities_by_type=stats.activities_by_type,
            activities_by_level=stats.activities_by_level,
            error_count=stats.error_count,
            warning_count=stats.warning_count,
            avg_workflow_duration_ms=stats.avg_workflow_duration_ms,
            success_rate=stats.success_rate,
            period_start=stats.period_start.isoformat(),
            period_end=stats.period_end.isoformat(),
        )


# API Endpoints


@router.get("", response_model=ActivityListResponse)
async def list_activities(
    db: Database = Depends(get_library_database),
    types: Optional[str] = Query(None, description="Comma-separated activity types"),
    levels: Optional[str] = Query(
        None, description="Comma-separated levels (info,warning,error)"
    ),
    workflow_id: Optional[str] = None,
    batch_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    since: Optional[str] = Query(None, description="ISO datetime string"),
    until: Optional[str] = Query(None, description="ISO datetime string"),
    search: Optional[str] = Query(None, description="Search in message text"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[ActivityResponse]:
    """
    Query historical activities with filtering.

    Supports filtering by type, level, workflow/batch/thread IDs, time range,
    and full-text search in messages.
    """
    tracker = get_activity_tracker(str(db.path))

    # Parse types
    type_list = None
    if types:
        try:
            type_list = [ActivityType(t.strip()) for t in types.split(",")]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid activity type: {e}")

    # Parse levels
    level_list = None
    if levels:
        try:
            level_list = [ActivityLevel(lvl.strip()) for lvl in levels.split(",")]
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"Invalid activity level: {e}")

    # Parse timestamps (handle ISO8601 with Z suffix)
    since_dt = None
    until_dt = None
    if since:
        try:
            since_dt = _parse_iso_to_naive_utc(since)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid 'since' datetime format"
            )
    if until:
        try:
            until_dt = _parse_iso_to_naive_utc(until)
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid 'until' datetime format"
            )

    filter = ActivityFilter(
        types=type_list,
        levels=level_list,
        workflow_id=workflow_id,
        batch_id=batch_id,
        thread_id=thread_id,
        since=since_dt,
        until=until_dt,
        search=search,
        limit=limit,
        offset=offset,
    )

    activities = await tracker.query(filter)
    items = [ActivityResponse.from_activity(a) for a in activities]
    return ActivityListResponse(items=items, count=len(items))


@router.get("/recent", response_model=ActivityListResponse)
async def get_recent_activities(
    db: Database = Depends(get_library_database),
    limit: int = Query(50, ge=1, le=200),
) -> list[ActivityResponse]:
    """
    Get recent activities from memory buffer.

    This is faster than querying the database and useful for
    real-time dashboards.
    """
    tracker = get_activity_tracker(str(db.path))
    activities = tracker.get_recent(limit)
    return ActivityListResponse(items=[ActivityResponse.from_activity(a) for a in activities], count=len(activities))


@router.get("/stats", response_model=ActivityStatsResponse)
async def get_activity_stats(
    db: Database = Depends(get_library_database),
    hours: int = Query(24, ge=1, le=720, description="Number of hours to analyze"),
) -> ActivityStatsResponse:
    """
    Get aggregated activity statistics.

    Returns counts by type and level, error/warning counts,
    average workflow duration, and success rate.
    """
    tracker = get_activity_tracker(str(db.path))

    until = utc_now()
    since = until - timedelta(hours=hours)

    stats = await tracker.get_stats(since=since, until=until)
    return ActivityStatsResponse.from_stats(stats)


@router.get("/stream")
async def stream_activities(
    db: Database = Depends(get_library_database),
    types: Optional[str] = Query(None, description="Comma-separated activity types"),
    levels: Optional[str] = Query(None, description="Comma-separated levels"),
    workflow_id: Optional[str] = None,
    batch_id: Optional[str] = None,
):
    """
    Stream real-time activities via Server-Sent Events.

    Clients receive activity events as they occur, filtered by
    the provided criteria.
    """
    tracker = get_activity_tracker(str(db.path))
    library_path = str(Path(db.path).parent)

    # Parse filter
    type_list = None
    if types:
        try:
            type_list = [ActivityType(t.strip()) for t in types.split(",")]
        except ValueError:
            pass

    level_list = None
    if levels:
        try:
            level_list = [ActivityLevel(lvl.strip()) for lvl in levels.split(",")]
        except ValueError:
            pass

    filter = ActivityFilter(
        types=type_list,
        levels=level_list,
        workflow_id=workflow_id,
        batch_id=batch_id,
    )

    # Subscribe to activity stream
    sub_id = tracker.subscribe(filter)
    change_subscription = _change_hub.connect(library_path)

    async def event_generator():
        tracker_stream = tracker.stream(sub_id, filter)
        try:
            while True:
                tracker_task = asyncio.create_task(anext(tracker_stream))
                change_task = asyncio.create_task(change_subscription.queue.get())
                try:
                    done, pending = await asyncio.wait(
                        {tracker_task, change_task},
                        timeout=_KEEPALIVE_TIMEOUT,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if not done:
                        yield ": keepalive\n\n"
                        continue
                    if change_task in done:
                        change_event = change_task.result()
                        response = _change_event_to_activity_response(change_event)
                        yield f"data: {response.model_dump_json()}\n\n"
                    if tracker_task in done:
                        activity = tracker_task.result()
                        response = ActivityResponse.from_activity(activity)
                        yield f"data: {response.model_dump_json()}\n\n"
                finally:
                    for task in (tracker_task, change_task):
                        if not task.done():
                            task.cancel()
                    results = await asyncio.gather(
                        tracker_task, change_task, return_exceptions=True
                    )
                    if any(isinstance(result, StopAsyncIteration) for result in results):
                        return
        except asyncio.CancelledError:
            logger.info("activity-stream: client cancelled cleanly lib=%s", library_path)
            raise
        except GeneratorExit:
            logger.info("activity-stream: client closed cleanly lib=%s", library_path)
            raise
        except Exception as e:
            logger.exception("activity-stream: SSE failed lib=%s", library_path)
            error_event = {"error": str(e)}
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            await tracker_stream.aclose()
            tracker.unsubscribe(sub_id)
            _change_hub.unsubscribe(library_path, change_subscription.queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# /ws (a second, parallel live transport duplicating GET /activity/stream) was
# deleted in the verify-then-prune pass (#3235, 2026-07-30). One live transport
# — SSE, which folds change frames (#3159) and carries the client's
# reconnect/backoff semantics — is the invariant worth protecting; the
# WebSocket path had no callers (app, CLI, MCP, docs all verified) and did not
# fold change events, so any client using it would silently miss remote
# mutations.


@router.get("/workflow/{workflow_id}", response_model=ActivityListResponse)
async def get_workflow_activity(
    workflow_id: str,
    db: Database = Depends(get_library_database),
    limit: int = Query(100, ge=1, le=1000),
) -> list[ActivityResponse]:
    """Get all activity for a specific workflow."""
    tracker = get_activity_tracker(str(db.path))

    filter = ActivityFilter(
        workflow_id=workflow_id,
        limit=limit,
    )

    activities = await tracker.query(filter)
    return ActivityListResponse(items=[ActivityResponse.from_activity(a) for a in activities], count=len(activities))


@router.get("/batch/{batch_id}", response_model=ActivityListResponse)
async def get_batch_activity(
    batch_id: str,
    db: Database = Depends(get_library_database),
    limit: int = Query(100, ge=1, le=1000),
) -> list[ActivityResponse]:
    """Get all activity for a specific batch."""
    tracker = get_activity_tracker(str(db.path))

    filter = ActivityFilter(
        batch_id=batch_id,
        limit=limit,
    )

    activities = await tracker.query(filter)
    return ActivityListResponse(items=[ActivityResponse.from_activity(a) for a in activities], count=len(activities))


@router.delete("/cleanup")
async def cleanup_old_activities(
    db: Database = Depends(get_library_database_for_write),
    days: int = Query(
        30, ge=1, le=365, description="Delete activities older than N days"
    ),
    ctx: ActionContext = Depends(action_context),
) -> CleanupResponse:
    """
    Delete old activities to manage database size.

    Returns the number of deleted activities.
    """
    result = registry.invoke(
        db,
        "activity.cleanup",
        {"days": days},
        ctx,
    )
    return CleanupResponse.model_validate(result.result)


@action(
    "activity.cleanup",
    ActivityCleanupParams,
    domains=["activity"],
    undoable=False,
)
def _action_cleanup_old_activities(
    db: Database,
    params: ActivityCleanupParams,
    ctx: ActionContext,
) -> tuple[dict[str, Any], ChangeSpec]:
    tracker = get_activity_tracker(str(db.path))
    older_than = utc_now() - timedelta(days=params.days)
    deleted = tracker.store.delete_old_sync(older_than)
    result = {"deleted": deleted, "older_than": older_than.isoformat()}
    spec = ChangeSpec(
        domains=["activity"],
        target_ids=[],
        before={"days": params.days},
        after=result,
        emit_type="activity.updated",
    )
    return result, spec


# =============================================================================
# Enhanced Activity Metrics (Issue #425)
# =============================================================================
#
# /feed, /trends, /top and their response models (~420 lines of #425
# dashboard-shaped aggregation) were deleted in the verify-then-prune pass
# (#3235, 2026-07-30): no UI was ever built on them and no non-app caller
# existed (app, CLI, MCP, docs all verified — the CLI's `top_entities` reads
# /api/entities/top, not /activity/top). If an activity dashboard becomes
# real, rebuild the aggregations against the need it actually has, next to
# /metrics/summary below. (/entity-types — a hardcoded 4-element literal
# served over HTTP — went earlier, in the 2026-07-27 endpoint cleanup.)


class ActivityMetricsSummary(BaseModel):
    """Enhanced activity metrics summary."""

    total_activities: int
    total_workflows: int
    total_batches: int
    error_count: int
    warning_count: int
    success_rate: float
    avg_workflow_duration_ms: float | None
    avg_batch_duration_ms: float | None
    busiest_hour: int | None
    period_start: str
    period_end: str


# -----------------------------------------------------------------------------
# Enhanced Metrics Endpoint
# -----------------------------------------------------------------------------


@router.get("/metrics/summary", response_model=ActivityMetricsSummary)
async def get_activity_metrics_summary(
    db: Database = Depends(get_library_database),
    hours: int = Query(24, ge=1, le=720),
) -> ActivityMetricsSummary:
    """
    Get comprehensive activity metrics summary.

    Includes trends, rates, and busiest periods.
    """
    tracker = get_activity_tracker(str(db.path))

    until = utc_now()
    since = until - timedelta(hours=hours)

    # Get basic stats
    stats = await tracker.get_stats(since=since, until=until)

    # Get activities for enhanced metrics
    filter = ActivityFilter(since=since, until=until, limit=10000)
    activities = await tracker.query(filter)

    # Count by hour to find busiest
    hour_counts: dict[int, int] = {}
    workflow_durations: list[float] = []
    batch_durations: list[float] = []
    workflow_count = 0
    batch_count = 0

    for act in activities:
        # Hour distribution, in UTC. Timestamps are aware UTC as of #4347, so
        # `busiest_hour` below is a UTC hour-of-day — before the sweep it was
        # accidentally the *server's* local hour, which was never the viewer's
        # either. A client that wants a local hour converts the UTC one.
        hour = act.timestamp.hour
        hour_counts[hour] = hour_counts.get(hour, 0) + 1

        # Durations
        if act.type == ActivityType.WORKFLOW_COMPLETED and act.duration_ms:
            workflow_durations.append(act.duration_ms)
            workflow_count += 1
        elif act.type == ActivityType.BATCH_COMPLETED and act.duration_ms:
            batch_durations.append(act.duration_ms)
            batch_count += 1

    busiest_hour = max(hour_counts.items(), key=lambda x: x[1])[0] if hour_counts else None

    avg_workflow_duration = (
        sum(workflow_durations) / len(workflow_durations) if workflow_durations else None
    )
    avg_batch_duration = (
        sum(batch_durations) / len(batch_durations) if batch_durations else None
    )

    return ActivityMetricsSummary(
        total_activities=stats.total_activities,
        total_workflows=workflow_count,
        total_batches=batch_count,
        error_count=stats.error_count,
        warning_count=stats.warning_count,
        success_rate=stats.success_rate,
        avg_workflow_duration_ms=avg_workflow_duration,
        avg_batch_duration_ms=avg_batch_duration,
        busiest_hour=busiest_hour,
        period_start=stats.period_start.isoformat(),
        period_end=stats.period_end.isoformat(),
    )


# Resolve forward refs in ActivityListResponse (declared in models.py with
# items: list["ActivityResponse"]). Pydantic v2 needs this after both modules
# are loaded — see #1144.
from fichero_server.models import ActivityListResponse  # noqa: E402

ActivityListResponse.model_rebuild(_types_namespace={"ActivityResponse": ActivityResponse})
