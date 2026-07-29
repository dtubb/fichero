"""
File System Trigger System.

Provides folder watching capabilities for automated workflow execution:
- Watch folders for file events (created, modified, deleted, moved)
- Filter events by file patterns (glob, regex)
- Debounce rapid events
- Integration with batch execution system
"""

import asyncio
import fnmatch
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

import duckdb
from watchdog.observers import Observer
from watchdog.events import (
    FileSystemEventHandler,
    FileCreatedEvent,
    FileModifiedEvent,
    FileDeletedEvent,
    FileMovedEvent,
)

from fichero_server.workflows.batch import BatchManager
from fichero_server.workflows.workflow_store import WorkflowStore

logger = logging.getLogger(__name__)


class TriggerEvent(str, Enum):
    """Types of file system events to trigger on."""

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"
    ANY = "any"


class TriggerStatus(str, Enum):
    """Status of a file trigger."""

    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"


class FilterMode(str, Enum):
    """How to filter files."""

    GLOB = "glob"  # e.g., "*.pdf"
    REGEX = "regex"  # e.g., r".*\.pdf$"
    EXTENSION = "extension"  # e.g., ["pdf", "docx"]


@dataclass
class TriggerConfig:
    """Configuration for a file trigger."""

    watch_path: str  # Directory to watch
    recursive: bool = True  # Watch subdirectories
    events: list[TriggerEvent] = field(default_factory=lambda: [TriggerEvent.CREATED])
    filter_mode: FilterMode = FilterMode.GLOB
    filter_pattern: Optional[str] = None  # Pattern for glob/regex
    filter_extensions: list[str] = field(
        default_factory=list
    )  # Extensions for extension mode
    exclude_patterns: list[str] = field(default_factory=list)  # Patterns to exclude
    debounce_seconds: float = 1.0  # Debounce rapid events
    batch_delay_seconds: float = 5.0  # Wait before batching events


@dataclass
class FileTrigger:
    """Represents a file system trigger for workflow execution."""

    trigger_id: str
    name: str
    workflow_id: str
    config: TriggerConfig
    status: TriggerStatus
    inputs_template: dict[str, Any] = field(
        default_factory=dict
    )  # Template with {file_path} placeholder
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_triggered_at: Optional[datetime] = None
    trigger_count: int = 0
    error_message: Optional[str] = None
    # Batch execution options
    use_batch: bool = True  # Batch multiple files
    max_concurrent: int = 5


@dataclass
class TriggerExecution:
    """Record of a trigger execution."""

    execution_id: str
    trigger_id: str
    triggered_at: datetime
    file_paths: list[str]
    batch_id: Optional[str] = None
    status: str = "running"  # running, completed, failed
    error: Optional[str] = None
    completed_at: Optional[datetime] = None


class FileWatchHandler(FileSystemEventHandler):
    """Watchdog event handler that queues events for processing."""

    def __init__(
        self,
        trigger: FileTrigger,
        event_callback: Callable[[str, str], None],
    ):
        """Initialize handler.

        Args:
            trigger: The FileTrigger configuration
            event_callback: Callback for (event_type, file_path)
        """
        self.trigger = trigger
        self.event_callback = event_callback
        self._last_events: dict[str, datetime] = {}

    def _should_process(self, path: str, event_type: str) -> bool:
        """Check if event should be processed based on config."""
        config = self.trigger.config

        # Check event type
        events = config.events
        if TriggerEvent.ANY not in events:
            event_enum = TriggerEvent(event_type)
            if event_enum not in events:
                return False

        # Check exclusion patterns
        file_path = Path(path)
        for pattern in config.exclude_patterns:
            if fnmatch.fnmatch(str(file_path), pattern):
                return False
            if fnmatch.fnmatch(file_path.name, pattern):
                return False

        # Check filter
        if config.filter_mode == FilterMode.GLOB:
            if config.filter_pattern:
                if not fnmatch.fnmatch(file_path.name, config.filter_pattern):
                    return False

        elif config.filter_mode == FilterMode.REGEX:
            if config.filter_pattern:
                if not re.match(config.filter_pattern, str(file_path)):
                    return False

        elif config.filter_mode == FilterMode.EXTENSION:
            if config.filter_extensions:
                ext = file_path.suffix.lstrip(".").lower()
                if ext not in [e.lower() for e in config.filter_extensions]:
                    return False

        # Debounce
        now = datetime.now()
        key = f"{event_type}:{path}"
        if key in self._last_events:
            elapsed = (now - self._last_events[key]).total_seconds()
            if elapsed < config.debounce_seconds:
                return False

        self._last_events[key] = now
        return True

    def _handle_event(self, event, event_type: str) -> None:
        """Handle a file system event."""
        if event.is_directory:
            return  # Ignore directory events

        path = event.src_path
        if self._should_process(path, event_type):
            logger.debug(f"Trigger {self.trigger.trigger_id}: {event_type} {path}")
            self.event_callback(event_type, path)

    def on_created(self, event):
        if isinstance(event, FileCreatedEvent):
            self._handle_event(event, "created")

    def on_modified(self, event):
        if isinstance(event, FileModifiedEvent):
            self._handle_event(event, "modified")

    def on_deleted(self, event):
        if isinstance(event, FileDeletedEvent):
            self._handle_event(event, "deleted")

    def on_moved(self, event):
        if isinstance(event, FileMovedEvent):
            # Handle as both deleted (src) and created (dest)
            self._handle_event(event, "moved")


