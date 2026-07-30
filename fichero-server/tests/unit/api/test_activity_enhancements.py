"""Unit tests for activity stream enhancements (Issue #425)."""

from datetime import datetime

from fichero_server.api.routes.system.activity import (
    ActivityFeedResponse,
    ActivityFeedGroup,
    ActivityTrendsResponse,
    TrendPoint,
    TopEntitiesResponse,
    TopEntity,
    ActivityMetricsSummary,
    ActivityResponse,
)
from fichero_server.workflows.activity import Activity, ActivityType, ActivityLevel
class TestActivityFeedResponse:
    """Test activity feed response models."""

    def test_feed_response_basic(self):
        """Test basic feed response creation."""
        activity = Activity(
            id="act-1",
            type=ActivityType.WORKFLOW_STARTED,
            level=ActivityLevel.INFO,
            timestamp=datetime.now(),
            message="Workflow started",
            workflow_id="wf-1",
        )
        response = ActivityResponse.from_activity(activity)

        feed = ActivityFeedResponse(
            activities=[response],
            groups=[],
            total=1,
            has_more=False,
        )
        assert feed.total == 1
        assert not feed.has_more

    def test_feed_group_creation(self):
        """Test feed group creation."""
        now = datetime.now()
        activity = Activity(
            id="act-1",
            type=ActivityType.WORKFLOW_STARTED,
            level=ActivityLevel.INFO,
            timestamp=now,
            message="Workflow started",
            workflow_id="wf-1",
            metadata={"workflow_name": "Test Workflow"},
        )
        response = ActivityResponse.from_activity(activity)

        group = ActivityFeedGroup(
            entity_type="workflow",
            entity_id="wf-1",
            entity_name="Test Workflow",
            count=1,
            last_activity=now.isoformat(),
            activities=[response],
        )
        assert group.entity_type == "workflow"
        assert group.entity_id == "wf-1"
        assert group.entity_name == "Test Workflow"
        assert group.count == 1
class TestActivityTrendsResponse:
    """Test activity trends response models."""

    def test_trends_response_creation(self):
        """Test trends response creation."""
        points = [
            TrendPoint(
                timestamp="2024-01-15T10:00:00",
                count=5,
                error_count=0,
                workflow_count=2,
                batch_count=3,
            ),
            TrendPoint(
                timestamp="2024-01-15T11:00:00",
                count=8,
                error_count=1,
                workflow_count=3,
                batch_count=4,
            ),
        ]

        trends = ActivityTrendsResponse(
            period="hourly",
            points=points,
            total_activities=13,
            total_errors=1,
        )
        assert trends.period == "hourly"
        assert len(trends.points) == 2
        assert trends.total_activities == 13
        assert trends.total_errors == 1

    def test_trend_point_validation(self):
        """Test trend point field types."""
        point = TrendPoint(
            timestamp="2024-01-15T10:00:00",
            count=10,
            error_count=2,
            workflow_count=3,
            batch_count=5,
        )
        assert point.count == 10
        assert point.error_count == 2
        assert point.workflow_count == 3
        assert point.batch_count == 5
class TestTopEntitiesResponse:
    """Test top entities response models."""

    def test_top_entities_response(self):
        """Test top entities response creation."""
        now = datetime.now().isoformat()
        workflows = [
            TopEntity(
                entity_type="workflow",
                entity_id="wf-1",
                entity_name="Import Workflow",
                activity_count=50,
                error_count=2,
                last_activity=now,
                success_rate=96.0,
            ),
            TopEntity(
                entity_type="workflow",
                entity_id="wf-2",
                entity_name="Analysis Workflow",
                activity_count=30,
                error_count=0,
                last_activity=now,
                success_rate=100.0,
            ),
        ]
        batches = [
            TopEntity(
                entity_type="batch",
                entity_id="batch-1",
                entity_name="Document Batch",
                activity_count=100,
                error_count=5,
                last_activity=now,
                success_rate=95.0,
            ),
        ]

        response = TopEntitiesResponse(
            workflows=workflows,
            batches=batches,
            time_range_hours=24,
        )
        assert len(response.workflows) == 2
        assert len(response.batches) == 1
        assert response.time_range_hours == 24

    def test_top_entity_fields(self):
        """Test top entity field values."""
        now = datetime.now().isoformat()
        entity = TopEntity(
            entity_type="workflow",
            entity_id="wf-1",
            entity_name="Test Workflow",
            activity_count=25,
            error_count=1,
            last_activity=now,
            success_rate=95.0,
        )
        assert entity.entity_type == "workflow"
        assert entity.activity_count == 25
        assert entity.success_rate == 95.0
