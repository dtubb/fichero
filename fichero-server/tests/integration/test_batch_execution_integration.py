"""
Integration tests for Batch Execution System.

Tests batch execution with multiple workflow items including:
- Batch creation and execution
- Progress tracking
- Pause/resume/cancel operations
- Error handling
- Activity logging integration
"""

import uuid
from datetime import datetime

import pytest

# Test the batch module
from fichero_server.execution.batch import (
    BatchItemStatus,
    BatchManager,
    BatchStatus,
)
from fichero_server.workflows.activity import (
    Activity,
    ActivityFilter,
    ActivityLevel,
    ActivityStore,
    ActivityTracker,
    ActivityType,
)


class TestBatchExecution:
    """Test batch execution functionality."""

    @pytest.fixture
    def db_path(self, tmp_path):
        """Create a temporary database path."""
        return str(tmp_path / "test_batch.duckdb")

    @pytest.fixture
    def batch_manager(self, db_path):
        """Create a batch manager for testing."""
        return BatchManager(db_path)

    @pytest.mark.asyncio
    async def test_create_batch(self, batch_manager):
        """Test creating a new batch."""
        workflow_id = str(uuid.uuid4())
        items_inputs = [
            {"file": "doc1.txt", "prompt": "Summarize"},
            {"file": "doc2.txt", "prompt": "Summarize"},
            {"file": "doc3.txt", "prompt": "Summarize"},
        ]

        batch = await batch_manager.create_batch(
            workflow_id=workflow_id,
            items_inputs=items_inputs,
            max_concurrent=2,
        )

        assert batch.batch_id is not None
        assert batch.workflow_id == workflow_id
        assert batch.status == BatchStatus.PENDING
        assert batch.total_items == 3
        assert batch.max_concurrent == 2
        assert len(batch.items) == 3
        for i, item in enumerate(batch.items):
            assert item.item_index == i
            assert item.status == BatchItemStatus.PENDING
            assert item.inputs == items_inputs[i]

    @pytest.mark.asyncio
    async def test_get_batch(self, batch_manager):
        """Test retrieving a batch by ID."""
        workflow_id = str(uuid.uuid4())
        items_inputs = [{"file": "test.txt"}]

        created_batch = await batch_manager.create_batch(
            workflow_id=workflow_id,
            items_inputs=items_inputs,
        )

        retrieved_batch = await batch_manager.get_batch(created_batch.batch_id)

        assert retrieved_batch is not None
        assert retrieved_batch.batch_id == created_batch.batch_id
        assert retrieved_batch.workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_list_batches(self, batch_manager):
        """Test listing batches."""
        workflow_id = str(uuid.uuid4())

        # Create multiple batches
        batch1 = await batch_manager.create_batch(workflow_id, [{"id": 1}])
        batch2 = await batch_manager.create_batch(workflow_id, [{"id": 2}])
        batch3 = await batch_manager.create_batch(workflow_id, [{"id": 3}])

        batches = await batch_manager.list_batches(limit=10)

        assert len(batches) >= 3
        batch_ids = [b.batch_id for b in batches]
        assert batch1.batch_id in batch_ids
        assert batch2.batch_id in batch_ids
        assert batch3.batch_id in batch_ids

    @pytest.mark.asyncio
    async def test_batch_progress(self, batch_manager):
        """Test batch progress calculation."""
        workflow_id = str(uuid.uuid4())
        items_inputs = [
            {"file": "doc1.txt"},
            {"file": "doc2.txt"},
            {"file": "doc3.txt"},
            {"file": "doc4.txt"},
        ]

        batch = await batch_manager.create_batch(
            workflow_id=workflow_id,
            items_inputs=items_inputs,
        )

        # Initial progress
        progress = batch.get_progress()
        assert progress.total_items == 4
        assert progress.completed_items == 0
        assert progress.progress_percent == 0.0

        # Simulate some completion
        batch.items[0].status = BatchItemStatus.COMPLETED
        batch.items[0].started_at = datetime.now()
        batch.items[0].completed_at = datetime.now()
        batch.items[1].status = BatchItemStatus.FAILED

        progress = batch.get_progress()
        assert progress.completed_items == 1
        assert progress.failed_items == 1
        assert progress.progress_percent == 25.0  # 1/4 completed

    @pytest.mark.asyncio
    async def test_cancel_batch(self, batch_manager):
        """Test cancelling a batch."""
        workflow_id = str(uuid.uuid4())
        batch = await batch_manager.create_batch(workflow_id, [{"id": 1}, {"id": 2}])

        cancelled_batch = await batch_manager.cancel_batch(batch.batch_id)

        assert cancelled_batch.status == BatchStatus.CANCELLED
        for item in cancelled_batch.items:
            assert item.status == BatchItemStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_delete_batch(self, batch_manager):
        """Test deleting a batch."""
        workflow_id = str(uuid.uuid4())
        batch = await batch_manager.create_batch(workflow_id, [{"id": 1}])

        await batch_manager.delete_batch(batch.batch_id)

        # Batch should no longer exist
        retrieved = await batch_manager.get_batch(batch.batch_id)
        assert retrieved is None


