"""Unit tests for the activity routes that survived the #3235 prune.

The #425 dashboard endpoints (/feed, /trends, /top) and the /ws duplicate
live transport were verified caller-less and deleted (#3235). These tests
cover what remains — the metrics summary model, the ActivityResponse
conversion — and pin the prune so the dead surface cannot quietly return.
"""

from datetime import datetime

from fichero_server.api.routes.system.activity import (
    ActivityMetricsSummary,
    ActivityResponse,
    router,
)
from fichero_server.workflows.activity import Activity, ActivityType, ActivityLevel


class TestPrunedEndpointsStayGone:
    """#3235: the orphaned endpoints must not reappear."""

    def test_pruned_paths_absent_from_router(self):
        paths = {route.path for route in router.routes}
        for gone in ("/ws", "/feed", "/trends", "/top", "/entity-types"):
            assert f"{router.prefix}{gone}" not in paths and gone not in paths, (
                f"{gone} was pruned in #3235 (no callers: app uses SSE "
                "/activity/stream; CLI top_entities uses /api/entities/top). "
                "Re-adding it needs a real client and a fresh decision."
            )

    def test_surviving_paths_still_present(self):
        # The read surface the app actually consumes must survive the prune.
        paths = {route.path for route in router.routes}
        for kept in (
            "/activity",
            "/activity/recent",
            "/activity/stats",
            "/activity/stream",
            "/activity/workflow/{workflow_id}",
            "/activity/batch/{batch_id}",
            "/activity/cleanup",
            "/activity/metrics/summary",
        ):
            assert kept in paths, f"{kept} unexpectedly missing from activity router"

    def test_pruned_models_are_gone(self):
        import fichero_server.api.routes.system.activity as module

        for name in (
            "ActivityFeedResponse",
            "ActivityFeedGroup",
            "ActivityTrendsResponse",
            "TrendPoint",
            "TopEntitiesResponse",
            "TopEntity",
            "websocket_activity_stream",
        ):
            assert not hasattr(module, name), f"{name} should have been pruned (#3235)"


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
