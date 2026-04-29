"""Tests for batch workflow execution routes.

Batch execution runs a workflow against multiple inputs concurrently.
Routes manage a BatchManager singleton backed by a DuckDB store.
Tests mock get_batch_manager() to avoid needing a real batch DB.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fichero.workflows.batch import BatchStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_batch(
    batch_id: str = "batch-1",
    workflow_id: str = "wf-1",
    status: BatchStatus = BatchStatus.PENDING,
    total_items: int = 3,
) -> MagicMock:
    batch = MagicMock()
    batch.batch_id = batch_id
    batch.workflow_id = workflow_id
    batch.status = status
    batch.total_items = total_items
    batch.completed_items = 0
    batch.failed_items = 0
    batch.max_concurrent = 5
    batch.created_at = datetime.now()
    batch.started_at = None
    batch.completed_at = None
    batch.error_message = None
    batch.items = []

    # BatchResponse.from_batch calls batch.get_progress() for progress endpoint
    progress = MagicMock()
    progress.batch_id = batch_id
    progress.total_items = total_items
    progress.completed_items = 0
    progress.failed_items = 0
    progress.running_items = 0
    progress.pending_items = total_items
    progress.progress_percent = 0.0
    progress.estimated_remaining_seconds = None
    progress.avg_item_duration_seconds = None
    batch.get_progress.return_value = progress

    return batch


def _make_mock_manager(batch: MagicMock | None = None) -> MagicMock:
    manager = MagicMock()
    manager.create_batch = AsyncMock(return_value=batch or _make_mock_batch())
    manager.list_batches = AsyncMock(return_value=[])
    manager.get_batch = AsyncMock(return_value=batch)
    manager.pause_batch = AsyncMock(return_value=batch or _make_mock_batch())
    manager.cancel_batch = AsyncMock(return_value=batch or _make_mock_batch())
    return manager


# ---------------------------------------------------------------------------
# GET /api/batches — list
# ---------------------------------------------------------------------------


class TestListBatches:
    def test_empty_list(self, client):
        manager = _make_mock_manager()
        with patch("fichero.api.routes.batch.get_batch_manager", return_value=manager):
            r = client.get("/api/batches")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_batches(self, client):
        batch = _make_mock_batch()
        manager = MagicMock()
        manager.list_batches = AsyncMock(return_value=[batch])
        with patch("fichero.api.routes.batch.get_batch_manager", return_value=manager):
            r = client.get("/api/batches")
        assert r.status_code == 200
        assert len(r.json()) == 1
        assert r.json()[0]["batch_id"] == "batch-1"


# ---------------------------------------------------------------------------
# POST /api/batches — create
# ---------------------------------------------------------------------------


class TestCreateBatch:
    def test_create_batch(self, client):
        batch = _make_mock_batch()
        manager = _make_mock_manager(batch)
        with patch("fichero.api.routes.batch.get_batch_manager", return_value=manager):
            r = client.post("/api/batches", json={
                "workflow_id": "wf-1",
                "items": [{"input_text": "item 1"}, {"input_text": "item 2"}],
            })
        assert r.status_code == 200
        assert r.json()["workflow_id"] == "wf-1"

    def test_empty_items_returns_400(self, client):
        manager = _make_mock_manager()
        with patch("fichero.api.routes.batch.get_batch_manager", return_value=manager):
            r = client.post("/api/batches", json={
                "workflow_id": "wf-1",
                "items": [],
            })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/batches/{batch_id}
# ---------------------------------------------------------------------------


class TestGetBatch:
    def test_get_existing_batch(self, client):
        batch = _make_mock_batch()
        manager = _make_mock_manager(batch)
        with patch("fichero.api.routes.batch.get_batch_manager", return_value=manager):
            r = client.get("/api/batches/batch-1")
        assert r.status_code == 200
        assert r.json()["batch_id"] == "batch-1"

    def test_get_missing_batch_returns_404(self, client):
        manager = _make_mock_manager(None)
        with patch("fichero.api.routes.batch.get_batch_manager", return_value=manager):
            r = client.get("/api/batches/no-such-batch")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/batches/{batch_id}/progress
# ---------------------------------------------------------------------------


class TestGetBatchProgress:
    def test_get_progress(self, client):
        batch = _make_mock_batch(total_items=10)
        manager = _make_mock_manager(batch)
        with patch("fichero.api.routes.batch.get_batch_manager", return_value=manager):
            r = client.get("/api/batches/batch-1/progress")
        assert r.status_code == 200
        data = r.json()
        assert "total_items" in data
        assert data["total_items"] == 10

    def test_progress_missing_batch_returns_404(self, client):
        manager = _make_mock_manager(None)
        with patch("fichero.api.routes.batch.get_batch_manager", return_value=manager):
            r = client.get("/api/batches/no-such-batch/progress")
        assert r.status_code == 404
