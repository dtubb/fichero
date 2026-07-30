"""Tests for background task queue routes.

Background tasks (reindex, metrics) run via an APScheduler-backed TaskQueue.
Routes require X-Fichero-Library-Path header — provided automatically by the
`client` fixture in conftest.py. Tests mock get_task_queue() to avoid
needing a real APScheduler instance.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fichero_server.workflows.tasks import TaskType, TaskStatus
from fichero_server.workflows.task_types import TaskResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_task(
    task_id: str = "task-1",
    task_type: TaskType = TaskType.REINDEX,
    status: TaskStatus = TaskStatus.PENDING,
) -> MagicMock:
    task = MagicMock()
    task.task_id = task_id
    task.task_type = task_type
    task.name = "Test Task"
    task.status = status
    task.progress = MagicMock()
    task.progress.current = 0
    task.progress.total = 100
    task.progress.percent = 0.0
    task.progress.message = "Waiting"
    task.progress.updated_at = datetime.now()
    task.result = None
    task.created_at = datetime.now()
    task.started_at = None
    task.completed_at = None
    task.error_message = None
    return task


def _make_mock_queue(task: MagicMock | None = None) -> MagicMock:
    queue = MagicMock()
    queue.create_task = AsyncMock(return_value=task or _make_mock_task())
    queue.list_tasks = AsyncMock(return_value=[])
    queue.get_task = AsyncMock(return_value=task)
    queue.cancel_task = AsyncMock(return_value=task)
    queue.delete_task = AsyncMock(return_value=True)
    return queue


# ---------------------------------------------------------------------------
# 503 when queue not initialized
# ---------------------------------------------------------------------------


# The tasks router uses prefix="/tasks" and is mounted at "/api/tasks",
# so actual routes are at /api/tasks/...

BASE = "/api/tasks"


class TestQueueNotInitialized:
    def test_list_tasks_returns_503(self, client):
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=None):
            r = client.get(BASE)
        assert r.status_code == 503

    def test_create_reindex_returns_503(self, client):
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=None):
            r = client.post(f"{BASE}/reindex")
        assert r.status_code == 503

    def test_create_metrics_returns_503(self, client):
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=None):
            r = client.post(f"{BASE}/metrics")
        assert r.status_code == 503


# ---------------------------------------------------------------------------
# POST /api/tasks/reindex
# ---------------------------------------------------------------------------


class TestCreateReindexTask:
    def test_create_reindex_task(self, client):
        task = _make_mock_task(task_type=TaskType.REINDEX)
        queue = _make_mock_queue(task)
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=queue):
            r = client.post(f"{BASE}/reindex")
        assert r.status_code == 200
        data = r.json()
        assert data["task_id"] == "task-1"
        assert data["task_type"] == "reindex"


# ---------------------------------------------------------------------------
# POST /api/tasks/metrics
# ---------------------------------------------------------------------------


class TestCreateMetricsTask:
    def test_create_metrics_task(self, client):
        task = _make_mock_task(task_id="task-2", task_type=TaskType.METRICS)
        queue = _make_mock_queue(task)
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=queue):
            r = client.post(f"{BASE}/metrics")
        assert r.status_code == 200
        data = r.json()
        assert data["task_type"] == "metrics"


# ---------------------------------------------------------------------------
# GET /api/tasks
# ---------------------------------------------------------------------------


class TestListTasks:
    def test_empty_list(self, client):
        queue = _make_mock_queue()
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=queue):
            r = client.get(BASE)
        assert r.status_code == 200
        data = r.json()
        assert "tasks" in data
        assert data["tasks"] == []

    def test_returns_tasks(self, client):
        task = _make_mock_task()
        queue = MagicMock()
        queue.list_tasks = AsyncMock(return_value=[task])
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=queue):
            r = client.get(BASE)
        assert r.status_code == 200
        assert len(r.json()["tasks"]) == 1

    def test_invalid_status_returns_400(self, client):
        queue = _make_mock_queue()
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=queue):
            r = client.get(f"{BASE}?status=bogus")
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/tasks/{task_id}
# ---------------------------------------------------------------------------


class TestGetTask:
    def test_get_existing_task(self, client):
        task = _make_mock_task()
        queue = _make_mock_queue(task)
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=queue):
            r = client.get(f"{BASE}/task-1")
        assert r.status_code == 200
        assert r.json()["task_id"] == "task-1"

    def test_get_missing_task_returns_404(self, client):
        queue = _make_mock_queue(None)
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=queue):
            r = client.get(f"{BASE}/no-such-task")
        assert r.status_code == 404


class TestTaskResults:
    def test_running_task_result_returns_202(self, client):
        task = _make_mock_task(status=TaskStatus.RUNNING)
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=_make_mock_queue(task)):
            response = client.get(f"{BASE}/task-1/result")
        assert response.status_code == 202

    def test_completed_metrics_missing_fields_returns_409(self, client):
        task = _make_mock_task(task_type=TaskType.METRICS, status=TaskStatus.COMPLETED)
        task.result = TaskResult(success=True, message="done", details={})
        with patch("fichero_server.api.routes.workflow.tasks.get_task_queue", return_value=_make_mock_queue(task)):
            response = client.get(f"{BASE}/metrics/task-1/data")
        assert response.status_code == 409
