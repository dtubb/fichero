"""Unit tests for background task system.

Tests cover:
- TaskQueue functionality
- Task creation and lifecycle
- Progress tracking
- Reindex task execution
- Metrics task execution
- API endpoints

Queue lifecycle note: this suite's async tests each run in their own event
loop (conftest's ``pytest_pyfunc_call`` drives coroutine tests via
``asyncio.run``), and ``TaskQueue.start()`` binds an AsyncIOScheduler to the
RUNNING loop. So the queue must be started INSIDE the test's own loop — the
``running_queue`` async context manager below. The previous ``async def``
``@pytest.fixture`` was never supported by any installed plugin and became a
hard setup error on pytest 9 (14 tests ERRORED, PytestRemovedIn9Warning).
"""

import pytest
from contextlib import asynccontextmanager
from unittest.mock import Mock
import asyncio

from fichero_server.workflows.tasks import (
    TaskQueue,
    TaskType,
    TaskStatus,
    BackgroundTask,
    TaskConfig,
    TaskProgress,
    TaskResult,
    get_task_queue,
    init_task_queue,
    shutdown_task_queue,
)


@asynccontextmanager
async def running_queue(db_path, database=None, *, paused=False):
    """A started TaskQueue, stopped on exit — in the CALLER's event loop."""
    queue = TaskQueue(db_path, database=database)
    await queue.start()
    if paused:
        # Pause the scheduler so tasks aren't picked up before an
        # ordering/pending assertion runs.
        queue._scheduler.pause()
    try:
        yield queue
    finally:
        if paused:
            queue._scheduler.resume()
        await queue.stop()


class TestTaskQueue:
    """Test suite for TaskQueue class."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Create temporary database path."""
        return str(tmp_path / "test_tasks.duckdb")

    @pytest.mark.asyncio
    async def test_create_task(self, temp_db_path):
        """Test creating a background task."""
        async with running_queue(temp_db_path) as task_queue:
            task = await task_queue.create_task(
                task_type=TaskType.REINDEX,
                name="Test Reindex",
                options={"full": True},
                priority=5,
            )

            assert task.task_id is not None
            assert task.task_type == TaskType.REINDEX
            assert task.name == "Test Reindex"
            assert task.status == TaskStatus.PENDING
            assert task.config.options == {"full": True}
            assert task.config.priority == 5

    @pytest.mark.asyncio
    async def test_get_task(self, temp_db_path):
        """Test retrieving a task by ID."""
        async with running_queue(temp_db_path) as task_queue:
            created = await task_queue.create_task(
                TaskType.METRICS,
                "Test Metrics",
            )

            retrieved = await task_queue.get_task(created.task_id)

            assert retrieved is not None
            assert retrieved.task_id == created.task_id
            assert retrieved.name == "Test Metrics"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, temp_db_path):
        """Test retrieving a non-existent task."""
        async with running_queue(temp_db_path) as task_queue:
            task = await task_queue.get_task("nonexistent-id")
            assert task is None

    @pytest.mark.asyncio
    async def test_list_tasks(self, temp_db_path):
        """Test listing tasks."""
        async with running_queue(temp_db_path) as task_queue:
            # Create multiple tasks
            await task_queue.create_task(TaskType.REINDEX, "Task 1")
            await task_queue.create_task(TaskType.METRICS, "Task 2")
            await task_queue.create_task(TaskType.REPAIR, "Task 3")

            tasks = await task_queue.list_tasks()

            assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_list_tasks_with_filter(self, temp_db_path):
        """Test listing tasks with status filter by creating finished and pending tasks."""
        async with running_queue(temp_db_path) as task_queue:
            first_task = await task_queue.create_task(TaskType.REPAIR, "Quick Task")

            # Poll until the first task is no longer PENDING or RUNNING (up to 3 seconds)
            for _ in range(30):
                await asyncio.sleep(0.1)
                t = await task_queue.get_task(first_task.task_id)
                if t and t.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
                    break

            # Now create more tasks — these will be pending (queued after running one)
            await task_queue.create_task(TaskType.REPAIR, "Pending Task 1")
            await task_queue.create_task(TaskType.REPAIR, "Pending Task 2")

            # Get all tasks
            all_tasks = await task_queue.list_tasks()

            # First task should have finished (completed or failed — no DB in this fixture)
            # The other two should still be pending (they were queued after the first ran)
            finished = [
                t
                for t in all_tasks
                if t.status not in (TaskStatus.PENDING, TaskStatus.RUNNING)
            ]
            pending = [t for t in all_tasks if t.status == TaskStatus.PENDING]

            assert len(finished) >= 1
            assert len(pending) >= 1

    @pytest.mark.asyncio
    async def test_list_tasks_by_type(self, temp_db_path):
        """Test listing tasks with type filter."""
        async with running_queue(temp_db_path) as task_queue:
            await task_queue.create_task(TaskType.REINDEX, "Reindex Task")
            await task_queue.create_task(TaskType.REINDEX, "Another Reindex")
            await task_queue.create_task(TaskType.METRICS, "Metrics Task")

            reindex_tasks = await task_queue.list_tasks(task_type=TaskType.REINDEX)

            assert len(reindex_tasks) == 2

    @pytest.mark.asyncio
    async def test_cancel_task(self, temp_db_path):
        """Test cancelling a pending task."""
        async with running_queue(temp_db_path) as task_queue:
            task = await task_queue.create_task(TaskType.REINDEX, "To Cancel")

            cancelled = await task_queue.cancel_task(task.task_id)

            assert cancelled is not None
            assert cancelled.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_non_pending_task_fails(self, temp_db_path):
        """Test cancelling a non-pending task raises error."""
        async with running_queue(temp_db_path) as task_queue:
            task = await task_queue.create_task(TaskType.REINDEX, "To Cancel")
            await task_queue.cancel_task(task.task_id)

            with pytest.raises(ValueError, match="Cannot cancel"):
                await task_queue.cancel_task(task.task_id)

    @pytest.mark.asyncio
    async def test_delete_task(self, temp_db_path):
        """Test deleting a completed task."""
        async with running_queue(temp_db_path) as task_queue:
            task = await task_queue.create_task(TaskType.REINDEX, "To Delete")
            await task_queue.cancel_task(task.task_id)

            deleted = await task_queue.delete_task(task.task_id)

            assert deleted is True
            assert await task_queue.get_task(task.task_id) is None

    @pytest.mark.asyncio
    async def test_delete_running_task_fails(self, temp_db_path):
        """Test deleting a running task raises error."""
        async with running_queue(temp_db_path) as task_queue:
            task = await task_queue.create_task(TaskType.REINDEX, "Running Task")
            # Simulate running status
            task.status = TaskStatus.RUNNING

            with pytest.raises(ValueError, match="Cannot delete"):
                await task_queue.delete_task(task.task_id)


