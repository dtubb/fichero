"""Tests for activity tracking routes.

Activity tracks workflow/batch events per library. Routes query historical
activities, recent events, stats, and cleanup. Tests mock get_activity_tracker
to avoid needing a real activity DB.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fichero.workflows.activity import ActivityStats


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_activity(
    activity_id: str = "act-1",
    activity_type: str = "workflow_started",
    level: str = "info",
    message: str = "Test activity",
) -> MagicMock:
    act = MagicMock()
    act.id = activity_id
    act.type = MagicMock(value=activity_type)
    act.level = MagicMock(value=level)
    act.timestamp = datetime.now()
    act.message = message
    act.workflow_id = None
    act.batch_id = None
    act.thread_id = None
    act.node_id = None
    act.metadata = {}
    act.duration_ms = None
    act.error = None
    return act


def _make_mock_tracker(activities=None) -> MagicMock:
    tracker = MagicMock()
    tracker.query = AsyncMock(return_value=activities or [])
    tracker.get_recent.return_value = activities or []
    tracker.get_stats = AsyncMock(return_value=_make_mock_stats())
    tracker.cleanup = AsyncMock(return_value=0)
    # cleanup route calls tracker.store.delete_old(dt)
    tracker.store = MagicMock()
    tracker.store.delete_old = AsyncMock(return_value=0)
    return tracker


def _make_mock_stats() -> MagicMock:
    stats = MagicMock()
    stats.total_activities = 0
    stats.activities_by_type = {}
    stats.activities_by_level = {}
    stats.error_count = 0
    stats.warning_count = 0
    stats.avg_workflow_duration_ms = None
    stats.success_rate = 1.0
    stats.period_start = datetime.now()
    stats.period_end = datetime.now()
    return stats


# ---------------------------------------------------------------------------
# GET /api/activity — list
# ---------------------------------------------------------------------------


class TestListActivities:
    def test_returns_empty_list(self, client):
        tracker = _make_mock_tracker()
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.get("/api/activity")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_activities(self, client):
        act = _make_mock_activity()
        tracker = _make_mock_tracker([act])
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.get("/api/activity")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["id"] == "act-1"

    def test_invalid_activity_type_returns_400(self, client):
        tracker = _make_mock_tracker()
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.get("/api/activity?types=invalid_type")
        assert r.status_code == 400

    def test_invalid_level_returns_400(self, client):
        tracker = _make_mock_tracker()
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.get("/api/activity?levels=bogus")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/activity/recent
# ---------------------------------------------------------------------------


class TestGetRecentActivities:
    def test_returns_recent(self, client):
        act = _make_mock_activity()
        tracker = _make_mock_tracker([act])
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.get("/api/activity/recent")
        assert r.status_code == 200
        assert len(r.json()) == 1


# ---------------------------------------------------------------------------
# GET /api/activity/stats
# ---------------------------------------------------------------------------


class TestGetActivityStats:
    def test_returns_stats(self, client):
        tracker = _make_mock_tracker()
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.get("/api/activity/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total_activities" in data
        assert "error_count" in data
        assert "success_rate" in data


# ---------------------------------------------------------------------------
# DELETE /api/activity/cleanup
# ---------------------------------------------------------------------------


class TestActivityCleanup:
    def test_cleanup_returns_deleted_count(self, client):
        tracker = _make_mock_tracker()
        tracker.cleanup = AsyncMock(return_value=42)
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.delete("/api/activity/cleanup")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/activity/workflow/{workflow_id}
# ---------------------------------------------------------------------------


class TestWorkflowActivity:
    def test_returns_workflow_activities(self, client):
        act = _make_mock_activity()
        tracker = _make_mock_tracker([act])
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.get("/api/activity/workflow/wf-123")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
