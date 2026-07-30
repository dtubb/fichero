"""Tests for file trigger routes.

File triggers watch directory paths and execute workflows when files change.
These are a dev-tier feature. Tests mock the FileWatcherManager dependency
since watchdog (the underlying library) may not be configured in all envs.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fichero_server.api.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_trigger(trigger_id: str = "trig-1") -> MagicMock:
    t = MagicMock()
    t.trigger_id = trigger_id
    t.name = "Test Trigger"
    t.workflow_id = "wf-1"
    t.config = MagicMock()
    t.config.watch_path = "/watch/path"
    t.config.recursive = True
    event_mock = MagicMock()
    event_mock.value = "created"
    t.config.events = [event_mock]
    t.config.filter_mode = MagicMock(value="glob")
    t.config.filter_pattern = None
    t.config.filter_extensions = []
    t.config.exclude_patterns = []
    t.config.debounce_seconds = 1.0
    t.config.batch_delay_seconds = 5.0
    t.inputs_template = {"file_path": "{file_path}"}
    t.status = MagicMock(value="active")
    t.use_batch = True
    t.max_concurrent = 5
    t.created_at = datetime.now()
    t.updated_at = datetime.now()
    t.last_triggered_at = None
    t.trigger_count = 0
    t.error_message = None
    return t


def _make_mock_watcher(triggers: list | None = None):
    w = AsyncMock()
    w.create_trigger = AsyncMock(return_value=_make_mock_trigger())
    w.list_triggers = AsyncMock(return_value=triggers or [])
    w.get_trigger = AsyncMock(return_value=_make_mock_trigger())
    w.delete_trigger = AsyncMock()
    w.update_trigger = AsyncMock(return_value=_make_mock_trigger())
    w.pause_trigger = AsyncMock(return_value=_make_mock_trigger())
    w.resume_trigger = AsyncMock(return_value=_make_mock_trigger())
    w.get_executions = AsyncMock(return_value=[])
    return w


@pytest.fixture
def mock_watcher(client):
    from fichero_server.api.routes.workflow.triggers import get_file_watcher
    mock = _make_mock_watcher()
    app.dependency_overrides[get_file_watcher] = lambda: mock
    yield mock
    app.dependency_overrides.pop(get_file_watcher, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListTriggers:
    def test_list_returns_empty(self, client, mock_watcher):
        mock_watcher.list_triggers.return_value = []
        r = client.get("/api/triggers")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_list_returns_triggers(self, client, mock_watcher):
        mock_watcher.list_triggers.return_value = [
            _make_mock_trigger("t1"),
            _make_mock_trigger("t2"),
        ]
        r = client.get("/api/triggers")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2


class TestCreateTrigger:
    def test_create_trigger_preserves_typed_response_boundaries(self, client, mock_watcher):
        trigger = _make_mock_trigger()
        trigger.config.filter_extensions = []
        trigger.config.exclude_patterns = []
        trigger.config.filter_pattern = None
        trigger.inputs_template = {
            "file_path": "{file_path}",
            "library_path": "{library_path}",
        }
        trigger.error_message = None
        mock_watcher.create_trigger.return_value = trigger

        payload = {
            "name": "Watch Inbox",
            "workflow_id": "wf-abc",
            "config": {
                "watch_path": "/Users/test/inbox",
                "recursive": True,
                "events": ["created"],
                "filter_mode": "glob",
                "filter_pattern": None,
                "filter_extensions": [],
                "exclude_patterns": [],
                "debounce_seconds": 1.0,
                "batch_delay_seconds": 5.0,
            },
            "inputs_template": {
                "file_path": "{file_path}",
                "library_path": "{library_path}",
            },
        }
        r = client.post("/api/triggers", json=payload)

        assert r.status_code == 200
        data = r.json()
        assert data["filter_pattern"] is None
        assert data["filter_extensions"] == []
        assert data["exclude_patterns"] == []
        assert data["last_triggered_at"] is None
        assert data["error_message"] is None
        assert data["inputs_template"] == {
            "file_path": "{file_path}",
            "library_path": "{library_path}",
        }

    def test_create_trigger(self, client, mock_watcher):
        payload = {
            "name": "Watch Inbox",
            "workflow_id": "wf-abc",
            "config": {
                "watch_path": "/Users/test/inbox",
                "recursive": True,
                "events": ["created"],
                "filter_mode": "glob",
                "filter_pattern": "*.pdf",
                "filter_extensions": [],
                "exclude_patterns": [],
                "debounce_seconds": 1.0,
                "batch_delay_seconds": 5.0,
            },
        }
        r = client.post("/api/triggers", json=payload)
        assert r.status_code == 200
        assert r.json()["trigger_id"] == "trig-1"


class TestGetTrigger:
    def test_get_existing_trigger(self, client, mock_watcher):
        r = client.get("/api/triggers/trig-1")
        assert r.status_code == 200
        assert r.json()["trigger_id"] == "trig-1"

    def test_get_missing_returns_404(self, client, mock_watcher):
        mock_watcher.get_trigger.return_value = None
        r = client.get("/api/triggers/no-such-id")
        assert r.status_code == 404


class TestDeleteTrigger:
    def test_delete_trigger(self, client, mock_watcher):
        r = client.delete("/api/triggers/trig-1")
        assert r.status_code == 200

    def test_delete_missing_returns_404(self, client, mock_watcher):
        mock_watcher.get_trigger.return_value = None
        r = client.delete("/api/triggers/no-such-id")
        assert r.status_code == 404


class TestPauseResumeTrigger:
    def test_pause_trigger(self, client, mock_watcher):
        r = client.post("/api/triggers/trig-1/pause")
        assert r.status_code == 200

    def test_resume_trigger(self, client, mock_watcher):
        r = client.post("/api/triggers/trig-1/resume")
        assert r.status_code == 200

    def test_pause_missing_returns_400(self, client, mock_watcher):
        mock_watcher.pause_trigger.side_effect = ValueError("not found")
        r = client.post("/api/triggers/bad-id/pause")
        assert r.status_code == 400


class TestTriggerExecutions:
    def test_get_executions_empty(self, client, mock_watcher):
        mock_watcher.get_executions.return_value = []
        r = client.get("/api/triggers/trig-1/executions")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_get_executions_missing_trigger_returns_404(self, client, mock_watcher):
        mock_watcher.get_trigger.return_value = None
        r = client.get("/api/triggers/bad-id/executions")
        assert r.status_code == 404


class TestTriggerOpenAPISchema:
    def test_trigger_schema_uses_typed_maps_and_list_items(self, client):
        schema = client.app.openapi()
        create_request = schema["components"]["schemas"]["CreateTriggerRequest"]
        update_request = schema["components"]["schemas"]["UpdateTriggerRequest"]
        trigger_response = schema["components"]["schemas"]["TriggerResponse"]
        trigger_list = schema["components"]["schemas"]["TriggerResponseList"]
        executions_list = schema["components"]["schemas"]["TriggerExecutionResponseList"]

        assert (
            create_request["properties"]["inputs_template"]["additionalProperties"]["type"]
            == "string"
        )
        assert (
            update_request["properties"]["inputs_template"]["anyOf"][0]["additionalProperties"]["type"]
            == "string"
        )
        assert (
            trigger_response["properties"]["inputs_template"]["additionalProperties"]["type"]
            == "string"
        )
        assert trigger_list["properties"]["items"]["items"]["$ref"].endswith("/TriggerResponse")
        assert (
            executions_list["properties"]["items"]["items"]["$ref"]
            .endswith("/TriggerExecutionResponse")
        )