class TestActivityTracking:
    """Test activity tracking functionality."""

    @pytest.fixture
    def db_path(self, tmp_path):
        """Create a temporary database path."""
        return str(tmp_path / "test_activity.duckdb")

    @pytest.fixture
    def activity_store(self, db_path):
        """Create an activity store for testing."""
        return ActivityStore(db_path)

    @pytest.fixture
    def activity_tracker(self, db_path):
        """Create an activity tracker for testing."""
        return ActivityTracker(db_path)

    @pytest.mark.asyncio
    async def test_save_and_query_activity(self, activity_store):
        """Test saving and querying activities."""
        activity = Activity(
            id=str(uuid.uuid4()),
            type=ActivityType.WORKFLOW_STARTED,
            level=ActivityLevel.INFO,
            timestamp=datetime.now(),
            message="Test workflow started",
            workflow_id="wf-123",
        )

        await activity_store.save(activity)

        # Query by workflow ID
        filter = ActivityFilter(workflow_id="wf-123")
        results = await activity_store.query(filter)

        assert len(results) == 1
        assert results[0].id == activity.id
        assert results[0].workflow_id == "wf-123"

    @pytest.mark.asyncio
    async def test_query_by_type(self, activity_store):
        """Test querying activities by type."""
        # Create activities of different types
        for activity_type in [
            ActivityType.WORKFLOW_STARTED,
            ActivityType.WORKFLOW_COMPLETED,
            ActivityType.NODE_STARTED,
        ]:
            activity = Activity(
                id=str(uuid.uuid4()),
                type=activity_type,
                level=ActivityLevel.INFO,
                timestamp=datetime.now(),
                message=f"Test {activity_type.value}",
            )
            await activity_store.save(activity)

        # Query only workflow events
        filter = ActivityFilter(
            types=[ActivityType.WORKFLOW_STARTED, ActivityType.WORKFLOW_COMPLETED]
        )
        results = await activity_store.query(filter)

        assert len(results) == 2
        for result in results:
            assert result.type in [ActivityType.WORKFLOW_STARTED, ActivityType.WORKFLOW_COMPLETED]

    @pytest.mark.asyncio
    async def test_query_by_level(self, activity_store):
        """Test querying activities by level."""
        # Create activities of different levels
        for level in [ActivityLevel.INFO, ActivityLevel.ERROR, ActivityLevel.WARNING]:
            activity = Activity(
                id=str(uuid.uuid4()),
                type=ActivityType.SYSTEM_INFO,
                level=level,
                timestamp=datetime.now(),
                message=f"Test {level.value}",
            )
            await activity_store.save(activity)

        # Query only errors
        filter = ActivityFilter(levels=[ActivityLevel.ERROR])
        results = await activity_store.query(filter)

        assert len(results) == 1
        assert results[0].level == ActivityLevel.ERROR

    @pytest.mark.asyncio
    async def test_activity_stats(self, activity_store):
        """Test activity statistics."""
        # Create various activities
        for i in range(5):
            await activity_store.save(Activity(
                id=str(uuid.uuid4()),
                type=ActivityType.WORKFLOW_COMPLETED,
                level=ActivityLevel.INFO,
                timestamp=datetime.now(),
                message=f"Workflow {i} completed",
                duration_ms=1000 + i * 100,
            ))

        for i in range(2):
            await activity_store.save(Activity(
                id=str(uuid.uuid4()),
                type=ActivityType.WORKFLOW_FAILED,
                level=ActivityLevel.ERROR,
                timestamp=datetime.now(),
                message=f"Workflow {i} failed",
                error="Test error",
            ))

        stats = await activity_store.get_stats()

        assert stats.total_activities >= 7
        assert ActivityType.WORKFLOW_COMPLETED.value in stats.activities_by_type
        assert ActivityType.WORKFLOW_FAILED.value in stats.activities_by_type
        assert stats.error_count >= 2
        # Success rate: 5 completed / 7 total workflows = ~71%
        assert stats.success_rate > 0

    @pytest.mark.asyncio
    async def test_activity_tracker_log(self, activity_tracker):
        """Test logging activities through the tracker."""
        activity = activity_tracker.log(
            type=ActivityType.BATCH_STARTED,
            message="Batch started",
            batch_id="batch-123",
            metadata={"total_items": 10},
        )

        assert activity.id is not None
        assert activity.type == ActivityType.BATCH_STARTED
        assert activity.batch_id == "batch-123"
        assert activity.metadata["total_items"] == 10

    @pytest.mark.asyncio
    async def test_activity_tracker_convenience_methods(self, activity_tracker):
        """Test convenience methods for common activity types."""
        workflow_id = "wf-456"
        thread_id = "thread-789"

        # Test workflow started
        started = activity_tracker.workflow_started(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name="Test Workflow",
        )
        assert started.type == ActivityType.WORKFLOW_STARTED
        assert started.workflow_id == workflow_id

        # Test workflow completed
        completed = activity_tracker.workflow_completed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name="Test Workflow",
            duration_ms=5000,
        )
        assert completed.type == ActivityType.WORKFLOW_COMPLETED
        assert completed.duration_ms == 5000

        # Test workflow failed
        failed = activity_tracker.workflow_failed(
            workflow_id=workflow_id,
            thread_id=thread_id,
            workflow_name="Test Workflow",
            error="Test error",
        )
        assert failed.type == ActivityType.WORKFLOW_FAILED
        assert failed.error == "Test error"

    def test_activity_to_dict(self):
        """Test activity serialization."""
        activity = Activity(
            id="act-123",
            type=ActivityType.NODE_COMPLETED,
            level=ActivityLevel.DEBUG,
            timestamp=datetime.now(),
            message="Node completed",
            workflow_id="wf-1",
            node_id="node-1",
            duration_ms=500,
        )

        data = activity.to_dict()

        assert data["id"] == "act-123"
        assert data["type"] == "node_completed"
        assert data["level"] == "debug"
        assert data["workflow_id"] == "wf-1"
        assert data["node_id"] == "node-1"
        assert data["duration_ms"] == 500

    def test_activity_from_dict(self):
        """Test activity deserialization."""
        data = {
            "id": "act-456",
            "type": "batch_completed",
            "level": "info",
            "timestamp": datetime.now().isoformat(),
            "message": "Batch done",
            "batch_id": "batch-1",
            "metadata": {"items": 10},
        }

        activity = Activity.from_dict(data)

        assert activity.id == "act-456"
        assert activity.type == ActivityType.BATCH_COMPLETED
        assert activity.level == ActivityLevel.INFO
        assert activity.batch_id == "batch-1"
        assert activity.metadata["items"] == 10


