"""
Workflow Scheduler System.

Provides scheduling capabilities for automated workflow execution:
- Cron-based scheduling (daily, weekly, monthly patterns)
- Interval-based scheduling (every N minutes/hours)
- One-time scheduled execution
- Schedule management (create, pause, resume, delete)
- Integration with batch execution system
"""

import asyncio
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime
from fichero_server.core.timeutil import ensure_utc, utc_now
from enum import Enum
from typing import Any, Optional


# apscheduler is imported lazily inside the methods that use it (constructors,
# trigger factories, JobLookupError catches). Keeping it off module scope defers
# ~77ms of import cost off the engine API bind path — the scheduler is only ever
# instantiated at lifespan startup via init_scheduler(), never at import.
from fichero_server.execution.batch import BatchManager
from fichero_server.workflows.workflow_store import WorkflowStore

logger = logging.getLogger(__name__)
MAX_SCHEDULE_CACHE_SIZE = 512


# The scheduler was already tz-correct before #4347; both local helpers now
# delegate to the one canonical implementation in core.timeutil so there is a
# single definition of "now" and of "a naive value means UTC".
_utcnow = utc_now
_ensure_aware_utc = ensure_utc


class ScheduleType(str, Enum):
    """Type of schedule trigger."""

    CRON = "cron"  # Cron expression (e.g., "0 9 * * 1" for every Monday at 9am)
    INTERVAL = "interval"  # Every N seconds/minutes/hours
    ONCE = "once"  # One-time execution at a specific datetime


