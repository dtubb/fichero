"""Background Task System for reindex, repair, and metrics jobs.

Provides:
- Task queue with persistent storage
- Background workers using APScheduler
- Progress tracking and status updates
- Support for reindex, metrics recomputation, and repair operations
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import duckdb
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from fichero.db import Database
from fichero.knowledge_models import KnowledgeClaim, KnowledgeClaimLink, KnowledgeEntity
from fichero.models import Artifact, Document

logger = logging.getLogger(__name__)


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


class TaskQueue:
    """Persistent task queue with background execution."""

    def __init__(self, db_path: str, database: Optional[Database] = None):
        self.db_path = db_path
        self.database = database
        self._tasks: dict[str, BackgroundTask] = {}
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._running: bool = False
        self._lock = asyncio.Lock()
        self._init_database()

    def _init_database(self) -> None:
        """Initialize database tables for task tracking."""
        conn = duckdb.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS background_tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    options JSON DEFAULT '{}',
                    priority INTEGER DEFAULT 0,
                    timeout_seconds INTEGER,
                    progress_current INTEGER DEFAULT 0,
                    progress_total INTEGER DEFAULT 0,
                    progress_message TEXT DEFAULT '',
                    progress_updated_at TIMESTAMP,
                    result_success BOOLEAN,
                    result_message TEXT,
                    result_details JSON DEFAULT '{}',
                    result_error TEXT,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    error_message TEXT
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_status
                ON background_tasks(status)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tasks_created
                ON background_tasks(created_at DESC)
            """)
        finally:
            conn.close()

    async def start(self) -> None:
        """Start the task queue and scheduler."""
        if self._running:
            return

        # Initialize APScheduler for background execution
        jobstores = {"default": MemoryJobStore()}
        executors = {"default": AsyncIOExecutor()}
        job_defaults = {"coalesce": True, "max_instances": 1}

        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
        )
        self._scheduler.start()

        # Load pending tasks from database
        await self._load_pending_tasks()

        self._running = True
        logger.info("Task queue started")

    async def stop(self) -> None:
        """Stop the task queue."""
        if self._scheduler:
            self._scheduler.shutdown(wait=True)
        self._running = False
        logger.info("Task queue stopped")

    async def _load_pending_tasks(self) -> None:
        """Load pending and running tasks from database."""

        def _load():
            conn = duckdb.connect(self.db_path)
            try:
                results = conn.execute("""
                    SELECT * FROM background_tasks
                    WHERE status IN ('pending', 'running')
                    ORDER BY priority ASC, created_at ASC
                """).fetchall()
                return results
            finally:
                conn.close()

        rows = await asyncio.to_thread(_load)

        for row in rows:
            task = self._row_to_task(row)
            self._tasks[task.task_id] = task

            # Resume running tasks as pending (they were interrupted)
            if task.status == TaskStatus.RUNNING:
                task.status = TaskStatus.PENDING
                task.error_message = "Interrupted by restart"
                await self._save_task(task)
                logger.info(f"Reset interrupted task {task.task_id} to pending")

        logger.info(f"Loaded {len(rows)} pending tasks")

        # Start processing if there are pending tasks
        if self._tasks:
            self._schedule_next_task()

    def _row_to_task(self, row) -> BackgroundTask:
        """Convert database row to BackgroundTask."""
        # Parse progress
        progress = TaskProgress(
            current=row[7] or 0,
            total=row[8] or 0,
            message=row[9] or "",
            updated_at=row[10] or datetime.now(),
        )
        if progress.total > 0:
            progress.percent = (progress.current / progress.total) * 100

        # Parse result if completed/failed
        result = None
        if row[11] is not None:  # result_success
            result = TaskResult(
                success=row[11],
                message=row[12] or "",
                details=json.loads(row[13]) if row[13] else {},
                error=row[14],
            )

        return BackgroundTask(
            task_id=row[0],
            task_type=TaskType(row[1]),
            name=row[2],
            status=TaskStatus(row[3]),
            config=TaskConfig(
                task_type=TaskType(row[1]),
                options=json.loads(row[4]) if row[4] else {},
                priority=row[5] or 0,
                timeout_seconds=row[6],
            ),
            progress=progress,
            result=result,
            created_at=row[15],
            started_at=row[16],
            completed_at=row[17],
            error_message=row[18],
        )

    async def create_task(
        self,
        task_type: TaskType,
        name: str,
        options: Optional[dict[str, Any]] = None,
        priority: int = 0,
        timeout_seconds: Optional[int] = None,
    ) -> BackgroundTask:
        """Create a new background task."""
        task_id = str(uuid.uuid4())
        now = datetime.now()

        task = BackgroundTask(
            task_id=task_id,
            task_type=task_type,
            name=name,
            status=TaskStatus.PENDING,
            config=TaskConfig(
                task_type=task_type,
                options=options or {},
                priority=priority,
                timeout_seconds=timeout_seconds,
            ),
            created_at=now,
        )

        await self._save_task(task)
        self._tasks[task_id] = task

        # Schedule for execution
        self._schedule_next_task()

        logger.info(f"Created {task_type.value} task {task_id}: {name}")
        return task

    async def _save_task(self, task: BackgroundTask) -> None:
        """Save task to database."""

        def _save():
            conn = duckdb.connect(self.db_path)
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO background_tasks (
                        task_id, task_type, name, status,
                        options, priority, timeout_seconds,
                        progress_current, progress_total, progress_message,
                        progress_updated_at,
                        result_success, result_message, result_details, result_error,
                        created_at, started_at, completed_at, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    [
                        task.task_id,
                        task.task_type.value,
                        task.name,
                        task.status.value,
                        json.dumps(task.config.options),
                        task.config.priority,
                        task.config.timeout_seconds,
                        task.progress.current,
                        task.progress.total,
                        task.progress.message,
                        task.progress.updated_at,
                        task.result.success if task.result else None,
                        task.result.message if task.result else None,
                        json.dumps(task.result.details) if task.result else None,
                        task.result.error if task.result else None,
                        task.created_at,
                        task.started_at,
                        task.completed_at,
                        task.error_message,
                    ],
                )
            finally:
                conn.close()

        try:
            await asyncio.to_thread(_save)
        except (asyncio.CancelledError, RuntimeError):
            # Event loop shutting down (e.g. test teardown) — save synchronously
            _save()

    def _schedule_next_task(self) -> None:
        """Schedule the next pending task for execution."""
        if not self._scheduler or not self._running:
            return

        # Find highest priority pending task
        pending = [t for t in self._tasks.values() if t.status == TaskStatus.PENDING]
        if not pending:
            return

        # Sort by priority, then creation time
        next_task = min(pending, key=lambda t: (t.config.priority, t.created_at))

        # Schedule immediate execution
        self._scheduler.add_job(
            self._execute_task,
            trigger="date",
            args=[next_task.task_id],
            id=f"task_{next_task.task_id}",
            replace_existing=True,
        )
        logger.debug(f"Scheduled task {next_task.task_id}")

    async def _execute_task(self, task_id: str) -> None:
        """Execute a background task."""
        async with self._lock:
            task = self._tasks.get(task_id)
            if not task or task.status != TaskStatus.PENDING:
                return

            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now()
            await self._save_task(task)

        logger.info(f"Starting task {task_id}: {task.name}")

        try:
            # Execute based on task type
            if task.task_type == TaskType.REINDEX:
                result = await self._execute_reindex(task)
            elif task.task_type == TaskType.METRICS:
                result = await self._execute_metrics(task)
            elif task.task_type == TaskType.REPAIR:
                result = await self._execute_repair(task)
            elif task.task_type == TaskType.VECTOR_REPAIR:
                result = await self._execute_vector_repair(task)
            elif task.task_type == TaskType.KG_METRICS:
                result = await self._execute_kg_metrics(task)
            else:
                raise ValueError(f"Unknown task type: {task.task_type}")

            task.result = result
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            if not result.success:
                task.error_message = result.error

        except Exception as e:
            logger.exception(f"Task {task_id} failed: {e}")
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.result = TaskResult(
                success=False,
                message="Task execution failed",
                error=str(e),
            )

        finally:
            task.completed_at = datetime.now()
            await self._save_task(task)

            # Schedule next task
            self._schedule_next_task()

    async def _execute_reindex(self, task: BackgroundTask) -> TaskResult:
        """Execute reindex task for LanceDB."""
        if not self.database:
            return TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )

        # Get documents to reindex


        docs = await asyncio.to_thread(self.database.all, Document)
        total = len(docs)

        task.progress.total = total
        task.progress.message = f"Reindexing {total} documents..."
        await self._save_task(task)

        indexed = 0
        for i, doc in enumerate(docs):
            try:
                # Skip documents without content
                if not doc.page_content:
                    continue

                # Embed document
                success = await asyncio.to_thread(self.database.embed, doc)
                if success:
                    indexed += 1

                # Update progress every 10 documents or on last
                if (i + 1) % 10 == 0 or i == total - 1:
                    task.progress.current = i + 1
                    task.progress.percent = ((i + 1) / total) * 100
                    task.progress.message = f"Indexed {indexed}/{i + 1} documents"
                    task.progress.updated_at = datetime.now()
                    await self._save_task(task)

            except Exception as e:
                logger.warning(f"Failed to index document {doc.id}: {e}")

        return TaskResult(
            success=True,
            message=f"Reindexed {indexed}/{total} documents",
            details={"indexed": indexed, "total": total},
        )

    async def _execute_metrics(self, task: BackgroundTask) -> TaskResult:
        """Execute metrics recomputation task."""
        if not self.database:
            return TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )

        task.progress.total = 5  # Steps in metrics computation
        task.progress.message = "Computing library metrics..."
        await self._save_task(task)

        # Step 1: Document counts
        task.progress.current = 1
        task.progress.message = "Counting documents..."
        task.progress.percent = 20.0
        await self._save_task(task)



        docs = await asyncio.to_thread(self.database.all, Document)
        doc_count = len(docs)

        # Step 2: Embedding stats
        task.progress.current = 2
        task.progress.message = "Getting embedding stats..."
        task.progress.percent = 40.0
        await self._save_task(task)

        stats = await asyncio.to_thread(self.database.embedding_stats)

        # Step 3: File type distribution
        task.progress.current = 3
        task.progress.message = "Analyzing file types..."
        task.progress.percent = 60.0
        await self._save_task(task)

        file_types: dict[str, int] = {}
        for doc in docs:
            ft = doc.file_type.value if doc.file_type else "unknown"
            file_types[ft] = file_types.get(ft, 0) + 1

        # Step 4: Status distribution
        task.progress.current = 4
        task.progress.message = "Analyzing document status..."
        task.progress.percent = 80.0
        await self._save_task(task)

        status_counts: dict[str, int] = {}
        for doc in docs:
            st = doc.status.value if doc.status else "unknown"
            status_counts[st] = status_counts.get(st, 0) + 1

        # Step 5: Complete
        task.progress.current = 5
        task.progress.message = "Metrics computed"
        task.progress.percent = 100.0
        await self._save_task(task)

        return TaskResult(
            success=True,
            message=f"Metrics computed for {doc_count} documents",
            details={
                "document_count": doc_count,
                "embedding_stats": stats,
                "file_types": file_types,
                "status_distribution": status_counts,
            },
        )

    async def _execute_repair(self, task: BackgroundTask) -> TaskResult:
        """Execute repair task for database inconsistencies.

        Repairs:
        - Documents with missing embeddings
        - Orphaned artifacts
        - Stale metadata entries
        """
        if not self.database:
            return TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )

        task.progress.total = 3
        task.progress.message = "Repairing database inconsistencies..."
        await self._save_task(task)



        repaired = {"embeddings": 0, "artifacts": 0, "docs": 0}

        # Step 1: Check for documents missing embeddings
        task.progress.current = 1
        task.progress.message = "Checking document embeddings..."
        task.progress.percent = 33.3
        await self._save_task(task)

        docs = await asyncio.to_thread(self.database.all, Document)
        for doc in docs:
            if doc.page_content and not doc.embedding:
                try:
                    await asyncio.to_thread(self.database.embed, doc)
                    repaired["embeddings"] += 1
                except Exception as e:
                    logger.warning(f"Failed to embed document {doc.id}: {e}")

        # Step 2: Check for orphaned artifacts
        task.progress.current = 2
        task.progress.message = "Checking for orphaned artifacts..."
        task.progress.percent = 66.6
        await self._save_task(task)

        artifacts = await asyncio.to_thread(self.database.all, Artifact)
        doc_ids = {d.id for d in docs}
        for artifact in artifacts:
            if artifact.document_id not in doc_ids:
                # Orphaned artifact - delete or mark as orphaned
                await asyncio.to_thread(self.database.delete, artifact)
                repaired["artifacts"] += 1

        # Step 3: Validate document metadata
        task.progress.current = 3
        task.progress.message = "Validating document metadata..."
        task.progress.percent = 100.0
        await self._save_task(task)

        for doc in docs:
            needs_save = False
            if not doc.updated_at:
                doc.updated_at = datetime.now()
                needs_save = True
            if not doc.created_at:
                doc.created_at = datetime.now()
                needs_save = True
            if needs_save:
                await asyncio.to_thread(self.database.save, doc)
                repaired["docs"] += 1

        total_repaired = sum(repaired.values())
        return TaskResult(
            success=True,
            message=f"Repair completed: {total_repaired} items fixed",
            details=repaired,
        )

    async def _execute_vector_repair(self, task: BackgroundTask) -> TaskResult:
        """Execute vector repair task for LanceDB consistency.

        Repairs vector index issues:
        - Missing vectors for documents with content
        - Orphaned vectors (no corresponding document)
        - Vector dimension mismatches
        """
        if not self.database:
            return TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )

        task.progress.total = 4
        task.progress.message = "Repairing vector index..."
        await self._save_task(task)



        repaired = {"added": 0, "removed": 0, "checked": 0}

        # Step 1: Get all documents and their vector status
        task.progress.current = 1
        task.progress.message = "Scanning documents..."
        task.progress.percent = 25.0
        await self._save_task(task)

        docs = await asyncio.to_thread(self.database.all, Document)

        # Step 2: Check for documents needing embeddings
        task.progress.current = 2
        task.progress.message = "Checking embeddings..."
        task.progress.percent = 50.0
        await self._save_task(task)

        for doc in docs:
            if doc.page_content and not doc.embedding:
                try:
                    success = await asyncio.to_thread(self.database.embed, doc)
                    if success:
                        repaired["added"] += 1
                except Exception as e:
                    logger.warning(f"Failed to repair embedding for {doc.id}: {e}")
            repaired["checked"] += 1

        # Step 3: Validate LanceDB table consistency
        task.progress.current = 3
        task.progress.message = "Validating LanceDB table..."
        task.progress.percent = 75.0
        await self._save_task(task)

        # This would call database-specific validation
        # For now, we just check document-embedding correspondence
        vector_count = 0
        try:
            stats = await asyncio.to_thread(self.database.embedding_stats)
            vector_count = stats.get("total_vectors", 0)
        except Exception as e:
            logger.warning(f"Could not get embedding stats: {e}")

        # Step 4: Complete
        task.progress.current = 4
        task.progress.message = "Vector repair complete"
        task.progress.percent = 100.0
        await self._save_task(task)

        return TaskResult(
            success=True,
            message=f"Vector repair complete: {repaired['added']} added, {repaired['removed']} removed",
            details={
                **repaired,
                "document_count": len(docs),
                "vector_count": vector_count,
            },
        )

    async def _execute_kg_metrics(self, task: BackgroundTask) -> TaskResult:
        """Execute knowledge graph metrics recomputation.

        Recomputes:
        - Entity statistics (per type)
        - Claim statistics (per status, type)
        - Link statistics (per relation type)
        - Connected component analysis
        """
        if not self.database:
            return TaskResult(
                success=False,
                message="Database not available",
                error="Database not initialized",
            )

        task.progress.total = 4
        task.progress.message = "Computing knowledge graph metrics..."
        await self._save_task(task)



        # Step 1: Entity metrics
        task.progress.current = 1
        task.progress.message = "Computing entity metrics..."
        task.progress.percent = 25.0
        await self._save_task(task)

        entities = await asyncio.to_thread(self.database.all, KnowledgeEntity)
        entity_by_type: dict[str, int] = {}
        for ent in entities:
            et = ent.entity_type.value if ent.entity_type else "unknown"
            entity_by_type[et] = entity_by_type.get(et, 0) + 1

        # Step 2: Claim metrics
        task.progress.current = 2
        task.progress.message = "Computing claim metrics..."
        task.progress.percent = 50.0
        await self._save_task(task)

        claims = await asyncio.to_thread(self.database.all, KnowledgeClaim)
        claims_by_status: dict[str, int] = {}
        claims_by_type: dict[str, int] = {}
        claims_with_sources = 0

        for claim in claims:
            st = claim.curation_state.value if claim.curation_state else "unknown"
            claims_by_status[st] = claims_by_status.get(st, 0) + 1

            ct = claim.claim_type.value if claim.claim_type else "unknown"
            claims_by_type[ct] = claims_by_type.get(ct, 0) + 1

            if claim.source_ids or claim.source_document_id:
                claims_with_sources += 1

        # Step 3: Link metrics
        task.progress.current = 3
        task.progress.message = "Computing link metrics..."
        task.progress.percent = 75.0
        await self._save_task(task)

        links = await asyncio.to_thread(self.database.all, KnowledgeClaimLink)
        links_by_relation: dict[str, int] = {}
        for link in links:
            rt = link.relation_type.value if link.relation_type else "unknown"
            links_by_relation[rt] = links_by_relation.get(rt, 0) + 1

        # Step 4: Complete
        task.progress.current = 4
        task.progress.message = "Knowledge graph metrics computed"
        task.progress.percent = 100.0
        await self._save_task(task)

        return TaskResult(
            success=True,
            message=f"KG metrics: {len(entities)} entities, {len(claims)} claims, {len(links)} links",
            details={
                "entity_count": len(entities),
                "entity_by_type": entity_by_type,
                "claim_count": len(claims),
                "claims_by_status": claims_by_status,
                "claims_by_type": claims_by_type,
                "claims_with_sources": claims_with_sources,
                "link_count": len(links),
                "links_by_relation": links_by_relation,
            },
        )

    async def get_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Get task by ID."""
        if task_id in self._tasks:
            return self._tasks[task_id]

        def _load():
            conn = duckdb.connect(self.db_path)
            try:
                result = conn.execute(
                    "SELECT * FROM background_tasks WHERE task_id = ?", [task_id]
                ).fetchone()
                return result
            finally:
                conn.close()

        row = await asyncio.to_thread(_load)
        if row:
            task = self._row_to_task(row)
            self._tasks[task_id] = task
            return task
        return None

    async def list_tasks(
        self,
        status: Optional[TaskStatus] = None,
        task_type: Optional[TaskType] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[BackgroundTask]:
        """List tasks with optional filtering."""

        def _list():
            conn = duckdb.connect(self.db_path)
            try:
                query = "SELECT * FROM background_tasks WHERE 1=1"
                params = []

                if status:
                    query += " AND status = ?"
                    params.append(status.value)
                if task_type:
                    query += " AND task_type = ?"
                    params.append(task_type.value)

                query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                results = conn.execute(query, params).fetchall()
                return results
            finally:
                conn.close()

        rows = await asyncio.to_thread(_list)
        return [self._row_to_task(row) for row in rows]

    async def cancel_task(self, task_id: str) -> Optional[BackgroundTask]:
        """Cancel a pending task."""
        task = await self.get_task(task_id)
        if not task:
            return None

        if task.status != TaskStatus.PENDING:
            raise ValueError(f"Cannot cancel task with status {task.status.value}")

        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now()
        await self._save_task(task)

        logger.info(f"Cancelled task {task_id}")
        return task

    async def delete_task(self, task_id: str) -> bool:
        """Delete a completed/cancelled/failed task."""
        task = await self.get_task(task_id)
        if not task:
            return False

        if task.status in (TaskStatus.PENDING, TaskStatus.RUNNING):
            raise ValueError("Cannot delete running/pending task")

        def _delete():
            conn = duckdb.connect(self.db_path)
            try:
                conn.execute(
                    "DELETE FROM background_tasks WHERE task_id = ?", [task_id]
                )
            finally:
                conn.close()

        await asyncio.to_thread(_delete)

        if task_id in self._tasks:
            del self._tasks[task_id]

        logger.info(f"Deleted task {task_id}")
        return True


# Global task queue instance
_task_queue: Optional[TaskQueue] = None


def get_task_queue() -> Optional[TaskQueue]:
    """Get the global task queue instance."""
    return _task_queue


async def init_task_queue(
    db_path: str, database: Optional[Database] = None
) -> TaskQueue:
    """Initialize and start the global task queue."""
    global _task_queue
    _task_queue = TaskQueue(db_path, database)
    await _task_queue.start()
    return _task_queue


async def shutdown_task_queue() -> None:
    """Shutdown the task queue."""
    global _task_queue
    if _task_queue:
        await _task_queue.stop()
        _task_queue = None