class TestBatchActivityIntegration:
    """Test integration between batch execution and activity tracking."""

    @pytest.fixture
    def db_path(self, tmp_path):
        """Create a temporary database path."""
        return str(tmp_path / "test_integration.duckdb")

    @pytest.fixture
    def batch_manager(self, db_path):
        """Create a batch manager for testing."""
        return BatchManager(db_path)

    @pytest.fixture
    def activity_store(self, db_path):
        """Create an activity store for testing."""
        return ActivityStore(db_path)

    @pytest.mark.asyncio
    async def test_batch_with_activity_logging(self, batch_manager, activity_store):
        """Test that batch operations can be logged to activity store."""
        workflow_id = str(uuid.uuid4())
        batch = await batch_manager.create_batch(
            workflow_id=workflow_id,
            items_inputs=[{"id": 1}, {"id": 2}],
        )

        # Log batch creation directly to store (manager also creates BATCH_CREATED)
        activity = Activity(
            id=str(uuid.uuid4()),
            type=ActivityType.BATCH_CREATED,
            level=ActivityLevel.INFO,
            timestamp=datetime.now(),
            message=f"Batch {batch.batch_id} created",
            batch_id=batch.batch_id,
            workflow_id=workflow_id,
            metadata={"total_items": batch.total_items},
        )
        await activity_store.save(activity)

        # create_batch()'s BATCH_CREATED activity is logged via
        # ActivityTracker.log(), which schedules its DB write as a
        # fire-and-forget background task (no ordering guarantee vs. an
        # immediate follow-up query). Wait for it to land before asserting.
        await batch_manager.activity_tracker.wait_for_pending_saves()

        # Query activities for this batch
        filter = ActivityFilter(batch_id=batch.batch_id)
        activities = await activity_store.query(filter)

        assert len(activities) == 2  # 1 from manager + 1 from test
        assert any(a.type == ActivityType.BATCH_CREATED for a in activities)

    @pytest.mark.asyncio
    async def test_batch_item_completion_logging(self, activity_store):
        """Test logging individual batch item completions."""
        batch_id = str(uuid.uuid4())

        # Simulate batch item completions - save directly to store
        for i in range(3):
            activity = Activity(
                id=str(uuid.uuid4()),
                type=ActivityType.BATCH_ITEM_COMPLETED,
                level=ActivityLevel.DEBUG,
                timestamp=datetime.now(),
                message=f"Batch item {i} completed",
                batch_id=batch_id,
                thread_id=f"thread-{i}",
                duration_ms=1000 + i * 100,
                metadata={"item_index": i},
            )
            await activity_store.save(activity)

        # Log a failure
        failed_activity = Activity(
            id=str(uuid.uuid4()),
            type=ActivityType.BATCH_ITEM_FAILED,
            level=ActivityLevel.ERROR,
            timestamp=datetime.now(),
            message="Batch item 3 failed: Processing error",
            batch_id=batch_id,
            thread_id="thread-3",
            error="Processing error",
            metadata={"item_index": 3},
        )
        await activity_store.save(failed_activity)

        # Query all activities for this batch
        filter = ActivityFilter(batch_id=batch_id)
        activities = await activity_store.query(filter)

        assert len(activities) == 4
        completed = [a for a in activities if a.type == ActivityType.BATCH_ITEM_COMPLETED]
        failed = [a for a in activities if a.type == ActivityType.BATCH_ITEM_FAILED]
        assert len(completed) == 3
        assert len(failed) == 1

    @pytest.mark.asyncio
    async def test_batch_progress_with_activity(self, batch_manager, activity_store):
        """Test batch progress tracking alongside activity logging."""
        workflow_id = str(uuid.uuid4())
        batch = await batch_manager.create_batch(
            workflow_id=workflow_id,
            items_inputs=[{"id": i} for i in range(5)],
        )

        # Log batch start
        start_activity = Activity(
            id=str(uuid.uuid4()),
            type=ActivityType.BATCH_STARTED,
            level=ActivityLevel.INFO,
            timestamp=datetime.now(),
            message=f"Batch started with {batch.total_items} items",
            batch_id=batch.batch_id,
            workflow_id=workflow_id,
            metadata={"total_items": batch.total_items},
        )
        await activity_store.save(start_activity)

        # Simulate progress
        for i in range(3):
            batch.items[i].status = BatchItemStatus.COMPLETED
            batch.items[i].started_at = datetime.now()
            batch.items[i].completed_at = datetime.now()

            item_activity = Activity(
                id=str(uuid.uuid4()),
                type=ActivityType.BATCH_ITEM_COMPLETED,
                level=ActivityLevel.DEBUG,
                timestamp=datetime.now(),
                message=f"Batch item {i} completed",
                batch_id=batch.batch_id,
                thread_id=batch.items[i].thread_id,
                duration_ms=500,
                metadata={"item_index": i},
            )
            await activity_store.save(item_activity)

        # Check progress
        progress = batch.get_progress()
        assert progress.completed_items == 3
        assert progress.progress_percent == 60.0

        # Log batch completion
        complete_activity = Activity(
            id=str(uuid.uuid4()),
            type=ActivityType.BATCH_COMPLETED,
            level=ActivityLevel.INFO,
            timestamp=datetime.now(),
            message=f"Batch completed: 3/{batch.total_items} successful, 0 failed",
            batch_id=batch.batch_id,
            workflow_id=workflow_id,
            duration_ms=5000,
            metadata={
                "total_items": batch.total_items,
                "completed_items": 3,
                "failed_items": 0,
            },
        )
        await activity_store.save(complete_activity)

        # Verify all activities logged
        filter = ActivityFilter(batch_id=batch.batch_id)
        activities = await activity_store.query(filter)

        assert len(activities) == 6  # 1 created + 1 start + 3 items + 1 completion