class ScheduleStatus(str, Enum):
    """Status of a schedule."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"  # For one-time schedules that have run
    ERROR = "error"


@dataclass
class ScheduleConfig:
    """Configuration for a schedule."""

    schedule_type: ScheduleType
    # For cron schedules
    cron_expression: Optional[str] = None
    # For interval schedules
    interval_seconds: Optional[int] = None
    # For one-time schedules
    run_at: Optional[datetime] = None
    # Common options
    timezone: str = "UTC"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    max_runs: Optional[int] = None  # Maximum number of executions


@dataclass
class Schedule:
    """Represents a scheduled workflow execution."""

    schedule_id: str
    name: str
    workflow_id: str
    config: ScheduleConfig
    status: ScheduleStatus
    inputs: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    run_count: int = 0
    error_message: Optional[str] = None
    # Batch execution options
    use_batch: bool = False
    batch_items: list[dict[str, Any]] = field(default_factory=list)
    max_concurrent: int = 5


@dataclass
class ScheduleRun:
    """Record of a schedule execution."""

    run_id: str
    schedule_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "running"  # running, completed, failed
    batch_id: Optional[str] = None
    error: Optional[str] = None


class WorkflowScheduler:
    """
    Manages scheduled workflow executions.

    Uses APScheduler for robust scheduling with:
    - Async execution
    - Persistent job tracking in DuckDB
    - Integration with BatchManager for batch executions
    """

    def __init__(
        self,
        db_path: str,
        workflow_store: WorkflowStore,
        batch_manager: Optional[BatchManager] = None,
    ):
        """Initialize the scheduler.

        Args:
            db_path: Path to DuckDB database
            workflow_store: WorkflowStore for loading workflows
            batch_manager: Optional BatchManager for batch executions
        """
        self.db_path = db_path
        self.workflow_store = workflow_store
        self.batch_manager = batch_manager or BatchManager(db_path)

        # Initialize APScheduler (imported here to keep it off the bind path)
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.jobstores.memory import MemoryJobStore
        from apscheduler.executors.asyncio import AsyncIOExecutor

        jobstores = {"default": MemoryJobStore()}
        executors = {"default": AsyncIOExecutor()}
        job_defaults = {"coalesce": True, "max_instances": 1}

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
        )

        self._schedules: OrderedDict[str, Schedule] = OrderedDict()
        self._bg_tasks: set[asyncio.Task] = set()
        self.db  # noqa: B018 -- the library opens at the making, as before; `db` is looked up on each use

    @property
    def db(self) -> Any:
        """The library's managed Database, looked up on each use (#6238): this outlives a close and reopen of the
        library, and the Database it was built with is closed for good after it."""
        from fichero_server.db.manager import database_for_file

        return database_for_file(self.db_path)

    def _remember_schedule(self, schedule: Schedule) -> None:
        self._schedules[schedule.schedule_id] = schedule
        self._schedules.move_to_end(schedule.schedule_id)
        while len(self._schedules) > MAX_SCHEDULE_CACHE_SIZE:
            self._schedules.popitem(last=False)

    def _track_background_task(self, task: Any) -> Any:
        """Keep a strong reference to background work until it ends (#2133): an asyncio task, or
        the future of work on the engine's background loop."""
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    async def start(self) -> None:
        """Start the scheduler and load existing schedules."""
        # Load schedules from database
        await self._load_schedules()

        # Start APScheduler
        self._scheduler.start()
        logger.info("Workflow scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._scheduler.shutdown(wait=True)
        logger.info("Workflow scheduler stopped")

    async def _load_schedules(self) -> None:
        """Load active schedules from database and register with APScheduler."""

        from fichero_server.models.schedules import ScheduleRecord

        def _load():
            return self.db.query(ScheduleRecord, status=ScheduleStatus.ACTIVE.value)

        rows = await asyncio.to_thread(_load)

        for row in rows:
            schedule = _schedule_of(row)
            self._remember_schedule(schedule)
            self._register_job(schedule)

        logger.info(f"Loaded {len(rows)} active schedules")

    async def create_schedule(
        self,
        name: str,
        workflow_id: str,
        config: ScheduleConfig,
        inputs: Optional[dict[str, Any]] = None,
        use_batch: bool = False,
        batch_items: Optional[list[dict[str, Any]]] = None,
        max_concurrent: int = 5,
    ) -> Schedule:
        """Create a new schedule.

        Args:
            name: Display name for the schedule
            workflow_id: ID of workflow to execute
            config: Schedule configuration (cron, interval, or once)
            inputs: Workflow inputs (for single execution)
            use_batch: Whether to use batch execution
            batch_items: Items for batch execution
            max_concurrent: Max concurrent batch items

        Returns:
            Created Schedule object
        """
        # Validate workflow exists
        workflow = self.workflow_store.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        schedule_id = str(uuid.uuid4())
        now = _utcnow()

        schedule = Schedule(
            schedule_id=schedule_id,
            name=name,
            workflow_id=workflow_id,
            config=config,
            status=ScheduleStatus.ACTIVE,
            inputs=inputs or {},
            created_at=now,
            updated_at=now,
            use_batch=use_batch,
            batch_items=batch_items or [],
            max_concurrent=max_concurrent,
        )

        # Calculate next run time
        trigger = self._create_trigger(config)
        next_run = trigger.get_next_fire_time(None, now)
        schedule.next_run_at = next_run

        # Save to database
        await self._save_schedule(schedule)

        # Register with APScheduler
        self._register_job(schedule)

        self._remember_schedule(schedule)
        logger.info(f"Created schedule {schedule_id}: {name}")

        return schedule

    def _create_trigger(self, config: ScheduleConfig):
        """Create APScheduler trigger from config."""
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
        from apscheduler.triggers.date import DateTrigger

        if config.schedule_type == ScheduleType.CRON:
            if not config.cron_expression:
                raise ValueError("Cron expression required for cron schedule")
            return CronTrigger.from_crontab(
                config.cron_expression,
                timezone=config.timezone,
            )
        elif config.schedule_type == ScheduleType.INTERVAL:
            if not config.interval_seconds:
                raise ValueError("Interval seconds required for interval schedule")
            return IntervalTrigger(
                seconds=config.interval_seconds,
                timezone=config.timezone,
                start_date=_ensure_aware_utc(config.start_date),
                end_date=_ensure_aware_utc(config.end_date),
            )
        elif config.schedule_type == ScheduleType.ONCE:
            if not config.run_at:
                raise ValueError("Run datetime required for one-time schedule")
            return DateTrigger(
                run_date=_ensure_aware_utc(config.run_at),
                timezone=config.timezone,
            )
        else:
            raise ValueError(f"Unknown schedule type: {config.schedule_type}")

    def _register_job(self, schedule: Schedule) -> None:
        """Register schedule with APScheduler."""
        trigger = self._create_trigger(schedule.config)

        self._scheduler.add_job(
            self._execute_schedule,
            trigger=trigger,
            id=schedule.schedule_id,
            args=[schedule.schedule_id],
            name=schedule.name,
            replace_existing=True,
        )

        logger.debug(f"Registered job for schedule {schedule.schedule_id}")

    async def _execute_schedule(self, schedule_id: str) -> None:
        """Execute a scheduled workflow.

        This is called by APScheduler when a schedule fires.
        """
        schedule = self._schedules.get(schedule_id)
        if not schedule:
            schedule = await self.get_schedule(schedule_id)
            if not schedule:
                logger.error(f"Schedule {schedule_id} not found")
                return

        if schedule.status != ScheduleStatus.ACTIVE:
            logger.info(f"Skipping inactive schedule {schedule_id}")
            return

        # Check max runs
        if schedule.config.max_runs and schedule.run_count >= schedule.config.max_runs:
            logger.info(
                f"Schedule {schedule_id} reached max runs ({schedule.config.max_runs})"
            )
            schedule.status = ScheduleStatus.COMPLETED
            await self._save_schedule(schedule)
            return

        # Create run record
        run = ScheduleRun(
            run_id=str(uuid.uuid4()),
            schedule_id=schedule_id,
            started_at=_utcnow(),
        )
        await self._save_run(run)

        try:
            if schedule.use_batch and schedule.batch_items:
                # Batch execution
                batch = await self.batch_manager.create_batch(
                    workflow_id=schedule.workflow_id,
                    items_inputs=schedule.batch_items,
                    max_concurrent=schedule.max_concurrent,
                )
                run.batch_id = batch.batch_id

                # Execute batch (fire and forget for scheduler)
                self._track_background_task(
                    asyncio.create_task(self._run_batch(batch.batch_id, run))
                )
            else:
                # Single workflow execution
                await self._run_single(schedule, run)

            # Update schedule stats
            schedule.last_run_at = run.started_at
            schedule.run_count += 1

            # Update next run time
            job = self._scheduler.get_job(schedule_id)
            if job:
                schedule.next_run_at = getattr(job, "next_run_time", None)

            # Mark one-time schedules as completed
            if schedule.config.schedule_type == ScheduleType.ONCE:
                schedule.status = ScheduleStatus.COMPLETED

            schedule.updated_at = _utcnow()
            await self._save_schedule(schedule)

        except Exception as e:
            logger.exception(f"Schedule {schedule_id} execution failed: {e}")
            run.status = "failed"
            run.error = str(e)
            run.completed_at = _utcnow()
            await self._save_run(run)

            schedule.error_message = str(e)
            schedule.updated_at = _utcnow()
            await self._save_schedule(schedule)

    async def _run_single(self, schedule: Schedule, run: ScheduleRun) -> None:
        """Run the workflow once, as a run of the one runner (#5372, `activity.run.scheduled-runs-
        execute`): the same path as a run started by hand. Its thread id is this schedule run's id."""
        from pathlib import Path

        from fichero_server.db.manager import db_manager
        from fichero_server.execution.runner import run_and_wait

        workflow = self.workflow_store.get(schedule.workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {schedule.workflow_id} not found")

        library = db_manager.get_database(str(Path(self.db_path).parent))
        status, error = await run_and_wait(library, workflow, schedule.inputs, thread_id=run.run_id,
                                           started_by="schedule")

        # Update run record
        run.status = "completed" if status == "completed" else "failed"
        run.error = error
        run.completed_at = _utcnow()
        await self._save_run(run)

    async def _run_batch(self, batch_id: str, run: ScheduleRun) -> None:
        """Run a batch execution."""
        try:
            async for event in self.batch_manager.execute_batch(
                batch_id, self.workflow_store
            ):
                # Log progress
                if event.progress:
                    logger.debug(
                        f"Batch {batch_id} progress: "
                        f"{event.progress.completed_items}/{event.progress.total_items}"
                    )

            # Batch completed
            run.status = "completed"
            run.completed_at = _utcnow()
            await self._save_run(run)

        except Exception as e:
            logger.exception(f"Batch {batch_id} failed: {e}")
            run.status = "failed"
            run.error = str(e)
            run.completed_at = _utcnow()
            await self._save_run(run)

    async def _save_schedule(self, schedule: Schedule) -> None:
        """Save schedule to database."""

        def _save():
            self.db.save(_record_of(schedule))

        await asyncio.to_thread(_save)

    async def _save_run(self, run: ScheduleRun) -> None:
        """Save schedule run to database."""

        from fichero_server.models.schedules import ScheduleRunRecord

        # One row, one save: a run is saved as it starts and again as it ends, never in bulk, so the plain-INSERT
        # path (`save_many(new=True)`, duckdb#26830) has nothing to save here.
        def _save():
            self.db.save(ScheduleRunRecord(
                id=run.run_id, schedule_id=run.schedule_id, started_at=run.started_at, completed_at=run.completed_at,
                status=run.status, batch_id=run.batch_id, error=run.error))

        await asyncio.to_thread(_save)

    async def get_schedule(self, schedule_id: str) -> Optional[Schedule]:
        """Get schedule by ID."""
        if schedule_id in self._schedules:
            self._schedules.move_to_end(schedule_id)
            return self._schedules[schedule_id]

        from fichero_server.models.schedules import ScheduleRecord

        record = await asyncio.to_thread(self.db.get, ScheduleRecord, schedule_id)
        if record is None:
            return None
        schedule = _schedule_of(record)
        self._remember_schedule(schedule)
        return schedule

    async def list_schedules(
        self,
        status: Optional[ScheduleStatus] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Schedule]:
        """List schedules with optional filtering."""

        from fichero_server.models.schedules import ScheduleRecord

        def _list():
            filters = {}
            if status:
                filters["status"] = status.value
            if workflow_id:
                filters["workflow_id"] = workflow_id
            # ponytail: sorted and paged here (`Database.query` filters by equality only); a library holds a handful
            # of schedules. Push the order into SQL if that ever changes.
            records = self.db.query(ScheduleRecord, **filters)
            records.sort(key=lambda r: ensure_utc(r.created_at), reverse=True)
            return records[offset:offset + limit]

        rows = await asyncio.to_thread(_list)
        return [_schedule_of(row) for row in rows]

    async def pause_schedule(self, schedule_id: str) -> Schedule:
        """Pause a schedule."""
        schedule = await self.get_schedule(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")

        if schedule.status != ScheduleStatus.ACTIVE:
            raise ValueError(f"Cannot pause schedule with status {schedule.status}")

        # Pause in APScheduler
        self._scheduler.pause_job(schedule_id)

        # Update status
        schedule.status = ScheduleStatus.PAUSED
        schedule.updated_at = _utcnow()
        await self._save_schedule(schedule)

        logger.info(f"Paused schedule {schedule_id}")
        return schedule

    async def resume_schedule(self, schedule_id: str) -> Schedule:
        """Resume a paused schedule."""
        schedule = await self.get_schedule(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")

        if schedule.status != ScheduleStatus.PAUSED:
            raise ValueError(f"Cannot resume schedule with status {schedule.status}")

        # Resume in APScheduler
        self._scheduler.resume_job(schedule_id)

        # Update status
        schedule.status = ScheduleStatus.ACTIVE
        schedule.updated_at = _utcnow()

        # Update next run time
        job = self._scheduler.get_job(schedule_id)
        if job:
            schedule.next_run_at = getattr(job, "next_run_time", None)

        await self._save_schedule(schedule)

        logger.info(f"Resumed schedule {schedule_id}")
        return schedule

    async def update_schedule(self, schedule: Schedule) -> Schedule:
        """Update an existing schedule.

        Args:
            schedule: Schedule object with updated fields

        Returns:
            Updated Schedule object
        """
        from apscheduler.jobstores.base import JobLookupError  # lazy: keep apscheduler off bind path
        # Verify schedule exists
        existing = await self.get_schedule(schedule.schedule_id)
        if not existing:
            raise ValueError(f"Schedule {schedule.schedule_id} not found")

        # If workflow_id changed, validate new workflow exists
        if schedule.workflow_id != existing.workflow_id:
            workflow = self.workflow_store.get(schedule.workflow_id)
            if not workflow:
                raise ValueError(f"Workflow {schedule.workflow_id} not found")

        # If schedule config changed and schedule is active, re-register job
        config_changed = (
            schedule.config.schedule_type != existing.config.schedule_type
            or schedule.config.cron_expression != existing.config.cron_expression
            or schedule.config.interval_seconds != existing.config.interval_seconds
            or schedule.config.run_at != existing.config.run_at
        )

        if config_changed and schedule.status == ScheduleStatus.ACTIVE:
            # Remove old job
            try:
                self._scheduler.remove_job(schedule.schedule_id)
            except JobLookupError:
                pass  # Job not registered yet — re-register below. Any OTHER
                # scheduler error must surface, not be silently swallowed (#2507).

            # Register new job
            self._register_job(schedule)

            # Update next run time
            job = self._scheduler.get_job(schedule.schedule_id)
            if job:
                schedule.next_run_at = getattr(job, "next_run_time", None)

        # Save to database
        await self._save_schedule(schedule)

        # Update cache
        self._remember_schedule(schedule)

        logger.info(f"Updated schedule {schedule.schedule_id}")
        return schedule

    async def delete_schedule(self, schedule_id: str) -> None:
        """Delete a schedule."""
        from apscheduler.jobstores.base import JobLookupError  # lazy: keep apscheduler off bind path
        # Remove from APScheduler
        try:
            self._scheduler.remove_job(schedule_id)
        except JobLookupError:
            pass  # Job might not exist. Any OTHER scheduler error must surface,
            # not be silently swallowed (#2507).

        # Remove from database
        from fichero_server.models.schedules import ScheduleRecord, ScheduleRunRecord

        def _delete():
            db = self.db  # once: a close mid-block must not open a second Database outside the transaction (#6238)
            with db.transaction():  # the schedule and its runs go together, or not at all
                for run in db.query(ScheduleRunRecord, schedule_id=schedule_id):
                    db.delete(run)
                record = db.get(ScheduleRecord, schedule_id)
                if record is not None:
                    db.delete(record)

        await asyncio.to_thread(_delete)

        # Remove from cache
        if schedule_id in self._schedules:
            del self._schedules[schedule_id]

        logger.info(f"Deleted schedule {schedule_id}")

    async def get_schedule_runs(
        self,
        schedule_id: str,
        limit: int = 50,
    ) -> list[ScheduleRun]:
        """Get run history for a schedule."""

        from fichero_server.models.schedules import ScheduleRunRecord

        def _get_runs():
            # ponytail: newest first, sorted here (`Database.query` filters by equality only); a schedule's history is
            # small. Push the order into SQL if that ever changes.
            records = self.db.query(ScheduleRunRecord, schedule_id=schedule_id)
            records.sort(key=lambda r: ensure_utc(r.started_at), reverse=True)
            return records[:limit]

        rows = await asyncio.to_thread(_get_runs)
        return [
            ScheduleRun(
                run_id=row.id,
                schedule_id=row.schedule_id,
                started_at=ensure_utc(row.started_at),
                completed_at=ensure_utc(row.completed_at),
                status=row.status,
                batch_id=row.batch_id,
                error=row.error,
            )
            for row in rows
        ]

    async def trigger_now(self, schedule_id: str) -> ScheduleRun:
        """Manually trigger a schedule to run immediately."""
        schedule = await self.get_schedule(schedule_id)
        if not schedule:
            raise ValueError(f"Schedule {schedule_id} not found")

        # Create and execute a run
        run = ScheduleRun(
            run_id=str(uuid.uuid4()),
            schedule_id=schedule_id,
            started_at=_utcnow(),
        )
        await self._save_run(run)

        # On the engine's background loop: off the API's loop, and not ended with this request.
        from fichero_server.execution.runner import on_background_loop

        self._track_background_task(on_background_loop(self._execute_manual_run(schedule, run)))

        return run

    async def _execute_manual_run(self, schedule: Schedule, run: ScheduleRun) -> None:
        """Execute a manually triggered run."""
        try:
            if schedule.use_batch and schedule.batch_items:
                batch = await self.batch_manager.create_batch(
                    workflow_id=schedule.workflow_id,
                    items_inputs=schedule.batch_items,
                    max_concurrent=schedule.max_concurrent,
                )
                run.batch_id = batch.batch_id
                await self._run_batch(batch.batch_id, run)
            else:
                await self._run_single(schedule, run)

            # Update schedule stats (but not next_run_at for manual triggers)
            schedule.last_run_at = run.started_at
            schedule.run_count += 1
            schedule.updated_at = _utcnow()
            await self._save_schedule(schedule)

        except Exception as e:
            logger.exception(f"Manual run for {schedule.schedule_id} failed: {e}")
            run.status = "failed"
            run.error = str(e)
            run.completed_at = _utcnow()
            await self._save_run(run)


def _record_of(schedule: Schedule) -> Any:
    """A schedule as the library keeps it (#5645)."""
    from fichero_server.models.schedules import ScheduleRecord

    config = schedule.config
    return ScheduleRecord(
        id=schedule.schedule_id, name=schedule.name, workflow_id=schedule.workflow_id,
        schedule_type=config.schedule_type.value, cron_expression=config.cron_expression,
        interval_seconds=config.interval_seconds, run_at=config.run_at, timezone=config.timezone,
        start_date=config.start_date, end_date=config.end_date, max_runs=config.max_runs,
        inputs=dict(schedule.inputs), status=schedule.status.value, use_batch=schedule.use_batch,
        batch_items=list(schedule.batch_items), max_concurrent=schedule.max_concurrent,
        created_at=schedule.created_at, updated_at=schedule.updated_at, last_run_at=schedule.last_run_at,
        next_run_at=schedule.next_run_at, run_count=schedule.run_count, error_message=schedule.error_message)


def _schedule_of(record: Any) -> Schedule:
    """A kept schedule as the scheduler works with it, field by field; every time a UTC instant (#5645: the old store
    gave the start and end dates back naive)."""
    return Schedule(
        schedule_id=record.id,
        name=record.name,
        workflow_id=record.workflow_id,
        config=ScheduleConfig(
            schedule_type=ScheduleType(record.schedule_type),
            cron_expression=record.cron_expression,
            interval_seconds=record.interval_seconds,
            run_at=ensure_utc(record.run_at),
            timezone=record.timezone or "UTC",
            start_date=ensure_utc(record.start_date),
            end_date=ensure_utc(record.end_date),
            max_runs=record.max_runs,
        ),
        inputs=dict(record.inputs or {}),
        status=ScheduleStatus(record.status),
        use_batch=record.use_batch,
        batch_items=list(record.batch_items or []),
        max_concurrent=record.max_concurrent,
        created_at=ensure_utc(record.created_at),
        updated_at=ensure_utc(record.updated_at),
        last_run_at=ensure_utc(record.last_run_at),
        next_run_at=ensure_utc(record.next_run_at),
        run_count=record.run_count,
        error_message=record.error_message,
    )


# Global scheduler instance
_scheduler: Optional[WorkflowScheduler] = None


def get_scheduler() -> Optional[WorkflowScheduler]:
    """Get the global scheduler instance."""
    return _scheduler


async def init_scheduler(
    db_path: str,
    workflow_store: WorkflowStore,
    batch_manager: Optional[BatchManager] = None,
) -> WorkflowScheduler:
    """Initialize and start the global scheduler."""
    global _scheduler
    _scheduler = WorkflowScheduler(db_path, workflow_store, batch_manager)
    await _scheduler.start()
    return _scheduler


async def shutdown_scheduler() -> None:
    """Shutdown the global scheduler."""
    global _scheduler
    if _scheduler:
        await _scheduler.stop()
        _scheduler = None
