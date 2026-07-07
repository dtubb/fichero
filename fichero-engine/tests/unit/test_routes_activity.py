"""Tests for activity tracking routes.

Activity tracks workflow/batch events per library. Routes query historical
activities, recent events, stats, and cleanup. Tests mock get_activity_tracker
to avoid needing a real activity DB.
"""

import asyncio
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fichero.api import change_stream
from fichero.api.change_stream import _ChangeHub, emit_change
from fichero.api.routes import activity as activity_routes

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
    tracker.subscribe.return_value = "sub-1"
    tracker.unsubscribe = MagicMock()
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
        assert r.json()["items"] == []
        assert r.json()["count"] == 0

    def test_returns_activities(self, client):
        act = _make_mock_activity()
        tracker = _make_mock_tracker([act])
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.get("/api/activity")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1
        assert r.json()["items"][0]["id"] == "act-1"

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

    def test_since_z_is_normalized_for_query_filter(self, client):
        tracker = _make_mock_tracker()
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.get("/api/activity?since=2026-05-16T14:32:06Z")
        assert r.status_code == 200
        assert tracker.query.await_count == 1
        filter_arg = tracker.query.await_args.args[0]
        assert filter_arg.since is not None
        assert filter_arg.since.tzinfo is None


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
        assert len(r.json()["items"]) == 1


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
# GET /api/activity/stream
# ---------------------------------------------------------------------------


class TestActivityStream:
    @pytest.mark.asyncio
    async def test_stream_yields_activity_response_sse_shape(self):
        from fichero.api.routes.activity import stream_activities

        act = _make_mock_activity(
            activity_id="act-stream-1",
            activity_type="workflow_completed",
            message="Workflow completed",
        )
        act.thread_id = "thread-1"
        tracker = _make_mock_tracker([act])

        async def stream(sub_id, filter):
            assert sub_id == "sub-1"
            assert filter.workflow_id is None
            yield act

        tracker.stream = stream
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            response = await stream_activities(
                db=MagicMock(path="/tmp/test.fichero"),
                types=None,
                levels=None,
            )

        chunk = await anext(response.body_iterator)
        assert chunk.startswith("data: ")
        assert '"type":"workflow_completed"' in chunk
        assert '"thread_id":"thread-1"' in chunk
        await response.body_iterator.aclose()
        tracker.unsubscribe.assert_called_once_with("sub-1")

    @pytest.mark.asyncio
    async def test_stream_yields_workflow_started_events(self):
        from fichero.api.routes.activity import stream_activities

        act = _make_mock_activity(
            activity_id="act-started-1",
            activity_type="workflow_started",
            message="Workflow started",
        )
        act.thread_id = "thread-started-1"
        tracker = _make_mock_tracker([act])

        async def stream(sub_id, filter):
            yield act

        tracker.stream = stream
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            response = await stream_activities(
                db=MagicMock(path="/tmp/test.fichero"),
                types=None,
                levels=None,
            )

        chunk = await anext(response.body_iterator)
        assert '"type":"workflow_started"' in chunk
        assert '"thread_id":"thread-started-1"' in chunk
        await response.body_iterator.aclose()

    @pytest.mark.asyncio
    async def test_stream_yields_change_events_for_current_library(self, monkeypatch):
        from fichero.api.routes.activity import stream_activities

        tracker = _make_mock_tracker([])

        async def stream(_sub_id, _filter):
            await asyncio.Future()
            yield None  # pragma: no cover

        tracker.stream = stream
        test_hub = _ChangeHub()
        monkeypatch.setattr(change_stream, "_change_hub", test_hub)
        monkeypatch.setattr(activity_routes, "_change_hub", test_hub)

        library_path = "/tmp/test-activity.fichero"
        db = MagicMock(path=Path(library_path) / "fichero.duckdb")
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            response = await stream_activities(db=db, types=None, levels=None)

        try:
            emit_change(
                library_path,
                type="backend.work.progress",
                run_id="task-1",
                actor="system",
                metadata={"task_type": "metrics", "percent": "40.0"},
            )
            chunk = await anext(response.body_iterator)
        finally:
            await response.body_iterator.aclose()

        assert '"type":"system_info"' in chunk
        assert '"message":"backend.work.progress changed"' in chunk
        assert '"change_type":"backend.work.progress"' in chunk
        assert '"actor":"system"' in chunk
        assert '"run_id":"task-1"' in chunk
        assert '"change_metadata":"' in chunk
        assert 'task_type' in chunk
        assert 'metrics' in chunk

    @pytest.mark.asyncio
    async def test_stream_ignores_other_library_change_events(self, monkeypatch):
        from fichero.api.routes.activity import stream_activities

        tracker = _make_mock_tracker([])

        async def stream(_sub_id, _filter):
            await asyncio.Future()
            yield None  # pragma: no cover

        tracker.stream = stream
        test_hub = _ChangeHub()
        monkeypatch.setattr(change_stream, "_change_hub", test_hub)
        monkeypatch.setattr(activity_routes, "_change_hub", test_hub)
        monkeypatch.setattr(activity_routes, "_KEEPALIVE_TIMEOUT", 0.01)

        library_path = "/tmp/test-activity.fichero"
        other_library_path = "/tmp/other-activity.fichero"
        db = MagicMock(path=Path(library_path) / "fichero.duckdb")
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            response = await stream_activities(db=db, types=None, levels=None)

        try:
            emit_change(
                other_library_path,
                type="document.updated",
                document_ids=["doc-2"],
                actor="remote-device",
            )
            chunk = await anext(response.body_iterator)
        finally:
            await response.body_iterator.aclose()

        assert chunk == ": keepalive\n\n"


