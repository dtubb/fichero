"""
Batch Execution System for Fichero Workflows.

Provides batch processing capabilities using LangGraph threads with:
- Concurrent execution with configurable parallelism
- Progress tracking across all batch items
- Pause/resume/cancel at batch level
- Automatic retry of failed items
- Durable checkpointing per item
"""

import asyncio
import json
import logging
import threading
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from fichero_server.core.timeutil import ensure_utc, utc_now
from enum import Enum
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fichero_server.core.duckdb_session import connect_utc

# NOTE: fichero_server.workflows.runtime is imported at CALL time, not here (#3950).
# It pulls builder -> langgraph -> the whole tool universe (~700 modules,
# seconds of import). This module is imported by api/routes/batch.py just to
# get BatchStatus/BatchItem/BatchManager — dataclasses and enums that describe
# a batch. Compiling a graph is something a batch does when it RUNS, not
# something the type definitions need. Keeping this at module scope made
# binding the HTTP socket wait for langgraph.
from fichero_server.workflows.activity import get_activity_tracker
from fichero_server.workflows.activity_store import duckdb_connection_lock
from fichero_server.workflows.workflow_store import WorkflowStore

# Passthrough wrappers (#3950).
#
# Deferring these imports must not remove them as MODULE ATTRIBUTES: tests
# patch `fichero_server.workflows.batch.<name>`, which needs (1) the attribute to exist for mock.patch,
# and (2) the call site to resolve it as a module GLOBAL so the patch takes
# effect. A function-local import satisfies neither and would let those tests
# pass while silently running the real implementation.


def create_compiled_app(*args, **kwargs):
    """Passthrough to fichero_server.workflows.runtime.create_compiled_app; imports it on first call (#3950)."""
    from fichero_server.workflows.runtime import create_compiled_app as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


def build_initial_state(*args, **kwargs):
    """Passthrough to fichero_server.workflows.runtime.build_initial_state; imports it on first call (#3950)."""
    from fichero_server.workflows.runtime import build_initial_state as _impl  # noqa: PLC0415

    return _impl(*args, **kwargs)


logger = logging.getLogger(__name__)
MAX_BATCH_CACHE_SIZE = 512


class BatchStatus(str, Enum):
    """Status of a batch execution."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BatchItemStatus(str, Enum):
    """Status of an individual item in a batch."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchItem:
    """Represents a single item in a batch execution."""

    thread_id: str
    item_index: int
    inputs: dict[str, Any]
    status: BatchItemStatus = BatchItemStatus.PENDING
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


@dataclass
class BatchProgress:
    """Progress information for a batch execution."""

    batch_id: str
    total_items: int
    completed_items: int
    failed_items: int
    running_items: int
    pending_items: int
    progress_percent: float
    estimated_remaining_seconds: Optional[float] = None
    avg_item_duration_seconds: Optional[float] = None


@dataclass
class BatchExecution:
    """Represents a batch of workflow executions."""

    batch_id: str
    workflow_id: str
    status: BatchStatus
    items: list[BatchItem]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    max_concurrent: int = 5

    @property
    def total_items(self) -> int:
        return len(self.items)

    @property
    def completed_items(self) -> int:
        return sum(1 for item in self.items if item.status == BatchItemStatus.COMPLETED)

    @property
    def failed_items(self) -> int:
        return sum(1 for item in self.items if item.status == BatchItemStatus.FAILED)

    @property
    def running_items(self) -> int:
        return sum(1 for item in self.items if item.status == BatchItemStatus.RUNNING)

    @property
    def pending_items(self) -> int:
        return sum(1 for item in self.items if item.status == BatchItemStatus.PENDING)

    def get_progress(self) -> BatchProgress:
        """Calculate current progress."""
        completed = self.completed_items
        total = self.total_items
        progress_percent = (completed / total * 100) if total > 0 else 0

        # Calculate average duration from completed items
        completed_items = [i for i in self.items if i.completed_at and i.started_at]
        if completed_items:
            durations = [
                (i.completed_at - i.started_at).total_seconds() for i in completed_items
            ]
            avg_duration = sum(durations) / len(durations)
            remaining = self.pending_items + self.running_items
            estimated_remaining = avg_duration * remaining / max(self.max_concurrent, 1)
        else:
            avg_duration = None
            estimated_remaining = None

        return BatchProgress(
            batch_id=self.batch_id,
            total_items=total,
            completed_items=completed,
            failed_items=self.failed_items,
            running_items=self.running_items,
            pending_items=self.pending_items,
            progress_percent=progress_percent,
            estimated_remaining_seconds=estimated_remaining,
            avg_item_duration_seconds=avg_duration,
        )


