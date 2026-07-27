"""
Activity Tracking API Routes.

Endpoints for monitoring workflow and batch activity:
- Query historical activities
- Real-time activity streaming via SSE
- Activity statistics and metrics

NOTE: All activity data is stored per-library in the library's database file.
Routes require the X-Fichero-Library-Path header.
"""

import asyncio
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from fichero.api.library_header import require_library_path
from fichero.api.auth import action_context
from fichero.api.change_stream import ChangeEvent, _change_hub
from fichero.api.main import get_library_database, get_library_database_for_write
from fichero.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero.db import Database, db_manager
from fichero.workflows.activity import (
    Activity,
    ActivityFilter,
    ActivityLevel,
    ActivityStats,
    ActivityType,
    get_activity_tracker,
)
from fichero.models import ActivityListResponse

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

    until = datetime.now()
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


@router.websocket("/ws")
async def websocket_activity_stream(
    websocket: WebSocket,
    x_fichero_library_path: str = Depends(require_library_path),
):
    """
    WebSocket endpoint for real-time activity streaming.

    Clients can send filter updates and receive activity events.
    """
    # WebSockets do not run the HTTP auth middleware in TestClient in the same
    # shape as normal routes, so gate before attaching to a library stream.
    from fichero.security import authz

    try:
        authz.assert_can_read(
            getattr(websocket.state, "user", None),
            x_fichero_library_path,
        )
    except authz.AuthorizationError:
        await websocket.close(code=1008)
        return

    await websocket.accept()

    # Get database for library
    db = db_manager.get_database(x_fichero_library_path)
    tracker = get_activity_tracker(str(db.path))
    sub_id = tracker.subscribe()

    try:
        # Start streaming in background
        async def send_activities():
            async for activity in tracker.stream(sub_id):
                response = ActivityResponse.from_activity(activity)
                await websocket.send_json(response.model_dump())

        send_task = asyncio.create_task(send_activities())

        # Listen for client messages (filter updates, ping, etc.)
        while True:
            try:
                message = await websocket.receive_json()
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif message.get("type") == "filter":
                    # Client wants to update filter - for now just acknowledge
                    await websocket.send_json({"type": "filter_updated"})
            except WebSocketDisconnect:
                break

        send_task.cancel()

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        tracker.unsubscribe(sub_id)


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
    older_than = datetime.now() - timedelta(days=params.days)
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
# Enhanced Activity Stream Endpoints (Issue #425)
# =============================================================================


class ActivityFeedGroup(BaseModel):
    """Activity grouped by entity type and ID."""

    entity_type: str  # "workflow", "batch", "node", "system"
    entity_id: str | None
    entity_name: str | None
    count: int
    last_activity: str
    activities: list[ActivityResponse]


class ActivityFeedResponse(BaseModel):
    """Response for activity feed with grouping."""

    activities: list[ActivityResponse]
    groups: list[ActivityFeedGroup]
    total: int
    has_more: bool


class TrendPoint(BaseModel):
    """Single point in a trend series."""

    timestamp: str
    count: int
    error_count: int
    workflow_count: int
    batch_count: int


class ActivityTrendsResponse(BaseModel):
    """Time-based activity trends."""

    period: str  # "hourly", "daily", "weekly"
    points: list[TrendPoint]
    total_activities: int
    total_errors: int


class TopEntity(BaseModel):
    """Entity with activity metrics."""

    entity_type: str
    entity_id: str
    entity_name: str | None
    activity_count: int
    error_count: int
    last_activity: str
    success_rate: float


class TopEntitiesResponse(BaseModel):
    """Response for top entities by activity."""

    workflows: list[TopEntity]
    batches: list[TopEntity]
    time_range_hours: int


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
# Enhanced Feed Endpoint
# -----------------------------------------------------------------------------