class FileWatcherManager:
    """
    Manages file system triggers for automated workflow execution.

    Uses Watchdog for cross-platform file system monitoring with:
    - Multiple watch directories
    - Event filtering and debouncing
    - Batched workflow execution
    """

    def __init__(
        self,
        db_path: str,
        workflow_store: WorkflowStore,
        batch_manager: Optional[BatchManager] = None,
    ):
        """Initialize the file watcher manager.

        Args:
            db_path: Path to DuckDB database
            workflow_store: WorkflowStore for loading workflows
            batch_manager: Optional BatchManager for batch executions
        """
        self.db_path = db_path
        self.workflow_store = workflow_store
        self.batch_manager = batch_manager or BatchManager(db_path)

        self._observer = Observer()
        self._triggers: dict[str, FileTrigger] = {}
        self._handlers: dict[str, FileWatchHandler] = {}
        self._pending_events: dict[
            str, list[tuple[str, str]]
        ] = {}  # trigger_id -> [(event_type, path)]
        self._batch_tasks: dict[str, asyncio.Task] = {}
        self._pending_tasks: dict[str, list[asyncio.Task]] = {}

        self._init_database()

    def _init_database(self) -> None:
        """Initialize database tables for trigger tracking."""
        conn = duckdb.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS file_triggers (
                    trigger_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    watch_path TEXT NOT NULL,
                    recursive BOOLEAN DEFAULT TRUE,
                    events JSON DEFAULT '["created"]',
                    filter_mode TEXT DEFAULT 'glob',
                    filter_pattern TEXT,
                    filter_extensions JSON DEFAULT '[]',
                    exclude_patterns JSON DEFAULT '[]',
                    debounce_seconds FLOAT DEFAULT 1.0,
                    batch_delay_seconds FLOAT DEFAULT 5.0,
                    inputs_template JSON DEFAULT '{}',
                    status TEXT NOT NULL,
                    use_batch BOOLEAN DEFAULT TRUE,
                    max_concurrent INTEGER DEFAULT 5,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    last_triggered_at TIMESTAMP,
                    trigger_count INTEGER DEFAULT 0,
                    error_message TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS trigger_executions (
                    execution_id TEXT PRIMARY KEY,
                    trigger_id TEXT NOT NULL,
                    triggered_at TIMESTAMP NOT NULL,
                    file_paths JSON NOT NULL,
                    batch_id TEXT,
                    status TEXT NOT NULL,
                    error TEXT,
                    completed_at TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_trigger_executions_trigger
                ON trigger_executions(trigger_id)
            """)
        finally:
            conn.close()

    async def start(self) -> None:
        """Start the file watcher and load existing triggers."""
        # Load triggers from database
        await self._load_triggers()

        # Start watchdog observer
        self._observer.start()
        logger.info("File watcher manager started")

    async def stop(self) -> None:
        """Stop the file watcher."""
        # Cancel pending batch tasks
        for task in self._batch_tasks.values():
            task.cancel()

        # Stop observer
        self._observer.stop()
        self._observer.join()
        logger.info("File watcher manager stopped")

    async def _load_triggers(self) -> None:
        """Load active triggers from database and set up watchers."""

        def _load():
            conn = duckdb.connect(self.db_path)
            try:
                results = conn.execute("""
                    SELECT * FROM file_triggers WHERE status = 'active'
                """).fetchall()
                return results
            finally:
                conn.close()

        rows = await asyncio.to_thread(_load)

        for row in rows:
            trigger = self._row_to_trigger(row)
            self._triggers[trigger.trigger_id] = trigger
            self._setup_watcher(trigger)

        logger.info(f"Loaded {len(rows)} active file triggers")

    def _row_to_trigger(self, row) -> FileTrigger:
        """Convert database row to FileTrigger object."""

        events = json.loads(row[4]) if row[4] else ["created"]

        return FileTrigger(
            trigger_id=row[0],
            name=row[1],
            workflow_id=row[2],
            config=TriggerConfig(
                watch_path=row[3],
                recursive=row[4] if row[4] is not None else True,
                events=[TriggerEvent(e) for e in events],
                filter_mode=FilterMode(row[6]) if row[6] else FilterMode.GLOB,
                filter_pattern=row[7],
                filter_extensions=json.loads(row[8]) if row[8] else [],
                exclude_patterns=json.loads(row[9]) if row[9] else [],
                debounce_seconds=row[10] or 1.0,
                batch_delay_seconds=row[11] or 5.0,
            ),
            inputs_template=json.loads(row[12]) if row[12] else {},
            status=TriggerStatus(row[13]),
            use_batch=row[14] if row[14] is not None else True,
            max_concurrent=row[15] or 5,
            created_at=row[16],
            updated_at=row[17],
            last_triggered_at=row[18],
            trigger_count=row[19] or 0,
            error_message=row[20],
        )

    def _setup_watcher(self, trigger: FileTrigger) -> None:
        """Set up a file system watcher for a trigger."""
        watch_path = Path(trigger.config.watch_path)
        if not watch_path.exists():
            logger.warning(f"Watch path does not exist: {watch_path}")
            return

        # Create event handler
        handler = FileWatchHandler(
            trigger=trigger,
            event_callback=lambda et, p: self._on_event(trigger.trigger_id, et, p),
        )

        # Schedule watcher
        self._observer.schedule(
            handler,
            str(watch_path),
            recursive=trigger.config.recursive,
        )

        self._handlers[trigger.trigger_id] = handler
        logger.debug(f"Watching {watch_path} for trigger {trigger.trigger_id}")

    def _on_event(self, trigger_id: str, event_type: str, file_path: str) -> None:
        """Handle a file system event (called from watchdog thread)."""
        # Queue event for processing
        if trigger_id not in self._pending_events:
            self._pending_events[trigger_id] = []

        self._pending_events[trigger_id].append((event_type, file_path))

        # Schedule batch processing
        self._schedule_batch_processing(trigger_id)

    def _schedule_batch_processing(self, trigger_id: str) -> None:
        """Schedule batch processing after delay."""
        trigger = self._triggers.get(trigger_id)
        if not trigger:
            return

        # Cancel existing task if any
        if trigger_id in self._batch_tasks:
            self._batch_tasks[trigger_id].cancel()

        # Schedule new task
        async def process_after_delay():
            await asyncio.sleep(trigger.config.batch_delay_seconds)
            await self._process_pending_events(trigger_id)

        loop = asyncio.get_event_loop()
        task = loop.create_task(process_after_delay())
        self._batch_tasks[trigger_id] = task

    async def _process_pending_events(self, trigger_id: str) -> None:
        """Process pending events for a trigger."""
        trigger = self._triggers.get(trigger_id)
        if not trigger:
            return

        events = self._pending_events.pop(trigger_id, [])
        if not events:
            return

        # Get unique file paths
        file_paths = list(set(path for _, path in events))

        # Create execution record
        execution = TriggerExecution(
            execution_id=str(uuid.uuid4()),
            trigger_id=trigger_id,
            triggered_at=datetime.now(),
            file_paths=file_paths,
        )
        await self._save_execution(execution)

        try:
            if trigger.use_batch and len(file_paths) > 1:
                # Create batch with inputs for each file
                batch_items = []
                for path in file_paths:
                    inputs = self._resolve_inputs(trigger.inputs_template, path)
                    batch_items.append(inputs)

                batch = await self.batch_manager.create_batch(
                    workflow_id=trigger.workflow_id,
                    items_inputs=batch_items,
                    max_concurrent=trigger.max_concurrent,
                )
                execution.batch_id = batch.batch_id

                # Execute batch in background
                asyncio.create_task(self._execute_batch(execution, batch.batch_id))

            else:
                # Execute workflow for each file
                asyncio.create_task(
                    self._execute_single(execution, trigger, file_paths)
                )

            # Update trigger stats
            trigger.last_triggered_at = execution.triggered_at
            trigger.trigger_count += len(file_paths)
            trigger.updated_at = datetime.now()
            await self._save_trigger(trigger)

        except Exception as e:
            logger.exception(f"Trigger {trigger_id} execution failed: {e}")
            execution.status = "failed"
            execution.error = str(e)
            execution.completed_at = datetime.now()
            await self._save_execution(execution)

            trigger.error_message = str(e)
            await self._save_trigger(trigger)

    def _resolve_inputs(
        self, template: dict[str, Any], file_path: str
    ) -> dict[str, Any]:
        """Resolve inputs template with file path."""
        path = Path(file_path)
        replacements = {
            "{file_path}": str(path),
            "{file_name}": path.name,
            "{file_stem}": path.stem,
            "{file_ext}": path.suffix.lstrip("."),
            "{parent_dir}": str(path.parent),
        }

        def resolve_value(value):
            if isinstance(value, str):
                for placeholder, replacement in replacements.items():
                    value = value.replace(placeholder, replacement)
                return value
            elif isinstance(value, dict):
                return {k: resolve_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [resolve_value(v) for v in value]
            return value

        return resolve_value(template)

    async def _execute_batch(self, execution: TriggerExecution, batch_id: str) -> None:
        """Execute a batch for file trigger."""
        try:
            async for event in self.batch_manager.execute_batch(
                batch_id, self.workflow_store
            ):
                logger.debug(f"Batch {batch_id} event: {event.event_type}")

            execution.status = "completed"
            execution.completed_at = datetime.now()
            await self._save_execution(execution)

        except Exception as e:
            logger.exception(f"Batch {batch_id} failed: {e}")
            execution.status = "failed"
            execution.error = str(e)
            execution.completed_at = datetime.now()
            await self._save_execution(execution)

    async def _execute_single(
        self,
        execution: TriggerExecution,
        trigger: FileTrigger,
        file_paths: list[str],
    ) -> None:
        """Execute workflows for individual files."""
        from fichero_server.workflows.builder import execute_workflow

        try:
            workflow = self.workflow_store.get(trigger.workflow_id)
            if not workflow:
                raise ValueError(f"Workflow {trigger.workflow_id} not found")

            for path in file_paths:
                inputs = self._resolve_inputs(trigger.inputs_template, path)
                await execute_workflow(workflow=workflow, inputs=inputs)

            execution.status = "completed"
            execution.completed_at = datetime.now()
            await self._save_execution(execution)

        except Exception as e:
            logger.exception(f"Single execution failed: {e}")
            execution.status = "failed"
            execution.error = str(e)
            execution.completed_at = datetime.now()
            await self._save_execution(execution)

    async def create_trigger(
        self,
        name: str,
        workflow_id: str,
        config: TriggerConfig,
        inputs_template: Optional[dict[str, Any]] = None,
        use_batch: bool = True,
        max_concurrent: int = 5,
    ) -> FileTrigger:
        """Create a new file trigger.

        Args:
            name: Display name for the trigger
            workflow_id: ID of workflow to execute
            config: Trigger configuration
            inputs_template: Template for workflow inputs with {file_path} etc.
            use_batch: Whether to batch multiple files
            max_concurrent: Max concurrent batch items

        Returns:
            Created FileTrigger object
        """
        # Validate workflow exists
        workflow = self.workflow_store.get(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        # Validate watch path exists
        watch_path = Path(config.watch_path)
        if not watch_path.exists():
            raise ValueError(f"Watch path does not exist: {watch_path}")

        trigger_id = str(uuid.uuid4())
        now = datetime.now()

        trigger = FileTrigger(
            trigger_id=trigger_id,
            name=name,
            workflow_id=workflow_id,
            config=config,
            status=TriggerStatus.ACTIVE,
            inputs_template=inputs_template or {"file_path": "{file_path}"},
            created_at=now,
            updated_at=now,
            use_batch=use_batch,
            max_concurrent=max_concurrent,
        )

        # Save to database
        await self._save_trigger(trigger)

        # Set up watcher
        self._setup_watcher(trigger)

        self._triggers[trigger_id] = trigger
        logger.info(f"Created file trigger {trigger_id}: {name}")

        return trigger

    async def _save_trigger(self, trigger: FileTrigger) -> None:
        """Save trigger to database."""

        def _save():

            conn = duckdb.connect(self.db_path)
            try:
                events = [e.value for e in trigger.config.events]
                conn.execute(
                    """
                    INSERT OR REPLACE INTO file_triggers (
                        trigger_id, name, workflow_id, watch_path, recursive,
                        events, filter_mode, filter_pattern, filter_extensions,
                        exclude_patterns, debounce_seconds, batch_delay_seconds,
                        inputs_template, status, use_batch, max_concurrent,
                        created_at, updated_at, last_triggered_at, trigger_count,
                        error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        trigger.trigger_id,
                        trigger.name,
                        trigger.workflow_id,
                        trigger.config.watch_path,
                        trigger.config.recursive,
                        json.dumps(events),
                        trigger.config.filter_mode.value,
                        trigger.config.filter_pattern,
                        json.dumps(trigger.config.filter_extensions),
                        json.dumps(trigger.config.exclude_patterns),
                        trigger.config.debounce_seconds,
                        trigger.config.batch_delay_seconds,
                        json.dumps(trigger.inputs_template),
                        trigger.status.value,
                        trigger.use_batch,
                        trigger.max_concurrent,
                        trigger.created_at,
                        trigger.updated_at,
                        trigger.last_triggered_at,
                        trigger.trigger_count,
                        trigger.error_message,
                    ],
                )
            finally:
                conn.close()

        await asyncio.to_thread(_save)

    async def _save_execution(self, execution: TriggerExecution) -> None:
        """Save trigger execution to database."""

        def _save():

            conn = duckdb.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO trigger_executions (
                        execution_id, trigger_id, triggered_at, file_paths,
                        batch_id, status, error, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        execution.execution_id,
                        execution.trigger_id,
                        execution.triggered_at,
                        json.dumps(execution.file_paths),
                        execution.batch_id,
                        execution.status,
                        execution.error,
                        execution.completed_at,
                    ],
                )
            finally:
                conn.close()

        await asyncio.to_thread(_save)

    async def get_trigger(self, trigger_id: str) -> Optional[FileTrigger]:
        """Get trigger by ID."""
        if trigger_id in self._triggers:
            return self._triggers[trigger_id]

        def _load():
            conn = duckdb.connect(self.db_path)
            try:
                result = conn.execute(
                    "SELECT * FROM file_triggers WHERE trigger_id = ?", [trigger_id]
                ).fetchone()
                return result
            finally:
                conn.close()

        row = await asyncio.to_thread(_load)
        if row:
            trigger = self._row_to_trigger(row)
            self._triggers[trigger_id] = trigger
            return trigger
        return None

    async def list_triggers(
        self,
        status: Optional[TriggerStatus] = None,
        workflow_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FileTrigger]:
        """List triggers with optional filtering."""

        def _list():
            conn = duckdb.connect(self.db_path)
            try:
                query = "SELECT * FROM file_triggers WHERE 1=1"
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
        return [self._row_to_trigger(row) for row in rows]

    async def pause_trigger(self, trigger_id: str) -> FileTrigger:
        """Pause a file trigger."""
        trigger = await self.get_trigger(trigger_id)
        if not trigger:
            raise ValueError(f"Trigger {trigger_id} not found")

        if trigger.status != TriggerStatus.ACTIVE:
            raise ValueError(f"Cannot pause trigger with status {trigger.status}")

        # Remove watcher
        if trigger_id in self._handlers:
            # Note: watchdog doesn't have unschedule by handler, we'd need to track watches
            del self._handlers[trigger_id]

        trigger.status = TriggerStatus.PAUSED
        trigger.updated_at = datetime.now()
        await self._save_trigger(trigger)

        logger.info(f"Paused file trigger {trigger_id}")
        return trigger

    async def resume_trigger(self, trigger_id: str) -> FileTrigger:
        """Resume a paused file trigger."""
        trigger = await self.get_trigger(trigger_id)
        if not trigger:
            raise ValueError(f"Trigger {trigger_id} not found")

        if trigger.status != TriggerStatus.PAUSED:
            raise ValueError(f"Cannot resume trigger with status {trigger.status}")

        # Re-setup watcher
        self._setup_watcher(trigger)

        trigger.status = TriggerStatus.ACTIVE
        trigger.updated_at = datetime.now()
        await self._save_trigger(trigger)

        logger.info(f"Resumed file trigger {trigger_id}")
        return trigger

    async def update_trigger(self, trigger: FileTrigger) -> FileTrigger:
        """Update an existing file trigger.

        Args:
            trigger: FileTrigger object with updated fields

        Returns:
            Updated FileTrigger object
        """
        # Verify trigger exists
        existing = await self.get_trigger(trigger.trigger_id)
        if not existing:
            raise ValueError(f"Trigger {trigger.trigger_id} not found")

        # If workflow_id changed, validate new workflow exists
        if trigger.workflow_id != existing.workflow_id:
            workflow = self.workflow_store.get(trigger.workflow_id)
            if not workflow:
                raise ValueError(f"Workflow {trigger.workflow_id} not found")

        # If watch path changed and trigger is active, re-setup watcher
        config_changed = (
            trigger.config.watch_path != existing.config.watch_path
            or trigger.config.recursive != existing.config.recursive
            or trigger.config.events != existing.config.events
            or trigger.config.filter_mode != existing.config.filter_mode
            or trigger.config.filter_pattern != existing.config.filter_pattern
        )

        if config_changed and trigger.status == TriggerStatus.ACTIVE:
            # Remove old handler
            if trigger.trigger_id in self._handlers:
                del self._handlers[trigger.trigger_id]

            # Cancel pending tasks
            if trigger.trigger_id in self._pending_tasks:
                for task in self._pending_tasks[trigger.trigger_id]:
                    task.cancel()
                del self._pending_tasks[trigger.trigger_id]

            # Setup new watcher
            self._setup_watcher(trigger)

        # Save to database
        await self._save_trigger(trigger)

        # Update cache
        self._triggers[trigger.trigger_id] = trigger

        logger.info(f"Updated file trigger {trigger.trigger_id}")
        return trigger

    async def delete_trigger(self, trigger_id: str) -> None:
        """Delete a file trigger."""
        # Remove from handlers
        if trigger_id in self._handlers:
            del self._handlers[trigger_id]

        # Cancel pending tasks
        if trigger_id in self._batch_tasks:
            self._batch_tasks[trigger_id].cancel()
            del self._batch_tasks[trigger_id]

        # Remove pending events
        if trigger_id in self._pending_events:
            del self._pending_events[trigger_id]

        # Remove from database
        def _delete():
            conn = duckdb.connect(self.db_path)
            try:
                conn.execute(
                    "DELETE FROM trigger_executions WHERE trigger_id = ?", [trigger_id]
                )
                conn.execute(
                    "DELETE FROM file_triggers WHERE trigger_id = ?", [trigger_id]
                )
            finally:
                conn.close()

        await asyncio.to_thread(_delete)

        # Remove from cache
        if trigger_id in self._triggers:
            del self._triggers[trigger_id]

        logger.info(f"Deleted file trigger {trigger_id}")

    async def get_trigger_executions(
        self,
        trigger_id: str,
        limit: int = 50,
    ) -> list[TriggerExecution]:
        """Get execution history for a trigger."""

        def _get_executions():
            conn = duckdb.connect(self.db_path)
            try:
                results = conn.execute(
                    """
                    SELECT execution_id, trigger_id, triggered_at, file_paths,
                           batch_id, status, error, completed_at
                    FROM trigger_executions
                    WHERE trigger_id = ?
                    ORDER BY triggered_at DESC
                    LIMIT ?
                """,
                    [trigger_id, limit],
                ).fetchall()
                return results
            finally:
                conn.close()

        rows = await asyncio.to_thread(_get_executions)
        return [
            TriggerExecution(
                execution_id=row[0],
                trigger_id=row[1],
                triggered_at=row[2],
                file_paths=json.loads(row[3]) if row[3] else [],
                batch_id=row[4],
                status=row[5],
                error=row[6],
                completed_at=row[7],
            )
            for row in rows
        ]


# Global file watcher instance
_file_watcher: Optional[FileWatcherManager] = None


def get_file_watcher() -> Optional[FileWatcherManager]:
    """Get the global file watcher instance."""
    return _file_watcher


async def init_file_watcher(
    db_path: str,
    workflow_store: WorkflowStore,
    batch_manager: Optional[BatchManager] = None,
) -> FileWatcherManager:
    """Initialize and start the global file watcher."""
    global _file_watcher
    _file_watcher = FileWatcherManager(db_path, workflow_store, batch_manager)
    await _file_watcher.start()
    return _file_watcher


async def shutdown_file_watcher() -> None:
    """Shutdown the global file watcher."""
    global _file_watcher
    if _file_watcher:
        await _file_watcher.stop()
        _file_watcher = None
