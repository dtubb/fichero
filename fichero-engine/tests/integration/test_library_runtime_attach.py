"""Runtime library attachment stays live without restarting the engine."""

from pathlib import Path
from urllib.parse import quote

from fastapi.testclient import TestClient

from fichero.api.main import app
from fichero.api.routes.library_registry import get_global_database
from fichero.db import Database
from fichero.db_manager import db_manager


def test_attach_bookmark_registers_and_opens_live_library(tmp_path: Path):
    global_db = Database(tmp_path / "global.fichero" / "fichero.duckdb")
    library_path = tmp_path / "AddedAfterStartup.fichero"
    library_path.mkdir()
    app.dependency_overrides[get_global_database] = lambda: global_db
    try:
        with TestClient(app) as client:
            attached = client.post(
                "/api/registry/attach-bookmark",
                json={
                    "path": str(library_path),
                    "name": "Added After Startup",
                    "bookmark": "opaque-host-bookmark",
                },
            )
            assert attached.status_code == 200, attached.text
            assert attached.json()["bookmark"] == "opaque-host-bookmark"

            listed = client.get("/api/registry")
            assert listed.status_code == 200, listed.text
            assert [library["path"] for library in listed.json()["libraries"]] == [
                str(library_path.resolve())
            ]

            queried = client.get(
                "/api/health",
                headers={"X-Fichero-Library-Path": quote(str(library_path), safe="/")},
            )
            assert queried.status_code == 200, queried.text
            assert queried.json()["library_path"] == str(library_path.resolve())

            repeated = client.post(
                "/api/registry/attach-bookmark",
                json={"path": str(library_path), "bookmark": "opaque-host-bookmark"},
            )
            assert repeated.status_code == 200, repeated.text
            assert client.get("/api/registry").json()["count"] == 1
    finally:
        app.dependency_overrides.pop(get_global_database, None)
        db_manager.close_database(library_path)
        global_db.close()