@router.get("/feed", response_model=ActivityFeedResponse)
async def get_activity_feed(
    db: Database = Depends(get_library_database),
    entity_type: str | None = Query(
        None,
        description="Filter by entity type: workflow, batch, node, system",
    ),
    entity_id: str | None = Query(None, description="Filter by specific entity ID"),
    types: str | None = Query(None, description="Comma-separated activity types"),
    levels: str | None = Query(None, description="Comma-separated levels"),
    since: str | None = Query(None, description="ISO datetime string"),
    until: str | None = Query(None, description="ISO datetime string"),
    group_by_entity: bool = Query(
        True, description="Group results by entity in response"
    ),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> ActivityFeedResponse:
    """
    Get enriched activity feed with optional grouping.

    Supports filtering by entity type (workflow, batch, node, system)
    and grouping results for dashboard views.
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

    # Parse timestamps
    since_dt = None
    until_dt = None
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid 'since' datetime format"
            )
    if until:
        try:
            until_dt = datetime.fromisoformat(until.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=400, detail="Invalid 'until' datetime format"
            )

    # Build filter
    filter = ActivityFilter(
        types=type_list,
        levels=level_list,
        since=since_dt,
        until=until_dt,
        limit=limit + 1,  # Fetch one extra to check for more
        offset=offset,
    )

    # If entity type and ID specified, add to filter
    if entity_type == "workflow" and entity_id:
        filter.workflow_id = entity_id
    elif entity_type == "batch" and entity_id:
        filter.batch_id = entity_id

    activities = await tracker.query(filter)
    has_more = len(activities) > limit
    activities = activities[:limit]  # Trim the extra

    response_activities = [ActivityResponse.from_activity(a) for a in activities]

    # Build groups if requested
    groups = []
    if group_by_entity and activities:
        entity_groups: dict[str, list[ActivityResponse]] = {}

        for act in response_activities:
            # Determine entity type and ID
            if act.workflow_id:
                key = f"workflow:{act.workflow_id}"
            elif act.batch_id:
                key = f"batch:{act.batch_id}"
            elif act.node_id:
                key = f"node:{act.node_id}"
            else:
                key = "system:system"

            if key not in entity_groups:
                entity_groups[key] = []
            entity_groups[key].append(act)

        for key, acts in entity_groups.items():
            entity_type_str, entity_id_str = key.split(":", 1)
            entity_name = None

            # Try to get entity name from metadata
            if acts:
                metadata = acts[0].metadata
                if entity_type_str == "workflow":
                    entity_name = metadata.get("workflow_name")
                elif entity_type_str == "batch":
                    entity_name = metadata.get("batch_name")
                elif entity_type_str == "node":
                    entity_name = metadata.get("node_name")

            groups.append(
                ActivityFeedGroup(
                    entity_type=entity_type_str,
                    entity_id=entity_id_str if entity_id_str != "system" else None,
                    entity_name=entity_name,
                    count=len(acts),
                    last_activity=acts[0].timestamp,  # Already sorted by time desc
                    activities=acts[:10],  # Include up to 10 per group
                )
            )

        # Sort groups by last_activity
        groups.sort(key=lambda g: g.last_activity, reverse=True)

    return ActivityFeedResponse(
        activities=response_activities,
        groups=groups,
        total=len(response_activities),
        has_more=has_more,
    )


# -----------------------------------------------------------------------------
# Trends Endpoint
# -----------------------------------------------------------------------------


@router.get("/trends", response_model=ActivityTrendsResponse)
async def get_activity_trends(
    db: Database = Depends(get_library_database),
    period: str = Query("hourly", description="hourly, daily, or weekly"),
    hours: int = Query(24, ge=1, le=720),
) -> ActivityTrendsResponse:
    """
    Get time-based activity trends.

    Returns aggregated counts over time periods for visualization.
    """
    tracker = get_activity_tracker(str(db.path))

    until = datetime.now()
    since = until - timedelta(hours=hours)

    # Get all activities in range
    filter = ActivityFilter(since=since, until=until, limit=10000)
    activities = await tracker.query(filter)

    # Group by time buckets
    buckets: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "error_count": 0, "workflow_count": 0, "batch_count": 0}
    )

    for act in activities:
        ts = act.timestamp

        if period == "hourly":
            bucket_key = ts.strftime("%Y-%m-%dT%H:00:00")
        elif period == "daily":
            bucket_key = ts.strftime("%Y-%m-%d")
        else:  # weekly
            bucket_key = ts.strftime("%Y-%W")

        buckets[bucket_key]["count"] += 1
        if act.level == ActivityLevel.ERROR:
            buckets[bucket_key]["error_count"] += 1
        if act.type.value.startswith("workflow"):
            buckets[bucket_key]["workflow_count"] += 1
        if act.type.value.startswith("batch"):
            buckets[bucket_key]["batch_count"] += 1

    # Convert to sorted trend points
    sorted_buckets = sorted(buckets.items())
    points = [
        TrendPoint(
            timestamp=bucket,
            count=data["count"],
            error_count=data["error_count"],
            workflow_count=data["workflow_count"],
            batch_count=data["batch_count"],
        )
        for bucket, data in sorted_buckets
    ]

    total_errors = sum(p.error_count for p in points)

    return ActivityTrendsResponse(
        period=period,
        points=points,
        total_activities=len(activities),
        total_errors=total_errors,
    )


# -----------------------------------------------------------------------------
# Top Entities Endpoint
# -----------------------------------------------------------------------------


@router.get("/top", response_model=TopEntitiesResponse)
async def get_top_entities(
    db: Database = Depends(get_library_database),
    hours: int = Query(24, ge=1, le=720, description="Time range in hours"),
    limit: int = Query(10, ge=1, le=50, description="Number of top entities per type"),
) -> TopEntitiesResponse:
    """
    Get top active workflows and batches by activity count.

    Useful for identifying most active or problematic entities.
    """
    tracker = get_activity_tracker(str(db.path))

    until = datetime.now()
    since = until - timedelta(hours=hours)

    filter = ActivityFilter(since=since, until=until, limit=10000)
    activities = await tracker.query(filter)

    # Aggregate by entity
    workflow_stats: dict[str, dict] = {}
    batch_stats: dict[str, dict] = {}

    for act in activities:
        if act.workflow_id:
            if act.workflow_id not in workflow_stats:
                workflow_stats[act.workflow_id] = {
                    "count": 0,
                    "errors": 0,
                    "name": act.metadata.get("workflow_name", "Unknown"),
                    "last_activity": act.timestamp,
                    "completed": 0,
                    "failed": 0,
                }
            stats = workflow_stats[act.workflow_id]
            stats["count"] += 1
            if act.level == ActivityLevel.ERROR:
                stats["errors"] += 1
            if act.type == ActivityType.WORKFLOW_COMPLETED:
                stats["completed"] += 1
            if act.type == ActivityType.WORKFLOW_FAILED:
                stats["failed"] += 1
            if act.timestamp > stats["last_activity"]:
                stats["last_activity"] = act.timestamp

        if act.batch_id:
            if act.batch_id not in batch_stats:
                batch_stats[act.batch_id] = {
                    "count": 0,
                    "errors": 0,
                    "name": act.metadata.get("batch_name", "Unknown"),
                    "last_activity": act.timestamp,
                    "completed": 0,
                    "failed": 0,
                }
            stats = batch_stats[act.batch_id]
            stats["count"] += 1
            if act.level == ActivityLevel.ERROR:
                stats["errors"] += 1
            if act.type == ActivityType.BATCH_COMPLETED:
                stats["completed"] += 1
            if act.type == ActivityType.BATCH_FAILED:
                stats["failed"] += 1
            if act.timestamp > stats["last_activity"]:
                stats["last_activity"] = act.timestamp

    # Build top entities
    def calc_success_rate(completed: int, failed: int) -> float:
        total = completed + failed
        if total == 0:
            return 100.0
        return (completed / total) * 100

    top_workflows = [
        TopEntity(
            entity_type="workflow",
            entity_id=wid,
            entity_name=data["name"],
            activity_count=data["count"],
            error_count=data["errors"],
            last_activity=data["last_activity"].isoformat(),
            success_rate=calc_success_rate(data["completed"], data["failed"]),
        )
        for wid, data in sorted(
            workflow_stats.items(), key=lambda x: x[1]["count"], reverse=True
        )[:limit]
    ]

    top_batches = [
        TopEntity(
            entity_type="batch",
            entity_id=bid,
            entity_name=data["name"],
            activity_count=data["count"],
            error_count=data["errors"],
            last_activity=data["last_activity"].isoformat(),
            success_rate=calc_success_rate(data["completed"], data["failed"]),
        )
        for bid, data in sorted(
            batch_stats.items(), key=lambda x: x[1]["count"], reverse=True
        )[:limit]
    ]

    return TopEntitiesResponse(
        workflows=top_workflows,
        batches=top_batches,
        time_range_hours=hours,
    )


# /entity-types (a hardcoded 4-element literal served over HTTP) was deleted
# in the endpoint cleanup (2026-07-27) — a client-side constant, not an API.


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

    until = datetime.now()
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
        # Hour distribution
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
from fichero.models import ActivityListResponse  # noqa: E402

ActivityListResponse.model_rebuild(_types_namespace={"ActivityResponse": ActivityResponse})
