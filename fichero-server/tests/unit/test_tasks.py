"""Unit tests for background task system.

Tests cover:
- TaskQueue functionality
- Task creation and lifecycle
- Progress tracking
- Reindex task execution
- Metrics task execution
- API endpoints
"""

import pytest
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


class TestTaskQueue:
    """Test suite for TaskQueue class."""

    @pytest.fixture
    def temp_db_path(self, tmp_path):
        """Create temporary database path."""
        return str(tmp_path / "test_tasks.duckdb")

    @pytest.fixture
    async def task_queue(self, temp_db_path):
        """Create and start a TaskQueue for testing."""
        queue = TaskQueue(temp_db_path)
        await queue.start()
        yield queue
        await queue.stop()

    @pytest.mark.asyncio
    async def test_create_task(self, task_queue):
        """Test creating a background task."""
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
    async def test_get_task(self, task_queue):
        """Test retrieving a task by ID."""
        created = await task_queue.create_task(
            TaskType.METRICS,
            "Test Metrics",
        )

        retrieved = await task_queue.get_task(created.task_id)

        assert retrieved is not None
        assert retrieved.task_id == created.task_id
        assert retrieved.name == "Test Metrics"

    @pytest.mark.asyncio
    async def test_get_task_not_found(self, task_queue):
        """Test retrieving a non-existent task."""
        task = await task_queue.get_task("nonexistent-id")
        assert task is None

    @pytest.mark.asyncio
    async def test_list_tasks(self, task_queue):
        """Test listing tasks."""
        # Create multiple tasks
        await task_queue.create_task(TaskType.REINDEX, "Task 1")
        await task_queue.create_task(TaskType.METRICS, "Task 2")
        await task_queue.create_task(TaskType.REPAIR, "Task 3")

        tasks = await task_queue.list_tasks()

        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_list_tasks_with_filter(self, task_queue):
        """Test listing tasks with status filter by creating finished and pending tasks."""
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
        finished = [t for t in all_tasks if t.status not in (TaskStatus.PENDING, TaskStatus.RUNNING)]
        pending = [t for t in all_tasks if t.status == TaskStatus.PENDING]

        assert len(finished) >= 1
        assert len(pending) >= 1

    @pytest.mark.asyncio
    async def test_list_tasks_by_type(self, task_queue):
        """Test listing tasks with type filter."""
        await task_queue.create_task(TaskType.REINDEX, "Reindex Task")
        await task_queue.create_task(TaskType.REINDEX, "Another Reindex")
        await task_queue.create_task(TaskType.METRICS, "Metrics Task")

        reindex_tasks = await task_queue.list_tasks(task_type=TaskType.REINDEX)

        assert len(reindex_tasks) == 2

    @pytest.mark.asyncio
    async def test_cancel_task(self, task_queue):
        """Test cancelling a pending task."""
        task = await task_queue.create_task(TaskType.REINDEX, "To Cancel")

        cancelled = await task_queue.cancel_task(task.task_id)

        assert cancelled is not None
        assert cancelled.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_non_pending_task_fails(self, task_queue):
        """Test cancelling a non-pending task raises error."""
        task = await task_queue.create_task(TaskType.REINDEX, "To Cancel")
        await task_queue.cancel_task(task.task_id)

        with pytest.raises(ValueError, match="Cannot cancel"):
            await task_queue.cancel_task(task.task_id)

    @pytest.mark.asyncio
    async def test_delete_task(self, task_queue):
        """Test deleting a completed task."""
        task = await task_queue.create_task(TaskType.REINDEX, "To Delete")
        await task_queue.cancel_task(task.task_id)

        deleted = await task_queue.delete_task(task.task_id)

        assert deleted is True
        assert await task_queue.get_task(task.task_id) is None

    @pytest.mark.asyncio
    async def test_delete_running_task_fails(self, task_queue):
        """Test deleting a running task raises error."""
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

    @pytest.fixture
    async def task_queue(self, temp_db_path, mock_database):
        """Create TaskQueue with mock database."""
        queue = TaskQueue(temp_db_path, database=mock_database)
        await queue.start()
        yield queue
        await queue.stop()

    @pytest.mark.asyncio
    async def test_reindex_task_with_no_documents(self, task_queue, mock_database):
        """Test reindex task when there are no documents."""
        mock_database.all.return_value = []

        task = await task_queue.create_task(TaskType.REINDEX, "Empty Reindex")

        updated = await self.wait_for_completion(task_queue, task.task_id)
        assert updated.status == TaskStatus.COMPLETED
        assert updated.result is not None
        assert updated.result.success is True
        assert updated.result.details["indexed"] == 0
        assert updated.result.details["total"] == 0

    @pytest.mark.asyncio
    async def test_metrics_task_with_empty_database(self, task_queue, mock_database):
        """Test metrics task with empty database."""
        mock_database.all.return_value = []
        mock_database.embedding_stats.return_value = {"indexed": 0, "exists": False}

        task = await task_queue.create_task(TaskType.METRICS, "Empty Metrics")

        updated = await self.wait_for_completion(task_queue, task.task_id)
        assert updated.status == TaskStatus.COMPLETED
        assert updated.result is not None
        assert updated.result.details["document_count"] == 0

    @pytest.mark.asyncio
    async def test_repair_task_placeholder(self, task_queue):
        """Test repair task completes successfully."""
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

    @pytest.fixture
    async def task_queue(self, temp_db_path):
        """Create TaskQueue for priority testing."""
        queue = TaskQueue(temp_db_path)
        await queue.start()
        # Pause scheduler so tasks aren't picked up before the ordering assertion
        queue._scheduler.pause()
        yield queue
        queue._scheduler.resume()
        await queue.stop()

    @pytest.mark.asyncio
    async def test_tasks_ordered_by_priority(self, task_queue):
        """Test that tasks are processed in priority order."""
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