class TestActivityMetricsSummary:
    """Test activity metrics summary model."""

    def test_metrics_summary_creation(self):
        """Test metrics summary creation."""
        now = datetime.now().isoformat()
        metrics = ActivityMetricsSummary(
            total_activities=100,
            total_workflows=10,
            total_batches=5,
            error_count=3,
            warning_count=10,
            success_rate=97.0,
            avg_workflow_duration_ms=1500.0,
            avg_batch_duration_ms=5000.0,
            busiest_hour=14,
            period_start=now,
            period_end=now,
        )
        assert metrics.total_activities == 100
        assert metrics.total_workflows == 10
        assert metrics.total_batches == 5
        assert metrics.error_count == 3
        assert metrics.success_rate == 97.0
        assert metrics.avg_workflow_duration_ms == 1500.0
        assert metrics.avg_batch_duration_ms == 5000.0
        assert metrics.busiest_hour == 14

    def test_metrics_summary_optional_fields(self):
        """Test metrics summary with optional fields as None."""
        now = datetime.now().isoformat()
        metrics = ActivityMetricsSummary(
            total_activities=50,
            total_workflows=0,
            total_batches=0,
            error_count=0,
            warning_count=0,
            success_rate=100.0,
            avg_workflow_duration_ms=None,
            avg_batch_duration_ms=None,
            busiest_hour=None,
            period_start=now,
            period_end=now,
        )
        assert metrics.avg_workflow_duration_ms is None
        assert metrics.avg_batch_duration_ms is None
        assert metrics.busiest_hour is None
class TestActivityResponse:
    """Test activity response conversion."""

    def test_activity_response_from_activity(self):
        """Test converting Activity to ActivityResponse."""
        activity = Activity(
            id="act-123",
            type=ActivityType.WORKFLOW_COMPLETED,
            level=ActivityLevel.INFO,
            timestamp=datetime.now(),
            message="Workflow completed successfully",
            workflow_id="wf-1",
            batch_id="batch-1",
            thread_id="thread-1",
            node_id="node-1",
            metadata={"workflow_name": "Test"},
            duration_ms=1500.0,
            error=None,
        )

        response = ActivityResponse.from_activity(activity)
        assert response.id == "act-123"
        assert response.type == "workflow_completed"
        assert response.level == "info"
        assert response.workflow_id == "wf-1"
        assert response.duration_ms == 1500.0

    def test_activity_response_with_error(self):
        """Test activity response with error."""
        activity = Activity(
            id="act-456",
            type=ActivityType.WORKFLOW_FAILED,
            level=ActivityLevel.ERROR,
            timestamp=datetime.now(),
            message="Workflow failed",
            workflow_id="wf-1",
            error="Connection timeout",
        )

        response = ActivityResponse.from_activity(activity)
        assert response.type == "workflow_failed"
        assert response.level == "error"
        assert response.error == "Connection timeout"

    def test_activity_response_metadata_conversion(self):
        """Test that metadata values are converted to strings."""
        activity = Activity(
            id="act-789",
            type=ActivityType.NODE_COMPLETED,
            level=ActivityLevel.DEBUG,
            timestamp=datetime.now(),
            message="Node completed",
            metadata={
                "count": 42,
                "flag": True,
                "value": None,
            },
        )

        response = ActivityResponse.from_activity(activity)
        assert response.metadata["count"] == "42"
        assert response.metadata["flag"] == "True"
        assert response.metadata["value"] is None
