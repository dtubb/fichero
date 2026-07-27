"""
Activity Tracking System for Fichero Workflows.

Provides comprehensive activity logging and real-time streaming:
- Activity logging for workflow and batch events
- WebSocket streaming for real-time updates
- Query interface for historical activity
- Aggregated metrics and statistics
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections import deque
from datetime import datetime
from typing import Any, AsyncIterator, Optional

from fichero.workflows.activity_types import (
    Activity,
    ActivityFilter,
    ActivityLevel,
    ActivityStats,
    ActivityType,
)
from fichero.workflows.activity_store import ActivityStore

logger = logging.getLogger(__name__)

# Re-export all public names so existing imports continue to work
__all__ = [
    "Activity",
    "ActivityFilter",
    "ActivityLevel",
    "ActivityStats",
    "ActivityStore",
    "ActivityTracker",
    "ActivityType",
    "close_activity_tracker",
    "get_activity_tracker",
]


class ActivityTracker:
    """
    Central activity tracking service.

    Combines persistent storage with real-time streaming capabilities.
    """

    def __init__(self, db_path: str, max_recent: int = 1000):
        """
        Initialize activity tracker.

        Args:
            db_path: Path to DuckDB database
            max_recent: Maximum number of recent activities to keep in memory
        """
        self.store = ActivityStore(db_path)
        self._recent: deque[Activity] = deque(maxlen=max_recent)
        self._subscribers: dict[str, asyncio.Queue[Activity]] = {}
        self._running = False
        try:
            self._event_loop: asyncio.AbstractEventLoop | None = (
                asyncio.get_running_loop()
            )
        except RuntimeError:
            self._event_loop = None
        # Fire-and-forget DB saves scheduled by log() (see below) have no
        # ordering guarantee relative to a caller's immediate follow-up query
        # — a caller that needs durability before proceeding (tests asserting
        # on persisted activities, graceful shutdown) awaits
        # `wait_for_pending_saves()` instead of racing the background task.
        self._pending_save_tasks: set[asyncio.Task] = set()

    def log(
        self,
        type: ActivityType,
        message: str,
        level: ActivityLevel = ActivityLevel.INFO,
        workflow_id: Optional[str] = None,
        batch_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        node_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        duration_ms: Optional[float] = None,
        error: Optional[str] = None,
    ) -> Activity:
        """
        Log an activity event.

        Returns the created Activity object.
        """
        activity = Activity(
            id=str(uuid.uuid4()),
            type=type,
            level=level,
            timestamp=datetime.now(),
            message=message,
            workflow_id=workflow_id,
            batch_id=batch_id,
            thread_id=thread_id,
            node_id=node_id,
            metadata=metadata or {},
            duration_ms=duration_ms,
            error=error,
        )

        # Add to recent buffer
        self._recent.appendleft(activity)

        # Save to database (fire and forget). Tracked in _pending_save_tasks
        # so a caller that needs the write to have landed can await
        # wait_for_pending_saves() instead of assuming completion order.
        self._schedule_activity(activity)

        # Log to Python logger as well
        log_level = getattr(logging, level.value.upper(), logging.INFO)
        logger.log(log_level, f"[{type.value}] {message}")

        return activity

    def _schedule_activity(self, activity: Activity) -> None:
        """Schedule persistence and delivery on the tracker's event loop."""
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None

        if self._event_loop is None or self._event_loop.is_closed():
            self._event_loop = running_loop

        if self._event_loop is None:
            logger.warning(
                "Activity could not be persisted: no running event loop (%s)",
                activity.message,
            )
            return

        if self._event_loop is not running_loop:
            self._event_loop.call_soon_threadsafe(self._create_activity_tasks, activity)
            return

        self._create_activity_tasks(activity)

    def _create_activity_tasks(self, activity: Activity) -> None:
        """Create activity tasks while running on the tracker event loop."""
        save_task = asyncio.create_task(self._save_activity(activity))
        self._pending_save_tasks.add(save_task)
        save_task.add_done_callback(self._pending_save_tasks.discard)

        # Notify subscribers
        asyncio.create_task(self._notify_subscribers(activity))

    async def wait_for_pending_saves(self) -> None:
        """Wait for all in-flight fire-and-forget activity DB saves to land.

        `log()` schedules its DB write as a background task so callers are
        never blocked on activity-store I/O. That means there is no ordering
        guarantee that a just-logged activity is queryable yet. Call this
        when durability matters — before asserting on persisted activities,
        or before a graceful shutdown — to wait for every save scheduled so
        far to complete.
        """
        pending = list(self._pending_save_tasks)
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    async def _save_activity(self, activity: Activity) -> None:
        """Save activity to persistent storage."""
        try:
            logger.info(
                f"Saving activity to DB: {activity.type.value} - {activity.message[:50]}"
            )
            await self.store.save(activity)
            logger.info(f"Activity saved successfully: {activity.id}")
        except Exception as e:
            logger.error(f"Failed to save activity: {e}", exc_info=True)

    async def _notify_subscribers(self, activity: Activity) -> None:
        """Notify all subscribers of new activity."""
        for queue in self._subscribers.values():
            try:
                await queue.put(activity)
            except asyncio.QueueFull:
                # Drop oldest if queue is full
                try:
                    queue.get_nowait()
                    await queue.put(activity)
                except asyncio.QueueEmpty:
                    pass

    def subscribe(self, filter: Optional[ActivityFilter] = None) -> str:
        """
        Subscribe to activity stream.

        Returns subscription ID for use with unsubscribe and stream.
        """
        sub_id = str(uuid.uuid4())
        self._subscribers[sub_id] = asyncio.Queue(maxsize=100)
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Unsubscribe from activity stream."""
        if subscription_id in self._subscribers:
            del self._subscribers[subscription_id]

    async def stream(
        self,
        subscription_id: str,
        filter: Optional[ActivityFilter] = None,
    ) -> AsyncIterator[Activity]:
        """
        Stream activities for a subscription.

        Yields Activity objects as they occur.
        """
        if subscription_id not in self._subscribers:
            raise ValueError(f"Invalid subscription ID: {subscription_id}")

        queue = self._subscribers[subscription_id]

        try:
            while True:
                activity = await queue.get()

                # Apply filter if provided
                if filter:
                    if filter.types and activity.type not in filter.types:
                        continue
                    if filter.levels and activity.level not in filter.levels:
                        continue
                    if (
                        filter.workflow_id
                        and activity.workflow_id != filter.workflow_id
                    ):
                        continue
                    if filter.batch_id and activity.batch_id != filter.batch_id:
                        continue

                yield activity
        finally:
            self.unsubscribe(subscription_id)

    def get_recent(self, limit: int = 50) -> list[Activity]:
        """Get recent activities from memory buffer."""
        return list(self._recent)[:limit]

    async def query(self, filter: ActivityFilter) -> list[Activity]:
        """Query historical activities."""
        return await self.store.query(filter)

    async def get_stats(
        self,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> ActivityStats:
        """Get activity statistics."""
        return await self.store.get_stats(since, until)

    # Convenience methods for common activity types

    def workflow_started(
        self,
        workflow_id: str,
        thread_id: str,
        workflow_name: str,
        **metadata,
    ) -> Activity:
        """Log workflow started event."""
        return self.log(
            type=ActivityType.WORKFLOW_STARTED,
            message=f"Workflow '{workflow_name}' started",
            workflow_id=workflow_id,
            thread_id=thread_id,
            metadata={"workflow_name": workflow_name, **metadata},
        )

    def workflow_completed(
        self,
        workflow_id: str,
        thread_id: str,
        workflow_name: str,
        duration_ms: float,
        **metadata,
    ) -> Activity:
        """Log workflow completed event."""
        return self.log(
            type=ActivityType.WORKFLOW_COMPLETED,
            message=f"Workflow '{workflow_name}' completed in {duration_ms:.0f}ms",
            workflow_id=workflow_id,
            thread_id=thread_id,
            duration_ms=duration_ms,
            metadata={"workflow_name": workflow_name, **metadata},
        )

    def workflow_failed(
        self,
        workflow_id: str,
        thread_id: str,
        workflow_name: str,
        error: str,
        duration_ms: Optional[float] = None,
        **metadata,
    ) -> Activity:
        """Log workflow failed event."""
        return self.log(
            type=ActivityType.WORKFLOW_FAILED,
            level=ActivityLevel.ERROR,
            message=f"Workflow '{workflow_name}' failed: {error}",
            workflow_id=workflow_id,
            thread_id=thread_id,
            error=error,
            duration_ms=duration_ms,
            metadata={"workflow_name": workflow_name, **metadata},
        )

    def workflow_cancelled(
        self,
        workflow_id: str,
        thread_id: str,
        workflow_name: Optional[str] = None,
        duration_ms: Optional[float] = None,
        **metadata,
    ) -> Activity:
        """Log workflow cancelled event (#1127).

        Emitted when a user-initiated cancellation interrupts the
        astream_events loop in the runner. Partial results (artifacts
        already written, entities/claims already extracted) are
        intentionally NOT rolled back — the comparison loop can still
        inspect what got done before the cancel. metadata may carry
        `partial_results_preserved=True` for downstream consumers
        that want to surface that to the user.
        """
        return self.log(
            type=ActivityType.WORKFLOW_CANCELLED,
            level=ActivityLevel.WARNING,
            message=(
                f"Workflow '{workflow_name}' cancelled by user"
                if workflow_name
                else "Workflow cancelled by user"
            ),
            workflow_id=workflow_id,
            thread_id=thread_id,
            duration_ms=duration_ms,
            metadata={"workflow_name": workflow_name, **metadata},
        )

    def workflow_paused(
        self,
        workflow_id: str,
        thread_id: str,
        workflow_name: Optional[str] = None,
        duration_ms: Optional[float] = None,
        **metadata,
    ) -> Activity:
        """Log workflow paused event."""
        return self.log(
            type=ActivityType.WORKFLOW_PAUSED,
            level=ActivityLevel.WARNING,
            message=(
                f"Workflow '{workflow_name}' paused by user"
                if workflow_name
                else "Workflow paused by user"
            ),
            workflow_id=workflow_id,
            thread_id=thread_id,
            duration_ms=duration_ms,
            metadata={"workflow_name": workflow_name, **metadata},
        )

    def workflow_resumed(
        self,
        workflow_id: str,
        thread_id: str,
        workflow_name: Optional[str] = None,
        **metadata,
    ) -> Activity:
        """Log workflow resumed event."""
        return self.log(
            type=ActivityType.WORKFLOW_RESUMED,
            message=(
                f"Workflow '{workflow_name}' resumed"
                if workflow_name
                else "Workflow resumed"
            ),
            workflow_id=workflow_id,
            thread_id=thread_id,
            metadata={"workflow_name": workflow_name, **metadata},
        )

    def workflow_deleted(
        self,
        workflow_id: str,
        thread_id: str,
        workflow_name: Optional[str] = None,
        **metadata,
    ) -> Activity:
        """Log workflow run history deletion."""
        return self.log(
            type=ActivityType.WORKFLOW_DELETED,
            message=(
                f"Workflow run '{workflow_name}' deleted"
                if workflow_name
                else "Workflow run deleted"
            ),
            workflow_id=workflow_id,
            thread_id=thread_id,
            metadata={"workflow_name": workflow_name, **metadata},
        )

    def node_started(
        self,
        workflow_id: str,
        thread_id: str,
        node_id: str,
        node_name: str,
        **metadata,
    ) -> Activity:
        """Log node started event."""
        return self.log(
            type=ActivityType.NODE_STARTED,
            level=ActivityLevel.DEBUG,
            message=f"Node '{node_name}' started",
            workflow_id=workflow_id,
            thread_id=thread_id,
            node_id=node_id,
            metadata={"node_name": node_name, **metadata},
        )

    def node_completed(
        self,
        workflow_id: str,
        thread_id: str,
        node_id: str,
        node_name: str,
        duration_ms: float,
        **metadata,
    ) -> Activity:
        """Log node completed event."""
        return self.log(
            type=ActivityType.NODE_COMPLETED,
            level=ActivityLevel.DEBUG,
            message=f"Node '{node_name}' completed in {duration_ms:.0f}ms",
            workflow_id=workflow_id,
            thread_id=thread_id,
            node_id=node_id,
            duration_ms=duration_ms,
            metadata={"node_name": node_name, **metadata},
        )

    def node_failed(
        self,
        workflow_id: str,
        thread_id: str,
        node_id: str,
        node_name: str,
        error: str,
        **metadata,
    ) -> Activity:
        """Log node failed event."""
        return self.log(
            type=ActivityType.NODE_FAILED,
            level=ActivityLevel.ERROR,
            message=f"Node '{node_name}' failed: {error}",
            workflow_id=workflow_id,
            thread_id=thread_id,
            node_id=node_id,
            error=error,
            metadata={"node_name": node_name, **metadata},
        )

    def batch_started(
        self,
        batch_id: str,
        workflow_id: str,
        total_items: int,
        **metadata,
    ) -> Activity:
        """Log batch started event."""
        return self.log(
            type=ActivityType.BATCH_STARTED,
            message=f"Batch started with {total_items} items",
            batch_id=batch_id,
            workflow_id=workflow_id,
            metadata={"total_items": total_items, **metadata},
        )

    def batch_created(
        self,
        batch_id: str,
        workflow_id: str,
        total_items: int,
        **metadata,
    ) -> Activity:
        """Log batch created event."""
        return self.log(
            type=ActivityType.BATCH_CREATED,
            message=f"Batch created with {total_items} items",
            batch_id=batch_id,
            workflow_id=workflow_id,
            metadata={"total_items": total_items, **metadata},
        )

    def batch_completed(
        self,
        batch_id: str,
        workflow_id: str,
        total_items: int,
        completed_items: int,
        failed_items: int,
        duration_ms: float,
        **metadata,
    ) -> Activity:
        """Log batch completed event."""
        return self.log(
            type=ActivityType.BATCH_COMPLETED,
            message=f"Batch completed: {completed_items}/{total_items} successful, {failed_items} failed",
            batch_id=batch_id,
            workflow_id=workflow_id,
            duration_ms=duration_ms,
            metadata={
                "total_items": total_items,
                "completed_items": completed_items,
                "failed_items": failed_items,
                **metadata,
            },
        )

    def batch_failed(
        self,
        batch_id: str,
        workflow_id: str,
        total_items: int,
        failed_items: int,
        error: str,
        duration_ms: float | None = None,
        **metadata,
    ) -> Activity:
        """Log batch failed event."""
        return self.log(
            type=ActivityType.BATCH_FAILED,
            level=ActivityLevel.ERROR,
            message=f"Batch failed: {failed_items}/{total_items} failed",
            batch_id=batch_id,
            workflow_id=workflow_id,
            duration_ms=duration_ms,
            error=error,
            metadata={
                "total_items": total_items,
                "failed_items": failed_items,
                **metadata,
            },
        )

    def batch_paused(self, batch_id: str, workflow_id: str, **metadata) -> Activity:
        """Log batch paused event."""
        return self.log(
            type=ActivityType.BATCH_PAUSED,
            message="Batch paused",
            batch_id=batch_id,
            workflow_id=workflow_id,
            metadata=metadata,
        )

    def batch_resumed(self, batch_id: str, workflow_id: str, **metadata) -> Activity:
        """Log batch resumed event."""
        return self.log(
            type=ActivityType.BATCH_RESUMED,
            message="Batch resumed",
            batch_id=batch_id,
            workflow_id=workflow_id,
            metadata=metadata,
        )

    def batch_cancelled(self, batch_id: str, workflow_id: str, **metadata) -> Activity:
        """Log batch cancelled event."""
        return self.log(
            type=ActivityType.BATCH_CANCELLED,
            level=ActivityLevel.WARNING,
            message="Batch cancelled",
            batch_id=batch_id,
            workflow_id=workflow_id,
            metadata=metadata,
        )

    def batch_item_started(
        self,
        batch_id: str,
        thread_id: str,
        item_index: int,
        workflow_id: str | None = None,
        **metadata,
    ) -> Activity:
        """Log batch item started event."""
        return self.log(
            type=ActivityType.BATCH_ITEM_STARTED,
            level=ActivityLevel.DEBUG,
            message=f"Batch item {item_index} started",
            batch_id=batch_id,
            workflow_id=workflow_id,
            thread_id=thread_id,
            metadata={"item_index": item_index, **metadata},
        )

    def batch_item_completed(
        self,
        batch_id: str,
        thread_id: str,
        item_index: int,
        duration_ms: float,
        workflow_id: str | None = None,
        **metadata,
    ) -> Activity:
        """Log batch item completed event."""
        return self.log(
            type=ActivityType.BATCH_ITEM_COMPLETED,
            level=ActivityLevel.DEBUG,
            message=f"Batch item {item_index} completed",
            batch_id=batch_id,
            workflow_id=workflow_id,
            thread_id=thread_id,
            duration_ms=duration_ms,
            metadata={"item_index": item_index, **metadata},
        )

    def batch_item_failed(
        self,
        batch_id: str,
        thread_id: str,
        item_index: int,
        error: str,
        workflow_id: str | None = None,
        **metadata,
    ) -> Activity:
        """Log batch item failed event."""
        return self.log(
            type=ActivityType.BATCH_ITEM_FAILED,
            level=ActivityLevel.ERROR,
            message=f"Batch item {item_index} failed: {error}",
            batch_id=batch_id,
            workflow_id=workflow_id,
            thread_id=thread_id,
            error=error,
            metadata={"item_index": item_index, **metadata},
        )


# Per-library activity tracker instances
# Key: database path string, Value: ActivityTracker instance
_activity_trackers: dict[str, ActivityTracker] = {}
_tracker_lock = __import__("threading").Lock()


async def _recover_stale_runs_bg(tracker: "ActivityTracker", db_path: str) -> None:
    """Fire-and-forget coroutine: recover zombie runs for a newly-opened library.

    Called once per library when its ActivityTracker is first created (#1350).
    Any exception is caught and logged so it can never break startup or
    library-open.

    ``max_age_hours=0`` carries #2223 across from the deleted startup sweep
    (#3920): the tracker is created ONCE per library per process, so at this
    moment no run in THIS process can be in flight — every ``running`` row
    belongs to a process that is already gone, regardless of how recently it
    started. The default of 2 hours would silently skip a run that died five
    minutes ago, which is the exact bug #2223 fixed.
    """
    try:
        recovered = await tracker.store.recover_stale_runs(max_age_hours=0)
        if recovered:
            logger.info(
                "recover_stale_runs: recovered %d stale run(s) for library %s",
                recovered,
                db_path,
            )
    except Exception:
        logger.exception(
            "recover_stale_runs failed for %s (ignored — library open continues)",
            db_path,
        )


def get_activity_tracker(db_path: Optional[str] = None) -> ActivityTracker:
    """Get or create activity tracker for a library.

    Each library has its own ActivityTracker storing activities in that
    library's database. This ensures activity data is kept with the library.

    Args:
        db_path: Path to the library's database file. REQUIRED for proper
                 per-library tracking. If None, falls back to app database
                 (not recommended).

    Returns:
        ActivityTracker instance for the specified library
    """
    if db_path is None:
        # Fallback to app database - not ideal but maintains backward compatibility
        from fichero.db.app import get_db_path

        db_path = get_db_path()
        logger.warning(
            "get_activity_tracker() called without db_path - using app database. "
            "Activity data should be stored per-library."
        )

    # Ensure we're using the string path
    db_path = str(db_path)
    logger.info(f"get_activity_tracker called with db_path: {db_path}")

    with _tracker_lock:
        if db_path not in _activity_trackers:
            logger.info(f"Creating NEW ActivityTracker for: {db_path}")
            tracker = ActivityTracker(db_path)
            _activity_trackers[db_path] = tracker
            # Recover stale 'running' rows left by a previous crash/restart (#1350).
            # Fire-and-forget: wrap in try/except so a DB error never blocks
            # library-open or startup.
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                logger.debug(
                    "recover_stale_runs skipped for %s: no running event loop", db_path
                )
            except Exception:
                logger.exception(
                    "recover_stale_runs scheduling failed for %s (ignored)", db_path
                )
            else:
                loop.create_task(_recover_stale_runs_bg(tracker, db_path))
        else:
            logger.debug(f"Reusing existing ActivityTracker for: {db_path}")
        return _activity_trackers[db_path]


def close_activity_tracker(db_path: str) -> None:
    """Close and remove activity tracker for a library.

    Call when closing a library to clean up resources.
    """
    with _tracker_lock:
        if db_path in _activity_trackers:
            del _activity_trackers[db_path]
            logger.info(f"Closed ActivityTracker for: {db_path}")
