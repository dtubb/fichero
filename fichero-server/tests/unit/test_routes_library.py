"""Tests for the library bootstrap route (``POST /api/library``).

The route creates a ``.fichero`` package on disk and initializes its DuckDB
schema. Tests use ``tmp_path`` (under /var/folders, which IS in the
allowlist) so we get a real create-then-verify-then-cleanup loop without
the conftest ``test_package`` fixture (which pre-creates the package).
"""

from __future__ import annotations

from pathlib import Path
import shutil
from urllib.parse import quote

from fastapi.testclient import TestClient

from fichero_server.api.auth import initialize_token
from fichero_server.api.main import app
from fichero_server.db import db_manager
from fichero_server.models import DocType, Document

_CLIENT_AUTH_TOKEN: str | None = None


def _client() -> TestClient:
    """TestClient with the bootstrap bearer token.

    Do NOT call ``attach_auth_middleware`` here: the unit conftest already
    attaches it (once, before the app starts) and another test's TestClient may
    have started the app already, which makes a late ``add_middleware`` raise
    "Cannot add middleware after an application has started". The token is the
    same stable value the conftest uses (``initialize_token`` reads the persisted
    ``.api-key``), so the conftest-attached middleware accepts this header.
    """
    global _CLIENT_AUTH_TOKEN
    if _CLIENT_AUTH_TOKEN is None:
        _CLIENT_AUTH_TOKEN = initialize_token()
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {_CLIENT_AUTH_TOKEN}"
    return client


def _root_inboxes(db) -> list[Document]:
    return list(
        db.query(
            Document,
            name="Inbox",
            parent_id=None,
            doc_type=DocType.folder,
        )
    )


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

    db = db_manager.get_database(target)
    inboxes = _root_inboxes(db)
    assert len(inboxes) == 1
    assert inboxes[0].name == "Inbox"
    assert inboxes[0].doc_type == DocType.folder
    assert inboxes[0].parent_id is None


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

    db = db_manager.get_database(target)
    assert len(_root_inboxes(db)) == 1


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
    immediately list documents without "table not found" errors, and
    the bootstrap Inbox is present.
    """
    target = tmp_path / "queryable.fichero"
    response = _client().post("/api/library", json={"path": str(target)})
    assert response.status_code == 200

    db = db_manager.get_database(target)
    assert db.count(Document) == 1
    assert len(_root_inboxes(db)) == 1


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
    from fichero_server.db import Database, db_manager
    from fichero_server.models import Document

    target = tmp_path / "recreated.fichero"
    client = _client()

    response = client.post("/api/library", json={"path": str(target)})
    assert response.status_code == 200

    stale_db = db_manager.get_database(target)
    assert len(_root_inboxes(stale_db)) == 1
    stale_doc = Document(name="stale", path="/stale")
    stale_db.save(stale_doc)
    assert stale_db.count(Document) == 2

    shutil.rmtree(target)
    response = client.post("/api/library", json={"path": str(target)})
    assert response.status_code == 200
    assert response.json()["created"] is True

    current_db = db_manager.get_database(target)
    assert len(_root_inboxes(current_db)) == 1
    current_doc = Document(name="current", path="/current")
    current_db.save(current_doc)
    assert current_db.count(Document) == 2
    assert current_db.get(Document, stale_doc.id) is None

    fresh_db = Database(target / "fichero.duckdb")
    try:
        assert fresh_db.get(Document, current_doc.id) is not None
        assert fresh_db.get(Document, stale_doc.id) is None
        assert len(_root_inboxes(fresh_db)) == 1
    finally:
        fresh_db.close()


def test_open_library_seeds_missing_inbox_once_without_data_loss(
    tmp_path: Path,
) -> None:
    """Existing libraries missing Inbox heal on open and keep other documents."""
    target = tmp_path / "legacy-no-inbox.fichero"
    client = _client()

    response = client.post("/api/library", json={"path": str(target)})
    assert response.status_code == 200

    db = db_manager.get_database(target)
    sentinel = Document(name="Keep Me", path="/keep-me.txt")
    db.save(sentinel)
    for inbox in _root_inboxes(db):
        db.delete(inbox)
    assert _root_inboxes(db) == []

    db_manager.close_database(target)

    headers = {"X-Fichero-Library-Path": str(target)}
    open_response = client.get("/api/documents/collections", headers=headers)
    assert open_response.status_code == 200, open_response.text

    reopened_db = db_manager.get_database(target)
    inboxes = _root_inboxes(reopened_db)
    assert len(inboxes) == 1
    assert reopened_db.get(Document, sentinel.id) is not None

    db_manager.close_database(target)
    reopen_again = client.get("/api/documents/collections", headers=headers)
    assert reopen_again.status_code == 200, reopen_again.text

    reopened_again_db = db_manager.get_database(target)
    assert len(_root_inboxes(reopened_again_db)) == 1
    assert reopened_again_db.get(Document, sentinel.id) is not None


def test_import_can_target_seeded_inbox_from_root_lookup(tmp_path: Path) -> None:
    """Seeded Inbox matches the root-drop lookup shape and accepts imports."""
    target = tmp_path / "import-target.fichero"
    client = _client()

    response = client.post("/api/library", json={"path": str(target)})
    assert response.status_code == 200

    headers = {"X-Fichero-Library-Path": str(target)}
    collections = client.get("/api/documents/collections", headers=headers)
    assert collections.status_code == 200, collections.text

    items = collections.json()["items"]
    inbox = next(
        item
        for item in items
        if item["name"] == "Inbox"
        and item["parent_id"] is None
        and item["doc_type"] == "folder"
    )

    import_response = client.post(
        f"/api/documents/import?parent_id={inbox['id']}",
        headers=headers,
        files={"file": ("hello.txt", b"hello from inbox", "text/plain")},
    )
    assert import_response.status_code == 200, import_response.text
    body = import_response.json()
    assert body["parent_id"] == inbox["id"]


def test_open_library_accepts_percent_encoded_non_ascii_header(
    tmp_path: Path,
    client: TestClient,
) -> None:
    """Encoded non-ASCII library paths must round-trip through the header.

    Uses the shared ``client`` fixture (carries the auth bearer token via the
    ``_unit_test_auth_header`` autouse fixture) so the request reaches the
    library-path logic instead of being rejected at the shared-secret auth
    gate. The ``X-Fichero-Library-Path`` header is overridden per-request with
    the percent-encoded non-ASCII path — modelling what a correct client
    sends. See #2647 for why the bare ``_client()`` helper 401s.
    """
    target = tmp_path / "Chocó_Librería.fichero"

    response = client.post("/api/library", json={"path": str(target)})
    assert response.status_code == 200, response.text

    encoded_headers = {
        "X-Fichero-Library-Path": quote(str(target), safe="/"),
    }
    collections = client.get("/api/documents/collections", headers=encoded_headers)

    assert collections.status_code == 200, collections.text
    items = collections.json()["items"]
    assert any(item["name"] == "Inbox" for item in items)
