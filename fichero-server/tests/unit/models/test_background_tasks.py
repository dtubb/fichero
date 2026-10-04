"""The task workers (reindex, metrics, repair, vector repair, KG metrics) and their data types.

The workers run as jobs (#5353): `task_workers._run_task_job` runs one on its host `_JobTask`. The
queue mechanics they used to sit in (`TaskQueue`, never started by the engine) are gone; the job
table's own tests cover queuing, durability and cancelling (tests/unit/jobs/test_tasks_on_the_lane.py).
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from fichero_server.db import Database
from fichero_server.models.knowledge import (
    ClaimCurationState,
    ClaimType,
    ClaimRelationType,
    EntityType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)
from fichero_server.models import Document, FileType, Status
from fichero_server.workflows.task_types import BackgroundTask, TaskConfig
from fichero_server.workflows.task_workers import _JobTask
from fichero_server.workflows.tasks import (
    TaskProgress,
    TaskResult,
    TaskStatus,
    TaskType,
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
        "fichero_server.workflows.task_workers.db_manager.get_database",
        lambda _path: db,
    )
    return db


class _Runner:
    """Runs a task's worker the way its job does (`task_workers._run_task_job`), on its real host."""

    def __init__(self, db):
        self.host = _JobTask(db, "job-1")

    async def create_task(self, task_type, name, options=None):
        return BackgroundTask(task_id="job-1", task_type=task_type, name=name, status=TaskStatus.RUNNING,
                              config=TaskConfig(task_type=task_type, options=options or {}))

    def __getattr__(self, name):
        if not name.startswith("_execute_"):
            raise AttributeError(name)
        worker = getattr(self.host, "_do_" + name[len("_execute_"):])

        async def run(task):
            task.result = await worker(task)
            task.status = TaskStatus.COMPLETED if task.result.success else TaskStatus.FAILED
            return task.result

        return run


@pytest.fixture
def task_queue(mock_db):
    """The workers' runner (named as the old queue was, so each test reads as it did)."""
    return _Runner(mock_db)


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
