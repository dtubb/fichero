"""Tests for knowledge migration routes.

Migrations transform the knowledge graph schema (multi-source claims,
backfills, orphan repair). Routes support dry-run mode and integrity checks.
Tests mock MigrationRunner to avoid running actual migrations on test data.
Router is mounted at "/api/migrations" with no own prefix (the doubled
/api/migrations/migrations stutter was fixed 2026-07-27).
"""

from unittest.mock import MagicMock, patch
from datetime import datetime


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

BASE = "/api/migrations"


def _make_migration_result(
    name: str = "migrate_claims_to_multi_source",
    status: str = "completed",
    migrated: int = 5,
) -> MagicMock:
    result = MagicMock()
    result.migration_name = name
    result.status = MagicMock(value=status)
    result.migrated = migrated
    result.skipped = 0
    result.failed = 0
    result.dry_run = False
    result.audit_id = "audit-1"
    result.error_message = None
    result.started_at = datetime.now()
    result.completed_at = datetime.now()
    result.duration_ms = 100
    result.details = {}
    return result


# ---------------------------------------------------------------------------
# GET /api/migrations — list
# ---------------------------------------------------------------------------


class TestListMigrations:
    def test_returns_migrations_list(self, client):
        r = client.get(BASE)
        assert r.status_code == 200
        data = r.json()
        assert "migrations" in data
        assert len(data["migrations"]) > 0

    def test_migration_has_required_fields(self, client):
        r = client.get(BASE)
        assert r.status_code == 200
        first = r.json()["migrations"][0]
        assert "name" in first
        assert "description" in first
        assert "type" in first


# ---------------------------------------------------------------------------
# POST /api/migrations/run
# ---------------------------------------------------------------------------


class TestRunMigration:
    def test_run_dry_run(self, client):
        result = _make_migration_result()
        with patch("fichero_server.api.routes.migrations.MigrationRunner") as MockRunner:
            MockRunner.return_value.migrate_claims_to_multi_source.return_value = result
            r = client.post(f"{BASE}/run", json={
                "command": "migrate_claims_to_multi_source",
                "dry_run": True,
            })
        assert r.status_code == 200
        data = r.json()
        assert data["migration_name"] == "migrate_claims_to_multi_source"
        assert data["migrated"] == 5

    def test_run_backfill(self, client):
        result = _make_migration_result("backfill_claim_source_metadata")
        with patch("fichero_server.api.routes.migrations.MigrationRunner") as MockRunner:
            MockRunner.return_value.backfill_claim_source_metadata.return_value = result
            r = client.post(f"{BASE}/run", json={
                "command": "backfill_claim_source_metadata",
                "dry_run": True,
            })
        assert r.status_code == 200

    def test_run_repair(self, client):
        result = _make_migration_result("repair_orphaned_claim_links")
        with patch("fichero_server.api.routes.migrations.MigrationRunner") as MockRunner:
            MockRunner.return_value.repair_orphaned_claim_links.return_value = result
            r = client.post(f"{BASE}/run", json={
                "command": "repair_orphaned_claim_links",
                "dry_run": True,
            })
        assert r.status_code == 200


# ---------------------------------------------------------------------------
# GET /api/migrations/integrity-check
# ---------------------------------------------------------------------------


class TestIntegrityCheck:
    def test_integrity_check_returns_200(self, client):
        r = client.get(f"{BASE}/integrity-check")
        assert r.status_code == 200
        data = r.json()
        assert "entity_count" in data
        assert "claim_count" in data
        assert "checks_passed" in data
