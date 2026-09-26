"""GET /api/health reports LIVE dependency versions for the About box.

Daniel wants the "Built with" list DERIVED from the engine env, never
hard-typed. The Mac app has no in-process Python, so the engine is the only
live source. This pins that /api/health carries a `dependencies` map of
lowercased pip distribution name → installed version, populated for the
notable frameworks and omitting anything not installed (so the box shows a
lib with no version rather than a wrong one).
"""

from __future__ import annotations


def test_health_carries_live_dependency_versions(client):
    response = client.get("/api/health")
    assert response.status_code == 200

    deps = response.json()["dependencies"]
    assert isinstance(deps, dict)
    # Core frameworks are always installed in the engine env.
    assert deps.get("fastapi"), deps
    assert deps.get("pydantic"), deps
    # Keys are lowercased distribution names (the UI looks up by that).
    assert all(key == key.lower() for key in deps)
    # A present key always carries a real version — never an empty/None value.
    assert all(value for value in deps.values())


def test_health_reports_recorded_migration_failures(client, db):
    """#4983 phase 1: a schema-migration failure recorded on the library's
    `Database` (atomic rollback + ERROR log happen elsewhere) must be
    visible at `GET /api/health` — the VISIBLE half of "atomic and loud,"
    so an operator or the app can see it without reading engine logs."""
    from datetime import datetime

    from fichero_server.db.migrations.schema import MigrationFailure

    assert db.migration_failures == []  # healthy library: none recorded

    db.migration_failures.append(
        MigrationFailure(
            migration="migrate_references_table",
            error_type="ConstraintException",
            message="Duplicate key \"doi\": violates unique constraint",
            occurred_at=datetime(2026, 9, 20, 12, 0, 0),
        )
    )

    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert len(body["migration_failures"]) == 1
    failure = body["migration_failures"][0]
    assert failure["migration"] == "migrate_references_table"
    assert failure["error_type"] == "ConstraintException"
    assert "doi" in failure["message"]


def test_health_redacts_the_local_library_path_from_failure_messages(client, db):
    """#4983 item 4: the server may be remote — a migration-failure message
    that happens to embed the library's local filesystem path (verified:
    DuckDB's own IOException does this on a missing file) must not reach
    a remote caller through the API response, even though the full,
    unredacted text still reaches the server log."""
    from datetime import datetime

    from fichero_server.db.migrations.schema import MigrationFailure

    local_path = str(db.path)
    db.migration_failures.append(
        MigrationFailure(
            migration="migrate_checkpoint_tables",
            error_type="IOException",
            message=f'IO Error: Cannot open file "{local_path}": No such file or directory',
            occurred_at=datetime(2026, 9, 20, 12, 0, 0),
        )
    )

    response = client.get("/api/health")
    assert response.status_code == 200
    message = response.json()["migration_failures"][0]["message"]
    assert local_path not in message
    assert "<library>" in message


def test_static_versions_omit_absent_libraries():
    # A distribution that is not installed is simply absent — never a wrong or
    # blank version.
    from fichero_server.api.main import _static_dependency_versions

    versions = _static_dependency_versions()
    assert "fastapi" in versions
    assert "definitely-not-a-real-distribution" not in versions
    assert all(v for v in versions.values())