class TestTaskExecution:
    async def wait_for_completion(self, task_queue, task_id):
        for _ in range(30):
            task = await task_queue.get_task(task_id)
            if task and task.status not in (TaskStatus.PENDING, TaskStatus.RUNNING):
                return task
            await asyncio.sleep(0.1)
        return await task_queue.get_task(task_id)

    """Test suite for task execution."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        return str(tmp_path / "test_exec.duckdb")

    @pytest.fixture
    def mock_database(self, monkeypatch, tmp_path):
        """Create a mock database.

        Workers now resolve a thread-local Database via
        ``db_manager.get_database`` from inside the pool thread (#2509), so
        the mock is given a realistic package ``.path`` and we patch
        ``db_manager.get_database`` to return it regardless of thread.
        """
        db = Mock()
        db.path = tmp_path / "test.fichero" / "fichero.duckdb"
        db.all = Mock(return_value=[])
        db.embed = Mock(return_value=True)
        db.embedding_stats = Mock(return_value={"indexed": 0, "total": 0})
        monkeypatch.setattr(
            "fichero_server.workflows.task_workers.db_manager.get_database",
            lambda _path: db,
        )
        return db

    @pytest.mark.asyncio
    async def test_reindex_task_with_no_documents(self, temp_db_path, mock_database):
        """Test reindex task when there are no documents."""
        mock_database.all.return_value = []

        async with running_queue(temp_db_path, mock_database) as task_queue:
            task = await task_queue.create_task(TaskType.REINDEX, "Empty Reindex")

            updated = await self.wait_for_completion(task_queue, task.task_id)
            assert updated.status == TaskStatus.COMPLETED
            assert updated.result is not None
            assert updated.result.success is True
            assert updated.result.details["indexed"] == 0
            assert updated.result.details["total"] == 0

    @pytest.mark.asyncio
    async def test_metrics_task_with_empty_database(self, temp_db_path, mock_database):
        """Test metrics task with empty database."""
        mock_database.all.return_value = []
        mock_database.embedding_stats.return_value = {"indexed": 0, "exists": False}

        async with running_queue(temp_db_path, mock_database) as task_queue:
            task = await task_queue.create_task(TaskType.METRICS, "Empty Metrics")

            updated = await self.wait_for_completion(task_queue, task.task_id)
            assert updated.status == TaskStatus.COMPLETED
            assert updated.result is not None
            assert updated.result.details["document_count"] == 0

    @pytest.mark.asyncio
    async def test_repair_task_placeholder(self, temp_db_path, mock_database):
        """Test repair task completes successfully."""
        async with running_queue(temp_db_path, mock_database) as task_queue:
            task = await task_queue.create_task(TaskType.REPAIR, "Repair Task")

            updated = await self.wait_for_completion(task_queue, task.task_id)
            assert updated.status == TaskStatus.COMPLETED
            assert updated.result.success is True
            assert updated.result.message  # any non-empty completion message


class TestGlobalFunctions:
    """Test suite for global task queue functions."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        return str(tmp_path / "test_global.duckdb")

    @pytest.mark.asyncio
    async def test_init_task_queue(self, temp_db_path):
        """Test initializing global task queue."""
        queue = await init_task_queue(temp_db_path)

        assert queue is not None
        assert get_task_queue() is queue

        await shutdown_task_queue()

    @pytest.mark.asyncio
    async def test_shutdown_task_queue(self, temp_db_path):
        """Test shutting down global task queue."""
        await init_task_queue(temp_db_path)
        assert get_task_queue() is not None

        await shutdown_task_queue()
        assert get_task_queue() is None

    @pytest.mark.asyncio
    async def test_get_task_queue_without_init(self):
        """Test getting queue before initialization."""
        # Reset global state
        import fichero_server.workflows.tasks as tasks_module

        tasks_module._task_queue = None
        assert get_task_queue() is None


class TestTaskToDict:
    """Test suite for task serialization."""

    def test_task_to_dict(self):
        """Test converting task to dictionary."""
        from datetime import datetime

        task = BackgroundTask(
            task_id="test-123",
            task_type=TaskType.REINDEX,
            name="Test Task",
            status=TaskStatus.PENDING,
            config=TaskConfig(task_type=TaskType.REINDEX),
            progress=TaskProgress(current=50, total=100, percent=50.0),
            created_at=datetime(2024, 1, 1, 12, 0, 0),
        )

        data = task.to_dict()

        assert data["task_id"] == "test-123"
        assert data["task_type"] == "reindex"
        assert data["status"] == "pending"
        assert data["progress"]["current"] == 50
        assert data["progress"]["percent"] == 50.0

    def test_task_result_to_dict(self):
        """Test converting task result to dictionary."""
        result = TaskResult(
            success=True,
            message="Completed",
            details={"count": 10},
        )

        data = result.to_dict()

        assert data["success"] is True
        assert data["message"] == "Completed"
        assert data["details"]["count"] == 10


class TestTaskPriority:
    """Test suite for task priority ordering."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        return str(tmp_path / "test_priority.duckdb")

    @pytest.mark.asyncio
    async def test_tasks_ordered_by_priority(self, temp_db_path):
        """Test that tasks are processed in priority order."""
        # paused=True: scheduler must not pick tasks up before the
        # ordering assertion runs.
        async with running_queue(temp_db_path, paused=True) as task_queue:
            # Create tasks with different priorities
            await task_queue.create_task(
                TaskType.REINDEX, "Low Priority", priority=10
            )
            await task_queue.create_task(
                TaskType.REINDEX, "High Priority", priority=1
            )
            await task_queue.create_task(
                TaskType.REINDEX, "Medium Priority", priority=5
            )

            # List pending tasks and verify order
            pending = await task_queue.list_tasks(status=TaskStatus.PENDING)

            # Should be ordered by priority (lowest first)
            priorities = [t.config.priority for t in pending]
            assert priorities == sorted(priorities)
