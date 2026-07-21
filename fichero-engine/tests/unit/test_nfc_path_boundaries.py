from __future__ import annotations

import unicodedata
from urllib.parse import quote

import fastapi
import pytest

from fichero.api.library_header import optional_library_path
from fichero.db import Database
from fichero.db_manager import DatabaseManager
from fichero.db.library_paths import nfc_path


def _request(header_value: str | None) -> fastapi.Request:
    headers: list[tuple[bytes, bytes]] = []
    if header_value is not None:
        headers.append((b"x-fichero-library-path", header_value.encode()))
    return fastapi.Request({"type": "http", "headers": headers})


@pytest.fixture
def global_client(tmp_path):
    from fastapi.testclient import TestClient

    from fichero.api.main import app
    from fichero.api.routes.library_registry import get_global_database

    global_db = Database(path=tmp_path / "global.fichero" / "fichero.duckdb")
    app.dependency_overrides[get_global_database] = lambda: global_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_global_database, None)
        global_db.conn.close()


def test_nfc_path_is_noop_for_already_normalized_paths() -> None:
    path = unicodedata.normalize("NFC", "/tmp/Chocó.fichero")
    assert nfc_path(path) == path


def test_optional_library_path_round_trips_nfd_header_as_nfc() -> None:
    header = quote(unicodedata.normalize("NFD", "/tmp/Chocó.fichero"), safe="/")
    assert optional_library_path(_request(header)) == unicodedata.normalize(
        "NFC",
        "/tmp/Chocó.fichero",
    )


def test_registry_round_trips_nfd_add_then_nfc_remove(global_client, tmp_path) -> None:
    library = tmp_path / unicodedata.normalize("NFC", "Chocó.fichero")
    library.mkdir(parents=True, exist_ok=True)
    nfd_path = unicodedata.normalize("NFD", str(library))

    added = global_client.post("/api/registry/add", params={"path": nfd_path})
    assert added.status_code == 200, added.text
    assert added.json()["path"] == unicodedata.normalize("NFC", str(library.resolve()))

    removed = global_client.delete(
        f"/api/registry/{quote(str(library.resolve()), safe='')}"
    )
    assert removed.status_code == 200, removed.text
    assert removed.json()["path"] == unicodedata.normalize("NFC", str(library.resolve()))


def test_db_manager_close_and_quiesce_follow_normalized_cache_key(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    manager = DatabaseManager()
    library = tmp_path / unicodedata.normalize("NFC", "Chocó.fichero")
    library.mkdir(parents=True, exist_ok=True)
    nfd_path = unicodedata.normalize("NFD", str(library))
    nfc = unicodedata.normalize("NFC", str(library))

    try:
        manager.get_database(nfd_path)
        assert list(manager._databases) == [nfc]

        manager.quiesce_database(nfc, checkpoint=False)
        assert list(manager._databases) == [nfc]

        manager.close_database(nfc)
        assert manager.active_count == 0
    finally:
        manager.close_all()
