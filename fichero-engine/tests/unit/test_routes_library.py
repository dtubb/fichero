"""Tests for the library bootstrap route (``POST /api/library``).

The route creates a ``.fichero`` package on disk and initializes its DuckDB
schema. Tests use ``tmp_path`` (under /var/folders, which IS in the
allowlist) so we get a real create-then-verify-then-cleanup loop without
the conftest ``test_package`` fixture (which pre-creates the package).
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from fichero.api.main import app


def _client() -> TestClient:
    """Bare TestClient — POST /api/library does NOT need a library header."""
    return TestClient(app)


def test_create_library_creates_package_and_db(tmp_path: Path) -> None:
    """Happy path: a fresh .fichero path under /var/folders → created=True."""
    target = tmp_path / "fresh.fichero"
    assert not target.exists()

    response = _client().post("/api/library", json={"path": str(target)})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["created"] is True
    assert body["tables_initialized"] is True
    assert Path(body["path"]).resolve() == target.resolve()

    # Filesystem side-effects we promised the caller.
    assert target.is_dir()
    assert (target / "files").is_dir()
    # We create both lance/ (SwiftUI parity) and vectors/ (task spec).
    assert (target / "vectors").is_dir()
    assert (target / "fichero.duckdb").exists()


def test_create_library_is_idempotent(tmp_path: Path) -> None:
    """Re-creating an existing package returns created=False, no error."""
    target = tmp_path / "again.fichero"
    client = _client()

    first = client.post("/api/library", json={"path": str(target)})
    assert first.status_code == 200
    assert first.json()["created"] is True

    second = client.post("/api/library", json={"path": str(target)})
    assert second.status_code == 200
    body = second.json()
    assert body["created"] is False
    assert body["tables_initialized"] is True


def test_create_library_rejects_non_allowlist_path(tmp_path: Path) -> None:
    """A .fichero path outside the allowlist roots → 403, no filesystem work."""
    # /tmp is NOT in the allowlist (only /var/folders, /private/var/folders,
    # ~/Documents, ~/Dropbox, ~/Library/Application Support).
    bad = Path("/tmp/nope.fichero")
    response = _client().post("/api/library", json={"path": str(bad)})
    assert response.status_code == 403
    assert "allowed location" in response.json()["detail"]
    assert not bad.exists()


def test_create_library_rejects_non_fichero_suffix(tmp_path: Path) -> None:
    """The allowlist also enforces the .fichero suffix → 403."""
    bad = tmp_path / "wrong-suffix.duckdb"
    response = _client().post("/api/library", json={"path": str(bad)})
    assert response.status_code == 403
    assert not bad.exists()


def test_create_library_initializes_schema_for_immediate_query(
    tmp_path: Path,
) -> None:
    """After create, the DB has the Document table and is queryable.

    Proves ``tables_initialized: true`` isn't a lie — a CLI caller can
    immediately list documents without "table not found" errors.
    """
    from fichero.db import db_manager
    from fichero.models import Document

    target = tmp_path / "queryable.fichero"
    response = _client().post("/api/library", json={"path": str(target)})
    assert response.status_code == 200

    db = db_manager.get_database(target)
    assert db.count(Document) == 0  # empty, but the table exists
