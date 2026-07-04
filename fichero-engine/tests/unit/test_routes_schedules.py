"""Tests for schedule routes.

Schedules trigger workflow executions on cron/interval/one-time basis.
Uses APScheduler under the hood (dev-tier feature). Tests mock the scheduler
dependency to avoid APScheduler installation requirements.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fichero.api.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_mock_schedule(schedule_id: str = "sched-1") -> MagicMock:
    s = MagicMock()
    s.schedule_id = schedule_id
    s.name = "Test Schedule"
    s.workflow_id = "wf-1"
    s.config = MagicMock()
    s.config.schedule_type = MagicMock(value="interval")
    s.config.cron_expression = None
    s.config.interval_seconds = 3600
    s.config.run_at = None
    s.config.timezone = "UTC"
    s.config.start_date = None
    s.config.end_date = None
    s.config.max_runs = None
    s.status = MagicMock(value="active")
    s.inputs = {}
    s.use_batch = False
    s.batch_items = []
    s.max_concurrent = 5
    s.created_at = datetime.now()
    s.updated_at = datetime.now()
    s.last_run_at = None
    s.next_run_at = None
    s.run_count = 0
    s.error_message = None
    return s


def _make_mock_scheduler(schedules: list | None = None):
    scheduler = AsyncMock()
    scheduler.start = AsyncMock()
    scheduler.create_schedule = AsyncMock(return_value=_make_mock_schedule())
    scheduler.list_schedules = AsyncMock(return_value=schedules or [])
    scheduler.get_schedule = AsyncMock(return_value=_make_mock_schedule())
    scheduler.delete_schedule = AsyncMock()
    scheduler.update_schedule = AsyncMock(return_value=_make_mock_schedule())
    scheduler.pause_schedule = AsyncMock(return_value=_make_mock_schedule())
    scheduler.resume_schedule = AsyncMock(return_value=_make_mock_schedule())
    run_mock = MagicMock()
    run_mock.run_id = "run-1"
    run_mock.schedule_id = "sched-1"
    run_mock.status = "completed"
    run_mock.started_at = datetime.now()
    run_mock.completed_at = datetime.now()
    run_mock.error = None
    run_mock.batch_id = None
    scheduler.trigger_now = AsyncMock(return_value=run_mock)
    scheduler.get_schedule_runs = AsyncMock(return_value=[])
    return scheduler


@pytest.fixture
def mock_scheduler(client):
    """Override scheduler dependency with a mock."""
    from fichero.api.routes.schedules import get_scheduler
    mock = _make_mock_scheduler()
    app.dependency_overrides[get_scheduler] = lambda: mock
    yield mock
    # Restore
    app.dependency_overrides.pop(get_scheduler, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListSchedules:
    def test_list_returns_empty(self, client, mock_scheduler):
        mock_scheduler.list_schedules.return_value = []
        r = client.get("/api/schedules")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_list_returns_schedules(self, client, mock_scheduler):
        mock_scheduler.list_schedules.return_value = [_make_mock_schedule("s1"), _make_mock_schedule("s2")]
        r = client.get("/api/schedules")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 2


class TestCreateSchedule:
    def test_create_interval_schedule(self, client, mock_scheduler):
        payload = {
            "name": "Hourly Run",
            "workflow_id": "wf-abc",
            "config": {
                "schedule_type": "interval",
                "interval_seconds": 3600,
                "timezone": "UTC",
            },
            "inputs": {},
        }
        r = client.post("/api/schedules", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Test Schedule"
        assert data["schedule_id"] == "sched-1"

    def test_create_cron_schedule(self, client, mock_scheduler):
        payload = {
            "name": "Daily",
            "workflow_id": "wf-abc",
            "config": {
                "schedule_type": "cron",
                "cron_expression": "0 9 * * 1",
                "timezone": "UTC",
            },
        }
        r = client.post("/api/schedules", json=payload)
        assert r.status_code == 200


class TestGetSchedule:
    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_get_existing_schedule(self, client, mock_scheduler):
        r = client.get("/api/schedules/sched-1")
        assert r.status_code == 200
        assert r.json()["items"]["schedule_id"] == "sched-1"

    def test_get_returns_404_when_none(self, client, mock_scheduler):
        mock_scheduler.get_schedule.return_value = None
        r = client.get("/api/schedules/no-such-id")
        assert r.status_code == 404


class TestDeleteSchedule:
    def test_delete_schedule(self, client, mock_scheduler):
        r = client.delete("/api/schedules/sched-1")
        assert r.status_code == 200

    def test_delete_missing_returns_404(self, client, mock_scheduler):
        mock_scheduler.get_schedule.return_value = None
        r = client.delete("/api/schedules/missing")
        assert r.status_code == 404


class TestPauseResumeSchedule:
    def test_pause_schedule(self, client, mock_scheduler):
        r = client.post("/api/schedules/sched-1/pause")
        assert r.status_code == 200

    def test_resume_schedule(self, client, mock_scheduler):
        r = client.post("/api/schedules/sched-1/resume")
        assert r.status_code == 200

    def test_pause_missing_returns_400(self, client, mock_scheduler):
        mock_scheduler.pause_schedule.side_effect = ValueError("not found")
        r = client.post("/api/schedules/bad-id/pause")
        assert r.status_code == 400


class TestTriggerSchedule:
    def test_trigger_now(self, client, mock_scheduler):
        r = client.post("/api/schedules/sched-1/trigger")
        assert r.status_code == 200

    def test_trigger_missing_returns_400(self, client, mock_scheduler):
        mock_scheduler.trigger_now.side_effect = ValueError("not found")
        r = client.post("/api/schedules/bad-id/trigger")
        assert r.status_code == 400


class TestScheduleRuns:
    def test_get_runs_empty(self, client, mock_scheduler):
        mock_scheduler.get_schedule_runs.return_value = []
        r = client.get("/api/schedules/sched-1/runs")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_get_runs_missing_schedule_returns_404(self, client, mock_scheduler):
        mock_scheduler.get_schedule.return_value = None
        r = client.get("/api/schedules/bad-id/runs")
        assert r.status_code == 404


class TestScheduleOpenAPISchema:
    def test_schedule_schema_uses_typed_maps_and_list_items(self, client):
        schema = client.app.openapi()
        create_request = schema["components"]["schemas"]["CreateScheduleRequest"]
        update_request = schema["components"]["schemas"]["UpdateScheduleRequest"]
        schedule_response = schema["components"]["schemas"]["ScheduleResponse"]
        schedule_list = schema["components"]["schemas"]["ScheduleResponseList"]
        runs_list = schema["components"]["schemas"]["ScheduleRunResponseList"]

        assert create_request["properties"]["inputs"]["additionalProperties"]["type"] == "string"
        assert (
            create_request["properties"]["batch_items"]["items"]["additionalProperties"]["type"]
            == "string"
        )
        assert update_request["properties"]["inputs"]["anyOf"][0]["additionalProperties"]["type"] == "string"
        assert (
            update_request["properties"]["batch_items"]["anyOf"][0]["items"]["additionalProperties"]["type"]
            == "string"
        )
        assert schedule_response["properties"]["inputs"]["additionalProperties"]["type"] == "string"
        assert (
            schedule_response["properties"]["batch_items"]["items"]["additionalProperties"]["type"]
            == "string"
        )
        assert schedule_list["properties"]["items"]["items"]["$ref"].endswith("/ScheduleResponse")
        assert runs_list["properties"]["items"]["items"]["$ref"].endswith("/ScheduleRunResponse")
