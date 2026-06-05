"""Tests for the library bootstrap route (``POST /api/library``).

The route creates a ``.fichero`` package on disk and initializes its DuckDB
schema. Tests use ``tmp_path`` (under /var/folders, which IS in the
allowlist) so we get a real create-then-verify-then-cleanup loop without
the conftest ``test_package`` fixture (which pre-creates the package).
"""

from __future__ import annotations

from pathlib import Path
import shutil

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
    # /usr/local is never in the allowlist on any OS or CI environment
    # (not ~/Documents, ~/Dropbox, ~/Library/Application Support,
    # /var/folders, /private/var/folders, or /tmp).
    bad = Path("/usr/local/nope.fichero")
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


def test_create_library_closes_stale_cached_connection_after_recreate(
    tmp_path: Path,
) -> None:
    """Recreating a package path must not keep a stale deleted DB handle.

    This mirrors the Finder-delete/import smoke trap: the backend can have
    an open DuckDB connection for ``target``; the package is deleted on disk;
    then ``POST /api/library`` recreates the same path. The route must close
    cached connections before initializing the new package so later writes
    hit the new on-disk fichero.duckdb.
    """
    from fichero.db import Database, db_manager
    from fichero.models import Document

    target = tmp_path / "recreated.fichero"
    client = _client()

    response = client.post("/api/library", json={"path": str(target)})
    assert response.status_code == 200

    stale_db = db_manager.get_database(target)
    stale_doc = Document(name="stale", path="/stale")
    stale_db.save(stale_doc)
    assert stale_db.count(Document) == 1

    shutil.rmtree(target)
    response = client.post("/api/library", json={"path": str(target)})
    assert response.status_code == 200
    assert response.json()["created"] is True

    current_db = db_manager.get_database(target)
    current_doc = Document(name="current", path="/current")
    current_db.save(current_doc)
    assert current_db.count(Document) == 1
    assert current_db.get(Document, stale_doc.id) is None

    fresh_db = Database(target / "fichero.duckdb")
    try:
        assert fresh_db.get(Document, current_doc.id) is not None
        assert fresh_db.get(Document, stale_doc.id) is None
    finally:
        fresh_db.close()
