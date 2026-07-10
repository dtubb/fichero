"""
Tests for Activity API routes.

Tests the activity tracking endpoints including:
- List activities with filtering
- Recent activities
- Activity statistics
- Workflow/batch specific activities
- Activity cleanup
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from fichero.workflows.activity import (
    Activity,
    ActivityLevel,
    ActivityStats,
    ActivityTracker,
    ActivityType,
)


@pytest.fixture
def sample_activities():
    """Create sample activity items for testing."""
    now = datetime.now()
    return [
        Activity(
            id="act-1",
            type=ActivityType.WORKFLOW_STARTED,
            level=ActivityLevel.INFO,
            message="Workflow 'Test' started",
            timestamp=now - timedelta(hours=1),
            workflow_id="wf-1",
            thread_id="thread-1",
        ),
        Activity(
            id="act-2",
            type=ActivityType.NODE_COMPLETED,
            level=ActivityLevel.INFO,
            message="Node 'describe' completed",
            timestamp=now - timedelta(minutes=30),
            workflow_id="wf-1",
            thread_id="thread-1",
            node_id="describe",
            duration_ms=1500.0,
        ),
        Activity(
            id="act-3",
            type=ActivityType.WORKFLOW_COMPLETED,
            level=ActivityLevel.INFO,
            message="Workflow 'Test' completed",
            timestamp=now - timedelta(minutes=25),
            workflow_id="wf-1",
            thread_id="thread-1",
            metadata={"nodes_completed": 3, "total_results": 5},
        ),
        Activity(
            id="act-4",
            type=ActivityType.WORKFLOW_FAILED,
            level=ActivityLevel.ERROR,
            message="Workflow 'Failed' failed",
            timestamp=now - timedelta(minutes=10),
            workflow_id="wf-2",
            thread_id="thread-2",
            error="Connection timeout",
        ),
    ]


class TestActivityEndpoints:
    """Tests for /api/activity endpoints."""

    def test_list_activities(self, client, db, sample_activities):
        """List activities returns array of activity items."""
        # Mock the activity tracker
        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.query = AsyncMock(return_value=sample_activities)
            mock_tracker.return_value = mock_instance

            response = client.get("/api/activity")
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, dict)
            assert "items" in data
            assert "count" in data
            assert len(data["items"]) == 4
            assert data["count"] == 4

    def test_list_activities_with_type_filter(self, client, db, sample_activities):
        """List activities with type filter."""
        completed_activities = [a for a in sample_activities if a.type == ActivityType.WORKFLOW_COMPLETED]

        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.query = AsyncMock(return_value=completed_activities)
            mock_tracker.return_value = mock_instance

            response = client.get("/api/activity?types=workflow_completed")
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["type"] == "workflow_completed"

    def test_list_activities_with_level_filter(self, client, db, sample_activities):
        """List activities with level filter."""
        error_activities = [a for a in sample_activities if a.level == ActivityLevel.ERROR]

        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.query = AsyncMock(return_value=error_activities)
            mock_tracker.return_value = mock_instance

            response = client.get("/api/activity?levels=error")
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["level"] == "error"

    def test_list_activities_with_workflow_filter(self, client, db, sample_activities):
        """List activities filtered by workflow ID."""
        wf1_activities = [a for a in sample_activities if a.workflow_id == "wf-1"]

        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.query = AsyncMock(return_value=wf1_activities)
            mock_tracker.return_value = mock_instance

            response = client.get("/api/activity?workflow_id=wf-1")
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 3
            assert all(item["workflow_id"] == "wf-1" for item in data["items"])

    def test_list_activities_with_time_filter(self, client, db, sample_activities):
        """List activities with time range filter."""
        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.query = AsyncMock(return_value=sample_activities[:2])
            mock_tracker.return_value = mock_instance

            since = (datetime.now() - timedelta(hours=2)).isoformat()
            until = (datetime.now() - timedelta(minutes=20)).isoformat()
            response = client.get(f"/api/activity?since={since}&until={until}")
            assert response.status_code == 200

    def test_list_activities_invalid_type(self, client, db):
        """List activities with invalid type returns 400."""
        response = client.get("/api/activity?types=invalid_type")
        assert response.status_code == 400

    def test_list_activities_invalid_level(self, client, db):
        """List activities with invalid level returns 400."""
        response = client.get("/api/activity?levels=invalid_level")
        assert response.status_code == 400

    def test_recent_activities(self, client, db, sample_activities):
        """Get recent activities from memory buffer."""
        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.get_recent = MagicMock(return_value=sample_activities[:2])
            mock_tracker.return_value = mock_instance

            response = client.get("/api/activity/recent?limit=2")
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 2
            assert data["count"] == 2

    def test_activity_stats(self, client, db):
        """Get activity statistics."""
        mock_stats = ActivityStats(
            total_activities=100,
            activities_by_type={"workflow_completed": 50, "workflow_failed": 10},
            activities_by_level={"info": 80, "error": 20},
            error_count=20,
            warning_count=5,
            avg_workflow_duration_ms=5000.0,
            success_rate=0.83,
            period_start=datetime.now() - timedelta(hours=24),
            period_end=datetime.now(),
        )

        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.get_stats = AsyncMock(return_value=mock_stats)
            mock_tracker.return_value = mock_instance

            response = client.get("/api/activity/stats?hours=24")
            assert response.status_code == 200
            data = response.json()
            assert data["total_activities"] == 100
            assert data["error_count"] == 20
            assert data["success_rate"] == 0.83

    def test_get_workflow_activity(self, client, db, sample_activities):
        """Get activities for specific workflow."""
        wf1_activities = [a for a in sample_activities if a.workflow_id == "wf-1"]

        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.query = AsyncMock(return_value=wf1_activities)
            mock_tracker.return_value = mock_instance

            response = client.get("/api/activity/workflow/wf-1")
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 3
            assert data["count"] == 3

    def test_get_batch_activity(self, client, db):
        """Get activities for specific batch."""
        batch_activity = Activity(
            id="act-batch-1",
            type=ActivityType.BATCH_STARTED,
            level=ActivityLevel.INFO,
            message="Batch started",
            timestamp=datetime.now(),
            batch_id="batch-1",
        )

        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.query = AsyncMock(return_value=[batch_activity])
            mock_tracker.return_value = mock_instance

            response = client.get("/api/activity/batch/batch-1")
            assert response.status_code == 200
            data = response.json()
            assert len(data["items"]) == 1
            assert data["items"][0]["batch_id"] == "batch-1"

    def test_cleanup_old_activities(self, client, db):
        """Delete old activities."""
        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.store = MagicMock()
            mock_instance.store.delete_old_sync.return_value = 50
            mock_tracker.return_value = mock_instance

            response = client.delete("/api/activity/cleanup?days=30")
            assert response.status_code == 200
            data = response.json()
            assert data["deleted"] == 50


class TestActivityResponse:
    """Tests for ActivityResponse model."""

    def test_response_metadata_converts_to_strings(self, client, db):
        """Activity response converts metadata values to strings."""
        activity = Activity(
            id="act-meta",
            type=ActivityType.WORKFLOW_COMPLETED,
            level=ActivityLevel.INFO,
            message="Test with metadata",
            timestamp=datetime.now(),
            workflow_id="wf-1",
            metadata={
                "nodes_completed": 5,  # int
                "duration": 1.5,  # float
                "success": True,  # bool
                "name": "test",  # string
            },
        )

        with patch("fichero.api.routes.activity.get_activity_tracker") as mock_tracker:
            mock_instance = MagicMock()
            mock_instance.query = AsyncMock(return_value=[activity])
            mock_tracker.return_value = mock_instance

            response = client.get("/api/activity")
            assert response.status_code == 200
            data = response.json()

            # All metadata values should be strings
            metadata = data["items"][0]["metadata"]
            assert metadata["nodes_completed"] == "5"
            assert metadata["duration"] == "1.5"
            assert metadata["success"] == "True"
            assert metadata["name"] == "test"


class TestActivityTrackerIntegration:
    """Integration tests for ActivityTracker with database.

    Note: ActivityTracker.log() uses asyncio.create_task() internally for
    fire-and-forget database saves. In production this works with FastAPI's
    event loop. For tests, we patch create_task to avoid event loop issues.
    """

    @pytest.fixture
    def tracker(self, test_package):
        """Create an ActivityTracker for the test package."""
        # ActivityTracker expects the db file path, not the package directory
        db_path = test_package / "fichero.duckdb"
        return ActivityTracker(str(db_path))

    @pytest.fixture
    def mock_create_task(self):
        """Mock asyncio.create_task to avoid event loop issues in sync tests.

        The ActivityTracker.log() method uses fire-and-forget async tasks.
        We mock create_task to just run the coroutine synchronously for testing.
        """
        created_tasks = []

        def mock_task(coro):
            """Store the coroutine for later execution, don't actually create a task."""
            created_tasks.append(coro)
            # Return a mock that looks like a task
            mock = MagicMock()
            mock.done.return_value = False
            return mock

        with patch("asyncio.create_task", side_effect=mock_task):
            yield created_tasks

        # Clean up any unawaited coroutines to avoid warnings
        for coro in created_tasks:
            coro.close()

    def test_log_activity_stores_in_memory(self, tracker, mock_create_task):
        """Log activity stores in recent memory buffer."""
        # Log an activity
        tracker.workflow_started("wf-test", "thread-test", "Test Workflow")

        # Should be in memory buffer
        recent = tracker.get_recent(10)
        assert len(recent) >= 1
        assert any(a.workflow_id == "wf-test" for a in recent)

    def test_log_workflow_lifecycle_in_memory(self, tracker, mock_create_task):
        """Log complete workflow lifecycle stores all events in memory."""
        workflow_id = "wf-lifecycle"
        thread_id = "thread-lifecycle"

        # Log workflow lifecycle
        tracker.workflow_started(workflow_id, thread_id, "Lifecycle Test")
        tracker.node_started(workflow_id, thread_id, "node-1", "Test Node")
        tracker.node_completed(workflow_id, thread_id, "node-1", "Test Node", 1000.0)
        tracker.workflow_completed(workflow_id, thread_id, "Lifecycle Test", 2000.0)

        # Check all events are in memory
        recent = tracker.get_recent(100)
        types = [a.type for a in recent if a.workflow_id == workflow_id]

        assert ActivityType.WORKFLOW_STARTED in types
        assert ActivityType.NODE_STARTED in types
        assert ActivityType.NODE_COMPLETED in types
        assert ActivityType.WORKFLOW_COMPLETED in types

    def test_log_error_activity(self, tracker, mock_create_task):
        """Log error activity with correct level."""
        tracker.workflow_failed("wf-error", "thread-error", "Error Test", "Connection error")

        recent = tracker.get_recent(10)
        error_activities = [a for a in recent if a.level == ActivityLevel.ERROR]

        assert len(error_activities) >= 1
        assert error_activities[0].error == "Connection error"

    def test_recent_activities_limit(self, tracker, mock_create_task):
        """Get recent activities respects limit parameter."""
        # Log several activities
        for i in range(5):
            tracker.workflow_started(f"wf-{i}", f"thread-{i}", f"Workflow {i}")

        # Get limited recent
        recent = tracker.get_recent(3)
        assert len(recent) == 3

    def test_activity_types_correct(self, tracker, mock_create_task):
        """Activity types are set correctly for different events."""
        tracker.workflow_started("wf-1", "t-1", "Test")
        tracker.node_started("wf-1", "t-1", "node-1", "Node")
        tracker.node_completed("wf-1", "t-1", "node-1", "Node", 100.0)
        tracker.workflow_completed("wf-1", "t-1", "Test", 500.0)
        tracker.workflow_failed("wf-2", "t-2", "Failed", "error")

        recent = tracker.get_recent(10)
        types = {a.type for a in recent}

        assert ActivityType.WORKFLOW_STARTED in types
        assert ActivityType.NODE_STARTED in types
        assert ActivityType.NODE_COMPLETED in types
        assert ActivityType.WORKFLOW_COMPLETED in types
        assert ActivityType.WORKFLOW_FAILED in types
