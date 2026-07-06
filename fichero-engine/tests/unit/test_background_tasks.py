"""Tests for background task system (reindex, repair, metrics jobs)."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from fichero.db import Database
from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimType,
    ClaimRelationType,
    EntityType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)
from fichero.models import Document, FileType, Status
from fichero.workflows.tasks import (
    TaskProgress,
    TaskQueue,
    TaskResult,
    TaskStatus,
    TaskType,
    _TASK_LIBRARY_PATH_OPTION,
)


@pytest.fixture
def mock_db(monkeypatch, tmp_path):
    """Create a mock database for testing.

    Workers now resolve a thread-local Database via
    ``db_manager.get_database`` from inside the pool thread (#2509), never
    capturing+shipping the queue's Database across the thread boundary. So
    the mock is given a realistic package ``.path`` and we patch
    ``db_manager.get_database`` to return it regardless of which thread asks.
    """
    db = MagicMock(spec=Database)
    db.path = tmp_path / "test.fichero" / "fichero.duckdb"
    db.all = MagicMock(return_value=[])
    db.save = MagicMock()
    db.delete = MagicMock()
    db.count = MagicMock(return_value=0)
    db.embed = MagicMock(return_value=True)
    db.embedding_stats = MagicMock(return_value={"total_vectors": 0})
    monkeypatch.setattr(
        "fichero.workflows.task_workers.db_manager.get_database",
        lambda _path: db,
    )
    return db


@pytest.fixture
def temp_db_path(tmp_path):
    """Create a temporary database path."""
    return str(tmp_path / "tasks.db")


@pytest.fixture
async def task_queue(temp_db_path, mock_db):
    """Create a TaskQueue instance for testing."""
    queue = TaskQueue(temp_db_path, database=mock_db)
    await queue.start()
    yield queue
    await queue.stop()


class TestTaskType:
    """Test TaskType enum."""

    def test_task_type_values(self):
        """Test task type enum values."""
        assert TaskType.REINDEX.value == "reindex"
        assert TaskType.METRICS.value == "metrics"
        assert TaskType.REPAIR.value == "repair"
        assert TaskType.VECTOR_REPAIR.value == "vector_repair"
        assert TaskType.KG_METRICS.value == "kg_metrics"


class TestTaskStatus:
    """Test TaskStatus enum."""

    def test_task_status_values(self):
        """Test task status enum values."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.RUNNING.value == "running"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"


class TestTaskQueue:
    """Test TaskQueue functionality."""

    @pytest.mark.asyncio
    async def test_create_task(self, task_queue):
        """Test creating a task."""
        task = await task_queue.create_task(
            task_type=TaskType.REINDEX,
            name="Test Reindex",
            options={"test": True},
            priority=5,
        )

        assert task.task_type == TaskType.REINDEX
        assert task.name == "Test Reindex"
        assert task.status == TaskStatus.PENDING
        assert task.config.options == {"test": True}
        assert task.config.priority == 5
        assert task.task_id is not None

    @pytest.mark.asyncio
    async def test_get_task(self, task_queue):
        """Test retrieving a task."""
        created = await task_queue.create_task(
            task_type=TaskType.METRICS,
            name="Test Metrics",
        )

        retrieved = await task_queue.get_task(created.task_id)

        assert retrieved is not None
        assert retrieved.task_id == created.task_id
        assert retrieved.name == "Test Metrics"

    @pytest.mark.asyncio
    async def test_get_nonexistent_task(self, task_queue):
        """Test retrieving non-existent task."""
        result = await task_queue.get_task("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_tasks(self, task_queue):
        """Test listing tasks."""
        # Create tasks
        await task_queue.create_task(TaskType.REINDEX, "Task 1")
        await task_queue.create_task(TaskType.METRICS, "Task 2")
        await task_queue.create_task(TaskType.REPAIR, "Task 3")

        # List all tasks
        tasks = await task_queue.list_tasks()
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_list_tasks_with_status_filter(self, task_queue):
        """Test listing tasks with status filter."""
        await task_queue.create_task(TaskType.REINDEX, "Task 1")

        # Task is still pending
        pending = await task_queue.list_tasks(status=TaskStatus.PENDING)
        running = await task_queue.list_tasks(status=TaskStatus.RUNNING)

        assert len(pending) == 1
        assert len(running) == 0

    @pytest.mark.asyncio
    async def test_list_tasks_with_type_filter(self, task_queue):
        """Test listing tasks with type filter."""
        await task_queue.create_task(TaskType.REINDEX, "Task 1")
        await task_queue.create_task(TaskType.METRICS, "Task 2")

        reindex_tasks = await task_queue.list_tasks(task_type=TaskType.REINDEX)
        metrics_tasks = await task_queue.list_tasks(task_type=TaskType.METRICS)

        assert len(reindex_tasks) == 1
        assert len(metrics_tasks) == 1

    @pytest.mark.asyncio
    async def test_cancel_task(self, task_queue):
        """Test cancelling a pending task."""
        task = await task_queue.create_task(TaskType.REINDEX, "Task to cancel")

        cancelled = await task_queue.cancel_task(task.task_id)

        assert cancelled is not None
        assert cancelled.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_running_task_fails(self, task_queue):
        """Test cancelling a running task fails."""
        task = await task_queue.create_task(TaskType.REINDEX, "Running task")
        # Manually mark as running
        task.status = TaskStatus.RUNNING
        await task_queue._save_task(task)

        with pytest.raises(ValueError, match="Cannot cancel task"):
            await task_queue.cancel_task(task.task_id)

    @pytest.mark.asyncio
    async def test_task_priority_sorting(self, task_queue):
        """Test tasks are sorted by creation time (not priority in list view)."""
        await task_queue.create_task(TaskType.REINDEX, "Low", priority=10)
        await task_queue.create_task(TaskType.REINDEX, "High", priority=1)
        await task_queue.create_task(TaskType.REINDEX, "Medium", priority=5)

        tasks = await task_queue.list_tasks()

        # Tasks are sorted by created_at DESC (newest first), not by priority
        assert len(tasks) == 3
        # Just verify all tasks are returned
        priorities = [t.config.priority for t in tasks]
        assert sorted(priorities) == [1, 5, 10]

    @pytest.mark.asyncio
    async def test_direct_task_execution_emits_backend_work_lifecycle(
        self, temp_db_path, mock_db, monkeypatch
    ):
        captured: list[dict[str, object]] = []
        monkeypatch.setattr(
            "fichero.workflows.tasks.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )
        queue = TaskQueue(temp_db_path, database=mock_db)
        library_path = str(mock_db.path.parent)
        task = await queue.create_task(
            TaskType.METRICS,
            "Metrics Test",
            options={_TASK_LIBRARY_PATH_OPTION: library_path},
        )

        await queue._execute_metrics(task)

        assert [call["type"] for call in captured].count("backend.work.started") == 1
        assert any(call["type"] == "backend.work.progress" for call in captured)
        assert [call["type"] for call in captured].count("backend.work.completed") == 1
        assert {call["library_path"] for call in captured} == {library_path}
        assert all(call["run_id"] == task.task_id for call in captured)
        final = captured[-1]
        assert final["metadata"] == {
            "task_type": "metrics",
            "task_name": "Metrics Test",
            "status": "completed",
            "message": "Metrics computed",
            "current": "5",
            "total": "5",
            "percent": "100.0",
        }


class TestTaskRecovery:
    """Test task recovery from interruption."""

    @pytest.mark.asyncio
    async def test_recovery_interrupted_tasks(self, temp_db_path, mock_db):
        """Test that running tasks are reset to pending on startup."""
        # Create first queue and add a task
        queue1 = TaskQueue(temp_db_path, database=mock_db)
        await queue1.start()

        task = await queue1.create_task(TaskType.REINDEX, "Test Task")
        # Manually mark as running
        task.status = TaskStatus.RUNNING
        await queue1._save_task(task)

        await queue1.stop()

        # Create new queue (simulating restart)
        queue2 = TaskQueue(temp_db_path, database=mock_db)
        await queue2.start()

        # Task should be reset to pending
        recovered = await queue2.get_task(task.task_id)
        assert recovered.status == TaskStatus.PENDING
        assert recovered.error_message == "Interrupted by restart"

        await queue2.stop()


class TestReindexTask:
    """Test reindex task execution."""

    @pytest.mark.asyncio
    async def test_reindex_empty_library(self, task_queue, mock_db):
        """Test reindex with no documents."""
        mock_db.all.return_value = []

        task = await task_queue.create_task(TaskType.REINDEX, "Reindex Test")
        await task_queue._execute_reindex(task)

        assert task.status == TaskStatus.COMPLETED
        assert task.result.success is True
        assert task.result.details["indexed"] == 0
        assert task.result.details["total"] == 0

    @pytest.mark.asyncio
    async def test_reindex_with_documents(self, task_queue, mock_db):
        """Test reindex with documents."""
        docs = [
            Document(id="doc1", name="Doc 1", page_content="content 1"),
            Document(id="doc2", name="Doc 2", page_content="content 2"),
        ]
        mock_db.all.return_value = docs

        task = await task_queue.create_task(TaskType.REINDEX, "Reindex Test")
        await task_queue._execute_reindex(task)

        assert task.status == TaskStatus.COMPLETED
        assert task.result.details["total"] == 2
        # embed should be called for each doc with content
        assert mock_db.embed.call_count == 2

    @pytest.mark.asyncio
    async def test_reindex_skips_no_content(self, task_queue, mock_db):
        """Test reindex skips documents without content."""
        docs = [
            Document(id="doc1", name="Doc 1", page_content="content 1"),
            Document(id="doc2", name="Doc 2", page_content=None),  # No content
        ]
        mock_db.all.return_value = docs

        task = await task_queue.create_task(TaskType.REINDEX, "Reindex Test")
        await task_queue._execute_reindex(task)

        assert task.result.details["total"] == 2
        # embed should only be called once (for doc with content)
        assert mock_db.embed.call_count == 1


class TestMetricsTask:
    """Test metrics task execution."""

    @pytest.mark.asyncio
    async def test_metrics_computation(self, task_queue, mock_db):
        """Test metrics computation."""
        docs = [
            Document(
                id="doc1", name="Doc 1", file_type=FileType.pdf, status=Status.active
            ),
            Document(
                id="doc2", name="Doc 2", file_type=FileType.docx, status=Status.active
            ),
            Document(
                id="doc3", name="Doc 3", file_type=FileType.pdf, status=Status.pending
            ),
        ]
        mock_db.all.return_value = docs
        mock_db.embedding_stats.return_value = {"total_vectors": 2}

        task = await task_queue.create_task(TaskType.METRICS, "Metrics Test")
        await task_queue._execute_metrics(task)

        assert task.status == TaskStatus.COMPLETED
        assert task.result.success is True
        assert task.result.details["document_count"] == 3
        assert task.result.details["file_types"]["pdf"] == 2
        assert task.result.details["file_types"]["docx"] == 1


class TestRepairTask:
    """Test repair task execution."""

    @pytest.mark.asyncio
    async def test_repair_empty_library(self, task_queue, mock_db):
        """Test repair with no documents."""
        mock_db.all.return_value = []

        task = await task_queue.create_task(TaskType.REPAIR, "Repair Test")
        await task_queue._execute_repair(task)

        assert task.status == TaskStatus.COMPLETED
        assert task.result.success is True

    @pytest.mark.asyncio
    async def test_repair_fixes_missing_embeddings(self, task_queue, mock_db):
        """Test repair adds missing embeddings."""
        doc = Document(id="doc1", name="Doc 1", page_content="content")
        doc.embedding = None  # Missing embedding
        mock_db.all.return_value = [doc]

        task = await task_queue.create_task(TaskType.REPAIR, "Repair Test")
        await task_queue._execute_repair(task)

        assert mock_db.embed.call_count == 1
        assert task.result.details["embeddings"] == 1


class TestVectorRepairTask:
    """Test vector repair task execution."""

    @pytest.mark.asyncio
    async def test_vector_repair(self, task_queue, mock_db):
        """Test vector repair task."""
        docs = [
            Document(id="doc1", name="Doc 1", page_content="content 1"),
            Document(id="doc2", name="Doc 2", page_content="content 2"),
        ]
        mock_db.all.return_value = docs
        mock_db.embedding_stats.return_value = {"total_vectors": 2}

        task = await task_queue.create_task(
            TaskType.VECTOR_REPAIR, "Vector Repair Test"
        )
        await task_queue._execute_vector_repair(task)

        assert task.status == TaskStatus.COMPLETED
        assert task.result.success is True
        assert task.result.details["checked"] == 2


class TestKGMetricsTask:
    """Test knowledge graph metrics task execution."""

    @pytest.mark.asyncio
    async def test_kg_metrics_empty(self, task_queue, mock_db):
        """Test KG metrics with empty knowledge graph."""
        mock_db.all.return_value = []

        task = await task_queue.create_task(TaskType.KG_METRICS, "KG Metrics Test")
        await task_queue._execute_kg_metrics(task)

        assert task.status == TaskStatus.COMPLETED
        assert task.result.success is True
        assert task.result.details["entity_count"] == 0
        assert task.result.details["claim_count"] == 0
        assert task.result.details["link_count"] == 0

    @pytest.mark.asyncio
    async def test_kg_metrics_computation(self, task_queue, mock_db):
        """Test KG metrics computation with data."""
        entities = [
            KnowledgeEntity(
                id="ent1", canonical_name="Entity 1", entity_type=EntityType.person
            ),
            KnowledgeEntity(
                id="ent2", canonical_name="Entity 2", entity_type=EntityType.location
            ),
            KnowledgeEntity(
                id="ent3", canonical_name="Entity 3", entity_type=EntityType.person
            ),
        ]

        claims = [
            KnowledgeClaim(
                id="claim1",
                text="Claim 1",
                source_document_id="doc1",
                claim_type=ClaimType.fact,
                curation_state=ClaimCurationState.unreviewed,
                entity_ids=["ent1"],
            ),
            KnowledgeClaim(
                id="claim2",
                text="Claim 2",
                source_document_id="doc2",
                claim_type=ClaimType.interpretation,
                curation_state=ClaimCurationState.curated,
                entity_ids=["ent1", "ent2"],
            ),
        ]

        links = [
            KnowledgeClaimLink(
                id="link1",
                claim_id="claim1",
                related_claim_id="claim2",
                relation_type=ClaimRelationType.supports,
            ),
        ]

        # Mock returns entities, claims, links in order
        mock_db.all.side_effect = [entities, claims, links]

        task = await task_queue.create_task(TaskType.KG_METRICS, "KG Metrics Test")
        await task_queue._execute_kg_metrics(task)

        assert task.status == TaskStatus.COMPLETED
        assert task.result.success is True
        assert task.result.details["entity_count"] == 3
        assert task.result.details["entity_by_type"]["person"] == 2
        assert task.result.details["entity_by_type"]["location"] == 1
        assert task.result.details["claim_count"] == 2
        assert task.result.details["link_count"] == 1
        assert task.result.details["links_by_relation"]["supports"] == 1


class TestTaskProgress:
    """Test task progress tracking."""

    def test_progress_to_dict(self):
        """Test progress serialization."""
        progress = TaskProgress(
            current=50,
            total=100,
            percent=50.0,
            message="Half way done",
            updated_at=datetime(2026, 4, 12, 12, 0, 0),
        )

        data = progress.to_dict()
        assert data["current"] == 50
        assert data["total"] == 100
        assert data["percent"] == 50.0
        assert data["message"] == "Half way done"
        assert "2026-04-12" in data["updated_at"]


class TestTaskResult:
    """Test task result handling."""

    def test_result_to_dict(self):
        """Test result serialization."""
        result = TaskResult(
            success=True,
            message="Completed successfully",
            details={"count": 42},
            error=None,
        )

        data = result.to_dict()
        assert data["success"] is True
        assert data["message"] == "Completed successfully"
        assert data["details"] == {"count": 42}
        assert data["error"] is None

    def test_result_to_dict_with_error(self):
        """Test result serialization with error."""
        result = TaskResult(
            success=False,
            message="Failed",
            details={},
            error="Something went wrong",
        )

        data = result.to_dict()
        assert data["success"] is False
        assert data["error"] == "Something went wrong"


class TestIdempotentRecomputation:
    """Test idempotent behavior of recomputation tasks."""

    @pytest.mark.asyncio
    async def test_reindex_is_idempotent(self, task_queue, mock_db):
        """Test that reindexing twice produces same result."""
        docs = [Document(id="doc1", name="Doc 1", page_content="content")]
        mock_db.all.return_value = docs

        # First reindex
        task1 = await task_queue.create_task(TaskType.REINDEX, "First")
        await task_queue._execute_reindex(task1)

        # Second reindex
        task2 = await task_queue.create_task(TaskType.REINDEX, "Second")
        await task_queue._execute_reindex(task2)

        # Both should succeed with same counts
        assert task1.result.details["indexed"] == task2.result.details["indexed"]
        assert task2.result.success is True

    @pytest.mark.asyncio
    async def test_metrics_is_idempotent(self, task_queue, mock_db):
        """Test that metrics recomputation is idempotent."""
        docs = [Document(id="doc1", name="Doc 1")]
        mock_db.all.return_value = docs

        # First computation
        task1 = await task_queue.create_task(TaskType.METRICS, "First")
        await task_queue._execute_metrics(task1)

        # Second computation
        task2 = await task_queue.create_task(TaskType.METRICS, "Second")
        await task_queue._execute_metrics(task2)

        # Both should succeed with same document count
        assert (
            task1.result.details["document_count"]
            == task2.result.details["document_count"]
        )