# ---------------------------------------------------------------------------
# DELETE /api/activity/cleanup
# ---------------------------------------------------------------------------


class TestActivityCleanup:
    def test_cleanup_returns_deleted_count(self, client):
        tracker = _make_mock_tracker()
        tracker.store.delete_old_sync = MagicMock(return_value=42)
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.delete("/api/activity/cleanup")
        assert r.status_code == 200
        data = r.json()
        assert data["deleted"] == 42
        assert "older_than" in data

    def test_cleanup_writes_audit_row(self, client, db):
        """Cleanup route goes through registry.invoke and writes an ActionAudit row."""
        tracker = _make_mock_tracker()
        tracker.store.delete_old_sync = MagicMock(return_value=10)
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.delete("/api/activity/cleanup?days=7")
        assert r.status_code == 200
        data = r.json()
        assert data["deleted"] == 10
        # Verify the audit row was written
        from fichero.models import ActionAudit
        audits = db.query(ActionAudit)
        activity_audits = [a for a in audits if a.action_name == "activity.cleanup"]
        assert len(activity_audits) == 1
        audit = activity_audits[0]
        assert audit.params["days"] == 7

    def test_cleanup_default_days(self, client, db):
        """Default days=30 when not specified."""
        tracker = _make_mock_tracker()
        tracker.store.delete_old_sync = MagicMock(return_value=5)
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.delete("/api/activity/cleanup")
        assert r.status_code == 200
        data = r.json()
        assert data["deleted"] == 5
        from fichero.models import ActionAudit
        audits = db.query(ActionAudit)
        activity_audits = [a for a in audits if a.action_name == "activity.cleanup"]
        assert len(activity_audits) == 1
        assert activity_audits[0].params["days"] == 30

    def test_cleanup_emits_change_event(self, client, db, monkeypatch):
        """Cleanup route emits activity.updated change event."""
        calls = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )
        tracker = _make_mock_tracker()
        tracker.store.delete_old_sync = MagicMock(return_value=3)
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r = client.delete("/api/activity/cleanup?days=14")
        assert r.status_code == 200
        # Verify change event was emitted
        assert len(calls) == 1
        _args, kwargs = calls[0]
        assert kwargs["type"] == "activity.updated"

    def test_cleanup_days_bounds(self, client):
        """Days parameter must be 1-365."""
        tracker = _make_mock_tracker()
        with patch("fichero.api.routes.activity.get_activity_tracker", return_value=tracker):
            r0 = client.delete("/api/activity/cleanup?days=0")
            assert r0.status_code in (400, 422)
            r366 = client.delete("/api/activity/cleanup?days=366")
            assert r366.status_code in (400, 422)


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
        assert "items" in r.json()
        assert len(r.json()["items"]) >= 1
