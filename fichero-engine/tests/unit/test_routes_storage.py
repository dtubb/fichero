"""Tests for storage and snapshot routes.

Storage routes serve thumbnails, display images, and source files from the
library package directory. Snapshots create point-in-time backups of the DB.
Tests focus on the simpler endpoints (stats, snapshots) and validate 404
behaviour without needing to mock the entire file-serving pipeline.
"""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# GET /api/storage/stats
# ---------------------------------------------------------------------------


class TestStorageStats:
    def test_returns_stats(self, client):
        with patch("fichero.storage.stats") as mock_stats:
            mock_stats.return_value = {
                "total_size_bytes": 1024,
                "document_count": 5,
                "thumbnail_count": 3,
            }
            r = client.get("/api/storage/stats")
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/storage/thumbnail/{doc_id} — basic validation
# ---------------------------------------------------------------------------


class TestThumbnailRoute:
    def test_missing_doc_returns_404(self, client):
        r = client.get("/api/storage/thumbnail/no-such-doc")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/storage/snapshots
# ---------------------------------------------------------------------------


class TestListSnapshots:
    def test_returns_empty_snapshots(self, client):
        with patch("fichero.api.routes.storage.list_snapshots") as mock_list:
            mock_list.return_value = []
            r = client.get("/api/storage/snapshots")
        assert r.status_code == 200
        data = r.json()
        assert "snapshots" in data
        assert data["snapshots"] == []
        assert data["total"] == 0

    def test_snapshots_total_matches_count(self, client):
        from fichero.models import LibrarySnapshot, SnapshotInitiatorType
        from datetime import datetime

        snap = LibrarySnapshot(
            id="snap-1",
            library_name="test-lib",
            library_path="/tmp/test.fichero",
            reason="test backup",
            initiator=SnapshotInitiatorType.user,
            snapshot_path="/tmp/snapshots/snap-1",
            duckdb_path="db.parquet",
            lance_path="lance/",
            created_at=datetime.now(),
        )
        with patch("fichero.api.routes.storage.list_snapshots") as mock_list:
            mock_list.return_value = [snap]
            r = client.get("/api/storage/snapshots")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert len(data["snapshots"]) == 1