@dataclass
class BatchEvent:
    """Event emitted during batch execution."""

    batch_id: str
    event_type: str  # batch_started, item_started, item_completed, item_failed, batch_completed, batch_failed
    thread_id: Optional[str] = None
    item_index: Optional[int] = None
    progress: Optional[BatchProgress] = None
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=utc_now)


class BatchManager:
    """
    Manages batch workflow executions.

    Uses LangGraph threads for individual item execution with checkpointing,
    coordinated at batch level for progress tracking and control.
    """

    def __init__(self, db_path: str):
        """Initialize batch manager with database path."""
        self.db_path = db_path
        self.activity_tracker = get_activity_tracker(str(db_path))
        self._batches: OrderedDict[str, BatchExecution] = OrderedDict()
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        # #4317: batch cancel shares the ONE cancellation primitive with
        # single runs (execution.cancellation, threading.Event) — this dict
        # holds references into that registry, keyed by batch_id.
        self._cancel_events: dict[str, threading.Event] = {}
        self._pause_events: dict[str, asyncio.Event] = {}
        self._init_database()

    def _remember_batch(self, batch: BatchExecution) -> None:
        self._batches[batch.batch_id] = batch
        self._batches.move_to_end(batch.batch_id)
        while len(self._batches) > MAX_BATCH_CACHE_SIZE:
            self._batches.popitem(last=False)

    def _init_database(self) -> None:
        """Initialize database tables for batch tracking."""
        conn = connect_utc(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    max_concurrent INTEGER DEFAULT 5,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_items (
                    batch_id TEXT NOT NULL,
                    thread_id TEXT NOT NULL,
                    item_index INTEGER NOT NULL,
                    inputs JSON NOT NULL,
                    status TEXT NOT NULL,
                    error TEXT,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    PRIMARY KEY (batch_id, thread_id)
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_batch_items_batch_id
                ON batch_items(batch_id)
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS batch_progress_snapshots (
                    batch_id TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    completed_count INTEGER,
                    failed_count INTEGER,
                    avg_duration_ms FLOAT,
                    PRIMARY KEY (batch_id, timestamp)
                )
            """)
        finally:
            conn.close()

    async def create_batch(
        self,
        workflow_id: str,
        items_inputs: list[dict[str, Any]],
        max_concurrent: int = 5,
    ) -> BatchExecution:
        """
        Create a new batch execution.

        Args:
            workflow_id: ID of the workflow to execute
            items_inputs: List of input dictionaries, one per item
            max_concurrent: Maximum concurrent executions

        Returns:
            BatchExecution object
        """
        batch_id = str(uuid.uuid4())
        now = utc_now()

        # Create batch items with unique thread IDs
        items = [
            BatchItem(
                thread_id=str(uuid.uuid4()),
                item_index=i,
                inputs=inputs,
            )
            for i, inputs in enumerate(items_inputs)
        ]

        batch = BatchExecution(
            batch_id=batch_id,
            workflow_id=workflow_id,
            status=BatchStatus.PENDING,
            items=items,
            created_at=now,
            max_concurrent=max_concurrent,
        )

        # Store in memory and database
        self._remember_batch(batch)
        await self._save_batch(batch)
        self.activity_tracker.batch_created(
            batch_id=batch_id,
            workflow_id=workflow_id,
            total_items=len(items),
            max_concurrent=max_concurrent,
        )

        logger.info(f"Created batch {batch_id} with {len(items)} items")
        return batch

    async def _save_batch(self, batch: BatchExecution) -> None:
        """Save batch state to database."""

        def _save():
            with duckdb_connection_lock(self.db_path):
                conn = connect_utc(self.db_path)
                try:
                    # Save batch
                    conn.execute(
                    """
                    INSERT OR REPLACE INTO batches
                    (batch_id, workflow_id, status, max_concurrent, created_at, started_at, completed_at, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        batch.batch_id,
                        batch.workflow_id,
                        batch.status.value,
                        batch.max_concurrent,
                        batch.created_at,
                        batch.started_at,
                        batch.completed_at,
                        batch.error_message,
                    ],
                )

                    # Save items
                    for item in batch.items:

                        conn.execute(
                        """
                        INSERT OR REPLACE INTO batch_items
                        (batch_id, thread_id, item_index, inputs, status, error, started_at, completed_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        [
                            batch.batch_id,
                            item.thread_id,
                            item.item_index,
                            json.dumps(item.inputs),
                            item.status.value,
                            item.error,
                            item.started_at,
                            item.completed_at,
                        ],
                        )
                finally:
                    conn.close()

        await asyncio.to_thread(_save)

    async def get_batch(self, batch_id: str) -> Optional[BatchExecution]:
        """Get batch by ID."""
        # Check memory cache first
        if batch_id in self._batches:
            self._batches.move_to_end(batch_id)
            return self._batches[batch_id]

        # Load from database
        return await self._load_batch(batch_id)

    async def _load_batch(self, batch_id: str) -> Optional[BatchExecution]:
        """Load batch from database."""

        def _load():
            conn = connect_utc(self.db_path)
            try:
                # Load batch
                result = conn.execute(
                    """
                    SELECT workflow_id, status, max_concurrent, created_at,
                           started_at, completed_at, error_message
                    FROM batches WHERE batch_id = ?
                """,
                    [batch_id],
                ).fetchone()

                if not result:
                    return None

                (
                    workflow_id,
                    status,
                    max_concurrent,
                    created_at,
                    started_at,
                    completed_at,
                    error_message,
                ) = result

                # Load items
                items_result = conn.execute(
                    """
                    SELECT thread_id, item_index, inputs, status, error, started_at, completed_at
                    FROM batch_items WHERE batch_id = ?
                    ORDER BY item_index
                """,
                    [batch_id],
                ).fetchall()


                items = [
                    BatchItem(
                        thread_id=row[0],
                        item_index=row[1],
                        inputs=json.loads(row[2]) if row[2] else {},
                        status=BatchItemStatus(row[3]),
                        error=row[4],
                        started_at=ensure_utc(row[5]),
                        completed_at=ensure_utc(row[6]),
                    )
                    for row in items_result
                ]

                return BatchExecution(
                    batch_id=batch_id,
                    workflow_id=workflow_id,
                    status=BatchStatus(status),
                    items=items,
                    created_at=created_at,
                    started_at=started_at,
                    completed_at=completed_at,
                    error_message=error_message,
                    max_concurrent=max_concurrent,
                )
            finally:
                conn.close()

        batch = await asyncio.to_thread(_load)
        if batch:
            self._remember_batch(batch)
        return batch

    async def list_batches(
        self,
        status: Optional[BatchStatus] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BatchExecution]:
        """List batches with optional filtering."""

        def _list():
            conn = connect_utc(self.db_path)
            try:
                if status:
                    result = conn.execute(
                        """
                        SELECT batch_id FROM batches
                        WHERE status = ?
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                    """,
                        [status.value, limit, offset],
                    ).fetchall()
                else:
                    result = conn.execute(
                        """
                        SELECT batch_id FROM batches
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                    """,
                        [limit, offset],
                    ).fetchall()
                return [row[0] for row in result]
            finally:
                conn.close()

        batch_ids = await asyncio.to_thread(_list)
        batches = []
        for batch_id in batch_ids:
            batch = await self.get_batch(batch_id)
            if batch:
                batches.append(batch)
        return batches

    async def execute_batch(
        self,
        batch_id: str,
        workflow_store: WorkflowStore,
    ) -> AsyncIterator[BatchEvent]:
        """
        Execute a batch, yielding progress events.

        Args:
            batch_id: ID of the batch to execute
            workflow_store: WorkflowStore for loading workflow definitions

        Yields:
            BatchEvent objects for progress tracking
        """
        batch = await self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        if batch.status not in [BatchStatus.PENDING, BatchStatus.PAUSED]:
            raise ValueError(
                f"Batch {batch_id} cannot be started (status: {batch.status})"
            )

        # Initialize control events. Cancel comes from the shared registry
        # (#4317) — cleared first so a re-executed batch id starts unset.
        from fichero_server.execution.cancellation import (
            cancellation_event,
            clear_cancellation,
        )

        clear_cancellation(batch_id)
        self._cancel_events[batch_id] = cancellation_event(batch_id)
        self._pause_events[batch_id] = asyncio.Event()
        self._semaphores[batch_id] = asyncio.Semaphore(batch.max_concurrent)

        # Update batch status
        batch.status = BatchStatus.RUNNING
        batch.started_at = batch.started_at or datetime.now(timezone.utc)
        await self._save_batch(batch)
        self.activity_tracker.batch_started(
            batch_id=batch_id,
            workflow_id=batch.workflow_id,
            total_items=batch.total_items,
            max_concurrent=batch.max_concurrent,
        )

        yield BatchEvent(
            batch_id=batch_id,
            event_type="batch_started",
            progress=batch.get_progress(),
        )

        # Load workflow definition
        workflow_def = workflow_store.get(batch.workflow_id)
        if not workflow_def:
            batch.status = BatchStatus.FAILED
            batch.error_message = f"Workflow {batch.workflow_id} not found"
            await self._save_batch(batch)
            yield BatchEvent(
                batch_id=batch_id,
                event_type="batch_failed",
                error=batch.error_message,
            )
            return

        # Build the graph once via shared runtime helper.
        compiled_graph, _ = create_compiled_app(
            workflow_def,
            db_path=self.db_path,
            enable_parallel=True,
        )

        # Create tasks for pending items
        pending_items = [i for i in batch.items if i.status == BatchItemStatus.PENDING]

        async def execute_item(item: BatchItem):
            """Execute a single batch item."""

            async def _settle_item_documents(final_status: str, **extra) -> None:
                """#4315: failed/cancelled items must not strand their
                documents at Status.processing — revert to pending with a
                provenance entry. Best-effort."""
                try:
                    from fichero_server.db.manager import db_manager
                    from fichero_server.workflows.completion import (
                        collect_processed_document_ids,
                        finalize_run_documents,
                    )

                    snapshot = await compiled_graph.aget_state(
                        {"configurable": {"thread_id": item.thread_id}}
                    )
                    item_db = db_manager.get_database(
                        str(Path(self.db_path).parent)
                    )
                    finalize_run_documents(
                        item_db,
                        collect_processed_document_ids(
                            getattr(snapshot, "values", None)
                        ),
                        final_status,
                        workflow_run={
                            "thread_id": item.thread_id,
                            "batch_id": batch_id,
                            "item_index": item.item_index,
                            "workflow_id": batch.workflow_id,
                            "workflow_name": workflow_def.name,
                            "result": {"status": final_status, **extra},
                            "started_at": item.started_at,
                            "completed_at": datetime.now(timezone.utc),
                        },
                    )
                except Exception as settle_exc:
                    logger.warning(
                        "Batch %s item %s document finalize (%s) failed: %s",
                        batch_id,
                        item.item_index,
                        final_status,
                        settle_exc,
                    )

            # Check for cancellation
            if self._cancel_events[batch_id].is_set():
                item.status = BatchItemStatus.CANCELLED
                return

            # Wait if paused
            while self._pause_events[batch_id].is_set():
                await asyncio.sleep(0.5)
                if self._cancel_events[batch_id].is_set():
                    item.status = BatchItemStatus.CANCELLED
                    return

            async with self._semaphores[batch_id]:
                item.status = BatchItemStatus.RUNNING
                item.started_at = datetime.now(timezone.utc)

                try:
                    # Execute with LangGraph
                    config = {"configurable": {"thread_id": item.thread_id}}
                    initial_state = build_initial_state(
                        item.inputs,
                        library_path=str(Path(self.db_path).parent),
                        metadata={"batch_id": batch_id, "item_index": item.item_index},
                    )
                    # #4313/#4317: the item's thread_id is its run id — tools
                    # stamp it onto artifacts, and the per-file fan-out checks
                    # it against the shared cancellation registry.
                    initial_state["task_id"] = item.thread_id

                    # Run the graph
                    async for _ in compiled_graph.astream(initial_state, config):
                        # Check for pause/cancel during execution
                        if self._cancel_events[batch_id].is_set():
                            item.status = BatchItemStatus.CANCELLED
                            item.completed_at = datetime.now(timezone.utc)
                            # #4315: settle docs this item left processing.
                            await _settle_item_documents("cancelled")
                            return

                    item.status = BatchItemStatus.COMPLETED
                    item.completed_at = datetime.now(timezone.utc)

                    # This item's full pipeline is done — flip its documents
                    # (and their page children) from processing → completed.
                    # Tool nodes leave docs in `processing` mid-pipeline so the
                    # per-page green check no longer appears after just the
                    # first step (#1282). Scoped to THIS item's documents so
                    # concurrent items don't complete each other's pages.
                    try:
                        from fichero_server.db.manager import db_manager
                        from fichero_server.workflows.completion import (
                            collect_processed_document_ids,
                            complete_run_documents,
                        )

                        snapshot = await compiled_graph.aget_state(config)
                        run_doc_ids = collect_processed_document_ids(
                            getattr(snapshot, "values", None)
                        )
                        item_db = db_manager.get_database(str(Path(self.db_path).parent))
                        complete_run_documents(
                            item_db,
                            run_doc_ids,
                            workflow_run={
                                "batch_id": batch_id,
                                "item_index": item.item_index,
                                "workflow_id": batch.workflow_id,
                                "workflow_name": workflow_def.name,
                                "provider": workflow_def.provider,
                                "model": workflow_def.model,
                                "result": {"status": item.status.value},
                                "started_at": item.started_at,
                                "completed_at": item.completed_at,
                            },
                        )
                        # document.updated is broadcast inside
                        # complete_run_documents (centralised for both paths,
                        # #2518) — no per-caller emit needed here.
                    except Exception as completion_exc:
                        item.status = BatchItemStatus.FAILED
                        item.error = f"Document completion failed: {completion_exc}"
                        logger.exception(
                            "Batch %s item %s document completion failed",
                            batch_id,
                            item.item_index,
                        )

                except Exception as e:
                    item.status = BatchItemStatus.FAILED
                    item.error = str(e)
                    item.completed_at = datetime.now(timezone.utc)
                    logger.error(f"Batch {batch_id} item {item.item_index} failed: {e}")
                    # #4315: settle docs this item left processing.
                    await _settle_item_documents("failed", error=str(e)[:500])

        # Execute items with progress tracking
        event_queue: asyncio.Queue[BatchEvent] = asyncio.Queue()

        async def execute_with_events(item: BatchItem):
            """Execute item and emit events."""
            self.activity_tracker.batch_item_started(
                batch_id=batch_id,
                thread_id=item.thread_id,
                item_index=item.item_index,
                workflow_id=batch.workflow_id,
            )
            await event_queue.put(
                BatchEvent(
                    batch_id=batch_id,
                    event_type="item_started",
                    thread_id=item.thread_id,
                    item_index=item.item_index,
                )
            )

            await execute_item(item)

            if item.status == BatchItemStatus.COMPLETED:
                duration_ms = None
                if item.started_at and item.completed_at:
                    duration_ms = (
                        item.completed_at - item.started_at
                    ).total_seconds() * 1000
                self.activity_tracker.batch_item_completed(
                    batch_id=batch_id,
                    thread_id=item.thread_id,
                    item_index=item.item_index,
                    duration_ms=duration_ms or 0,
                    workflow_id=batch.workflow_id,
                )
                await event_queue.put(
                    BatchEvent(
                        batch_id=batch_id,
                        event_type="item_completed",
                        thread_id=item.thread_id,
                        item_index=item.item_index,
                        progress=batch.get_progress(),
                    )
                )
            elif item.status == BatchItemStatus.FAILED:
                self.activity_tracker.batch_item_failed(
                    batch_id=batch_id,
                    thread_id=item.thread_id,
                    item_index=item.item_index,
                    error=item.error or "Unknown batch item failure",
                    workflow_id=batch.workflow_id,
                )
                await event_queue.put(
                    BatchEvent(
                        batch_id=batch_id,
                        event_type="item_failed",
                        thread_id=item.thread_id,
                        item_index=item.item_index,
                        error=item.error,
                        progress=batch.get_progress(),
                    )
                )

        # Start all item tasks
        tasks = [
            asyncio.create_task(execute_with_events(item)) for item in pending_items
        ]

        # Yield events as they come
        completed_tasks = 0
        total_tasks = len(tasks)

        while completed_tasks < total_tasks:
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                yield event

                if event.event_type in ["item_completed", "item_failed"]:
                    completed_tasks += 1
                    await self._save_batch(batch)

            except asyncio.TimeoutError:
                # Check if any tasks completed
                done = [t for t in tasks if t.done()]
                if len(done) == total_tasks:
                    break

        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)

        # Determine final batch status
        if self._cancel_events[batch_id].is_set():
            batch.status = BatchStatus.CANCELLED
        elif batch.failed_items > 0 and batch.completed_items > 0:
            batch.status = BatchStatus.PARTIAL_FAILURE
        elif batch.failed_items == batch.total_items:
            batch.status = BatchStatus.FAILED
        else:
            batch.status = BatchStatus.COMPLETED

        batch.completed_at = datetime.now(timezone.utc)
        await self._save_batch(batch)
        duration_ms = None
        if batch.started_at and batch.completed_at:
            duration_ms = (batch.completed_at - batch.started_at).total_seconds() * 1000
        if batch.status == BatchStatus.CANCELLED:
            self.activity_tracker.batch_cancelled(
                batch_id=batch_id,
                workflow_id=batch.workflow_id,
                total_items=batch.total_items,
            )
        elif batch.status == BatchStatus.FAILED:
            self.activity_tracker.batch_failed(
                batch_id=batch_id,
                workflow_id=batch.workflow_id,
                total_items=batch.total_items,
                failed_items=batch.failed_items,
                error=batch.error_message or "All batch items failed",
                duration_ms=duration_ms,
            )
        else:
            # COMPLETED or PARTIAL_FAILURE map to batch_completed with counts.
            self.activity_tracker.batch_completed(
                batch_id=batch_id,
                workflow_id=batch.workflow_id,
                total_items=batch.total_items,
                completed_items=batch.completed_items,
                failed_items=batch.failed_items,
                duration_ms=duration_ms or 0,
                status=batch.status.value,
            )

        # Cleanup — drop the shared cancellation events for the batch and its
        # items now that everything reached a terminal state (#4317).
        from fichero_server.execution.cancellation import clear_cancellation

        del self._cancel_events[batch_id]
        del self._pause_events[batch_id]
        del self._semaphores[batch_id]
        clear_cancellation(batch_id)
        for item in batch.items:
            clear_cancellation(item.thread_id)

        yield BatchEvent(
            batch_id=batch_id,
            event_type="batch_completed"
            if batch.status == BatchStatus.COMPLETED
            else "batch_finished",
            progress=batch.get_progress(),
        )

    async def pause_batch(self, batch_id: str) -> BatchExecution:
        """Pause a running batch."""
        batch = await self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        if batch.status != BatchStatus.RUNNING:
            raise ValueError(f"Cannot pause batch with status {batch.status}")

        if batch_id in self._pause_events:
            self._pause_events[batch_id].set()

        batch.status = BatchStatus.PAUSED
        await self._save_batch(batch)
        self.activity_tracker.batch_paused(
            batch_id=batch_id,
            workflow_id=batch.workflow_id,
            total_items=batch.total_items,
        )

        logger.info(f"Paused batch {batch_id}")
        return batch

    async def resume_batch(
        self,
        batch_id: str,
        workflow_store: WorkflowStore,
    ) -> AsyncIterator[BatchEvent]:
        """Resume a paused batch."""
        batch = await self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        if batch.status != BatchStatus.PAUSED:
            raise ValueError(f"Cannot resume batch with status {batch.status}")

        if batch_id in self._pause_events:
            self._pause_events[batch_id].clear()
        self.activity_tracker.batch_resumed(
            batch_id=batch_id,
            workflow_id=batch.workflow_id,
            total_items=batch.total_items,
        )

        # Continue execution
        async for event in self.execute_batch(batch_id, workflow_store):
            yield event

    async def cancel_batch(self, batch_id: str) -> BatchExecution:
        """Cancel a running or paused batch."""
        batch = await self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        if batch.status not in [
            BatchStatus.RUNNING,
            BatchStatus.PAUSED,
            BatchStatus.PENDING,
        ]:
            raise ValueError(f"Cannot cancel batch with status {batch.status}")

        # One primitive (#4317): set the batch-level event AND each
        # non-terminal item's run event so per-file fan-out branches inside a
        # long node stop at their next file boundary.
        from fichero_server.execution.cancellation import request_cancellation

        request_cancellation(batch_id)
        for item in batch.items:
            if item.status in (BatchItemStatus.PENDING, BatchItemStatus.RUNNING):
                request_cancellation(item.thread_id)

        # Mark pending items as cancelled
        for item in batch.items:
            if item.status == BatchItemStatus.PENDING:
                item.status = BatchItemStatus.CANCELLED

        batch.status = BatchStatus.CANCELLED
        batch.completed_at = datetime.now(timezone.utc)
        await self._save_batch(batch)
        self.activity_tracker.batch_cancelled(
            batch_id=batch_id,
            workflow_id=batch.workflow_id,
            total_items=batch.total_items,
        )

        logger.info(f"Cancelled batch {batch_id}")
        return batch

    async def reset_failed_items(self, batch_id: str) -> BatchExecution:
        """Reset a batch's FAILED items back to PENDING (the discrete pre-stream
        transition of a retry).

        Extracted from ``retry_failed_items`` so BOTH the streaming retry route
        AND the audited ``batch.retry`` action (EPIC #1848) drive the *same*
        reset logic (iterate-not-replace: the transition is wrapped, never
        re-derived). Raises ``ValueError`` on missing batch or a status that
        cannot be retried, exactly as before.
        """
        batch = await self.get_batch(batch_id)
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        if batch.status not in [BatchStatus.PARTIAL_FAILURE, BatchStatus.FAILED]:
            raise ValueError(f"Cannot retry batch with status {batch.status}")

        # Reset failed items to pending
        for item in batch.items:
            if item.status == BatchItemStatus.FAILED:
                item.status = BatchItemStatus.PENDING
                item.error = None
                item.started_at = None
                item.completed_at = None

        batch.status = BatchStatus.PENDING
        batch.completed_at = None
        await self._save_batch(batch)
        return batch

    async def retry_failed_items(
        self,
        batch_id: str,
        workflow_store: WorkflowStore,
    ) -> AsyncIterator[BatchEvent]:
        """Retry failed items in a batch."""
        await self.reset_failed_items(batch_id)

        # Execute again
        async for event in self.execute_batch(batch_id, workflow_store):
            yield event

    async def delete_batch(self, batch_id: str) -> None:
        """Delete a batch and its items."""

        def _delete():
            conn = connect_utc(self.db_path)
            try:
                conn.execute("DELETE FROM batch_items WHERE batch_id = ?", [batch_id])
                conn.execute(
                    "DELETE FROM batch_progress_snapshots WHERE batch_id = ?",
                    [batch_id],
                )
                conn.execute("DELETE FROM batches WHERE batch_id = ?", [batch_id])
            finally:
                conn.close()

        await asyncio.to_thread(_delete)

        if batch_id in self._batches:
            del self._batches[batch_id]

        logger.info(f"Deleted batch {batch_id}")
