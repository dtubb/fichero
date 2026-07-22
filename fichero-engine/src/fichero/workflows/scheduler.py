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
import json
import logging
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import duckdb

# apscheduler is imported lazily inside the methods that use it (constructors,
# trigger factories, JobLookupError catches). Keeping it off module scope defers
# ~77ms of import cost off the engine API bind path — the scheduler is only ever
# instantiated at lifespan startup via init_scheduler(), never at import.
from fichero.workflows.batch import BatchManager
from fichero.workflows.workflow_store import WorkflowStore

logger = logging.getLogger(__name__)
MAX_SCHEDULE_CACHE_SIZE = 512


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
        self._init_database()

    def _remember_schedule(self, schedule: Schedule) -> None:
        self._schedules[schedule.schedule_id] = schedule
        self._schedules.move_to_end(schedule.schedule_id)
        while len(self._schedules) > MAX_SCHEDULE_CACHE_SIZE:
            self._schedules.popitem(last=False)

    def _track_background_task(self, task: asyncio.Task) -> asyncio.Task:
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    def _init_database(self) -> None:
        """Initialize database tables for schedule tracking."""
        # ponytail: not a managed shared conn (#2508). Every method here opens a
        # FRESH ``conn = duckdb.connect(self.db_path)`` per operation and closes
        # it — a connection-per-operation pattern, not the package's managed
        # Database connection. Database._lock and the locked execute() helpers do
        # not apply. Folding the scheduler onto the shared Database is a separate
        # architectural call (lead review).
        conn = duckdb.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schedules (
                    schedule_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    schedule_type TEXT NOT NULL,
                    cron_expression TEXT,
                    interval_seconds INTEGER,
                    run_at TIMESTAMP,
                    timezone TEXT DEFAULT 'UTC',
                    start_date TIMESTAMP,
                    end_date TIMESTAMP,
                    max_runs INTEGER,
                    inputs JSON DEFAULT '{}',
                    status TEXT NOT NULL,
                    use_batch BOOLEAN DEFAULT FALSE,
                    batch_items JSON DEFAULT '[]',
                    max_concurrent INTEGER DEFAULT 5,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    last_run_at TIMESTAMP,
                    next_run_at TIMESTAMP,
                    run_count INTEGER DEFAULT 0,
                    error_message TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS schedule_runs (
                    run_id TEXT PRIMARY KEY,
                    schedule_id TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL,
                    completed_at TIMESTAMP,
                    status TEXT NOT NULL,
                    batch_id TEXT,
                    error TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_schedule_runs_schedule
                ON schedule_runs(schedule_id)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_schedules_status
                ON schedules(status)
            """)
        finally:
            conn.close()

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

        def _load():
            conn = duckdb.connect(self.db_path)
            try:
                results = conn.execute("""
                    SELECT * FROM schedules WHERE status = 'active'
                """).fetchall()
                return results
            finally:
                conn.close()

        rows = await asyncio.to_thread(_load)

        for row in rows:
            schedule = self._row_to_schedule(row)
            self._remember_schedule(schedule)
            self._register_job(schedule)

        logger.info(f"Loaded {len(rows)} active schedules")

    def _row_to_schedule(self, row) -> Schedule:
        """Convert database row to Schedule object."""

        return Schedule(
            schedule_id=row[0],
            name=row[1],
            workflow_id=row[2],
            config=ScheduleConfig(
                schedule_type=ScheduleType(row[3]),
                cron_expression=row[4],
                interval_seconds=row[5],
                run_at=row[6],
                timezone=row[7] or "UTC",
                start_date=row[8],
                end_date=row[9],
                max_runs=row[10],
            ),
            inputs=json.loads(row[11]) if row[11] else {},
            status=ScheduleStatus(row[12]),
            use_batch=row[13],
            batch_items=json.loads(row[14]) if row[14] else [],
            max_concurrent=row[15] or 5,
            created_at=row[16],
            updated_at=row[17],
            last_run_at=row[18],
            next_run_at=row[19],
            run_count=row[20] or 0,
            error_message=row[21],
        )

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
        """Run a single workflow execution."""
        from fichero.workflows.builder import execute_workflow

        workflow = self.workflow_store.get(schedule.workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {schedule.workflow_id} not found")

        # Execute workflow
        result = await execute_workflow(
            workflow=workflow,
            inputs=schedule.inputs,
        )

        # Update run record
        run.status = "completed" if not result.get("error") else "failed"
        run.error = result.get("error")
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

            conn = duckdb.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO schedules (
                        schedule_id, name, workflow_id, schedule_type,
                        cron_expression, interval_seconds, run_at, timezone,
                        start_date, end_date, max_runs, inputs, status,
                        use_batch, batch_items, max_concurrent,
                        created_at, updated_at, last_run_at, next_run_at,
                        run_count, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        schedule.schedule_id,
                        schedule.name,
                        schedule.workflow_id,
                        schedule.config.schedule_type.value,
                        schedule.config.cron_expression,
                        schedule.config.interval_seconds,
                        schedule.config.run_at,
                        schedule.config.timezone,
                        schedule.config.start_date,
                        schedule.config.end_date,
                        schedule.config.max_runs,
                        json.dumps(schedule.inputs),
                        schedule.status.value,
                        schedule.use_batch,
                        json.dumps(schedule.batch_items),
                        schedule.max_concurrent,
                        schedule.created_at,
                        schedule.updated_at,
                        schedule.last_run_at,
                        schedule.next_run_at,
                        schedule.run_count,
                        schedule.error_message,
                    ],
                )
            finally:
                conn.close()

        await asyncio.to_thread(_save)

    async def _save_run(self, run: ScheduleRun) -> None:
        """Save schedule run to database."""

        def _save():
            conn = duckdb.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO schedule_runs (
                        run_id, schedule_id, started_at, completed_at,
                        status, batch_id, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        run.run_id,
                        run.schedule_id,
                        run.started_at,
                        run.completed_at,
                        run.status,
                        run.batch_id,
                        run.error,
                    ],
                )
            finally:
                conn.close()

        await asyncio.to_thread(_save)

    async def get_schedule(self, schedule_id: str) -> Optional[Schedule]:
        """Get schedule by ID."""
        if schedule_id in self._schedules:
            self._schedules.move_to_end(schedule_id)
            return self._schedules[schedule_id]

        def _load():
            conn = duckdb.connect(self.db_path)
            try:
                result = conn.execute(
                    "SELECT * FROM schedules WHERE schedule_id = ?", [schedule_id]
                ).fetchone()
                return result
            finally:
                conn.close()

        row = await asyncio.to_thread(_load)
        if row:
            schedule = self._row_to_schedule(row)
            self._remember_schedule(schedule)
            return schedule
        return None

    async def list_schedules(
        self,
        status: Optional[ScheduleStatus] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Schedule]:
        """List schedules with optional filtering."""

        def _list():
            conn = duckdb.connect(self.db_path)
            try:
                query = "SELECT * FROM schedules WHERE 1=1"
                params = []

                if status:
                    query += " AND status = ?"
                    params.append(status.value)
                if workflow_id:
                    query += " AND workflow_id = ?"
                    params.append(workflow_id)

                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                results = conn.execute(query, params).fetchall()
                return results
            finally:
                conn.close()

        rows = await asyncio.to_thread(_list)
        return [self._row_to_schedule(row) for row in rows]

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
        # Remove from APScheduler
        try:
            self._scheduler.remove_job(schedule_id)
        except JobLookupError:
            pass  # Job might not exist. Any OTHER scheduler error must surface,
            # not be silently swallowed (#2507).

        # Remove from database
        def _delete():
            conn = duckdb.connect(self.db_path)
            try:
                conn.execute(
                    "DELETE FROM schedule_runs WHERE schedule_id = ?", [schedule_id]
                )
                conn.execute(
                    "DELETE FROM schedules WHERE schedule_id = ?", [schedule_id]
                )
            finally:
                conn.close()

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

        def _get_runs():
            conn = duckdb.connect(self.db_path)
            try:
                results = conn.execute(
                    """
                    SELECT run_id, schedule_id, started_at, completed_at,
                           status, batch_id, error
                    FROM schedule_runs
                    WHERE schedule_id = ?
                    ORDER BY started_at DESC
                    LIMIT ?
                """,
                    [schedule_id, limit],
                ).fetchall()
                return results
            finally:
                conn.close()

        rows = await asyncio.to_thread(_get_runs)
        return [
            ScheduleRun(
                run_id=row[0],
                schedule_id=row[1],
                started_at=row[2],
                completed_at=row[3],
                status=row[4],
                batch_id=row[5],
                error=row[6],
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

        # Execute in background
        self._track_background_task(
            asyncio.create_task(self._execute_manual_run(schedule, run))
        )

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
