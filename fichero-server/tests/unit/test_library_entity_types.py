"""Unit tests for per-library entity type routes (#874).

Covers:
  GET  /api/libraries/{lib}/entity-types          — list enabled types
  POST /api/libraries/{lib}/entity-types          — add/enable a type
  DELETE /api/libraries/{lib}/entity-types/{key}  — remove a type
"""

import pytest
from fastapi.testclient import TestClient

from fichero_server.api.main import app
from fichero_server.db import db_manager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def et_package(tmp_path):
    """Isolated .fichero package for entity-type route tests."""
    pkg = tmp_path / "entitytype_test.fichero"
    pkg.mkdir()
    (pkg / "lance").mkdir()
    (pkg / "storage").mkdir()
    (pkg / "files").mkdir()
    db_manager.get_database(pkg)
    yield pkg
    db_manager.close_all()


@pytest.fixture
def et_client(et_package):
    """TestClient wired to the isolated entity-type package.

    Overrides _get_db_manager so the library-path routes resolve to the
    test db_manager (same global singleton, fresh package each test).
    """
    from fichero_server.api.routes.library_entity_types import _get_db_manager
    from fichero_server.db.app import AppDatabase
    import fichero_server.db.app as _app_db_module

    # Isolate the app DB so the fixture never touches the prod DuckDB.
    app_db_path = et_package.parent / "test_app.duckdb"
    test_app_db = AppDatabase(path=app_db_path)
    saved_singleton = _app_db_module._app_db
    _app_db_module._app_db = test_app_db

    app.dependency_overrides[_get_db_manager] = lambda: db_manager

    client = TestClient(app)
    yield client, et_package

    app.dependency_overrides.clear()
    _app_db_module._app_db = saved_singleton
    test_app_db.close()


def _lib(pkg_path) -> str:
    """Return the raw string path for use in route segments.

    The {lib:path} route param accepts literal slashes so no encoding needed.
    """
    return str(pkg_path)


# ---------------------------------------------------------------------------
# GET — list entity types
# ---------------------------------------------------------------------------


class TestListLibraryEntityTypes:
    def test_empty_for_new_library(self, et_client):
        client, pkg = et_client
        r = client.get(f"/api/libraries/{_lib(pkg)}/entity-types")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []
        assert data["count"] == 0

    def test_returns_added_types(self, et_client):
        client, pkg = et_client
        lib = _lib(pkg)
        client.post(f"/api/libraries/{lib}/entity-types?entity_type_key=person")
        client.post(f"/api/libraries/{lib}/entity-types?entity_type_key=place")

        r = client.get(f"/api/libraries/{lib}/entity-types")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 2
        keys = {item["entity_type_key"] for item in data["items"]}
        assert keys == {"person", "place"}


# ---------------------------------------------------------------------------
# POST — add an entity type
# ---------------------------------------------------------------------------


class TestAddLibraryEntityType:
    def test_add_returns_created_entry(self, et_client):
        client, pkg = et_client
        r = client.post(
            f"/api/libraries/{_lib(pkg)}/entity-types?entity_type_key=concept"
        )
        assert r.status_code == 200
        data = r.json()
        assert data["entity_type_key"] == "concept"
        assert data["enabled"] is True
        assert "id" in data

    def test_add_with_enabled_false(self, et_client):
        client, pkg = et_client
        r = client.post(
            f"/api/libraries/{_lib(pkg)}/entity-types"
            "?entity_type_key=artifact&enabled=false"
        )
        assert r.status_code == 200
        assert r.json()["enabled"] is False

    def test_add_then_get_returns_it(self, et_client):
        client, pkg = et_client
        lib = _lib(pkg)
        client.post(f"/api/libraries/{lib}/entity-types?entity_type_key=event")

        r = client.get(f"/api/libraries/{lib}/entity-types")
        assert r.status_code == 200
        keys = [item["entity_type_key"] for item in r.json()["items"]]
        assert "event" in keys

    def test_duplicate_key_is_idempotent_not_error(self, et_client):
        """Re-posting an existing key updates enabled rather than creating a duplicate.

        The route is idempotent: a second POST with the same key returns 200
        and updates the enabled flag.  Only one row should exist in the list.
        """
        client, pkg = et_client
        lib = _lib(pkg)
        r1 = client.post(f"/api/libraries/{lib}/entity-types?entity_type_key=person")
        assert r1.status_code == 200

        r2 = client.post(
            f"/api/libraries/{lib}/entity-types?entity_type_key=person&enabled=false"
        )
        assert r2.status_code == 200
        assert r2.json()["enabled"] is False

        # Confirm only one row exists — no duplicate was inserted.
        r3 = client.get(f"/api/libraries/{lib}/entity-types")
        person_rows = [
            item for item in r3.json()["items"]
            if item["entity_type_key"] == "person"
        ]
        assert len(person_rows) == 1


# ---------------------------------------------------------------------------
# DELETE — remove an entity type
# ---------------------------------------------------------------------------


class TestRemoveLibraryEntityType:
    def test_delete_existing_returns_204(self, et_client):
        client, pkg = et_client
        lib = _lib(pkg)
        client.post(f"/api/libraries/{lib}/entity-types?entity_type_key=location")

        r = client.delete(f"/api/libraries/{lib}/entity-types/location")
        assert r.status_code == 204

    def test_delete_removes_from_list(self, et_client):
        client, pkg = et_client
        lib = _lib(pkg)
        client.post(f"/api/libraries/{lib}/entity-types?entity_type_key=person")
        client.post(f"/api/libraries/{lib}/entity-types?entity_type_key=place")

        client.delete(f"/api/libraries/{lib}/entity-types/person")

        r = client.get(f"/api/libraries/{lib}/entity-types")
        assert r.status_code == 200
        keys = [item["entity_type_key"] for item in r.json()["items"]]
        assert "person" not in keys
        assert "place" in keys

    def test_delete_nonexistent_returns_404(self, et_client):
        client, pkg = et_client
        lib = _lib(pkg)

        r = client.delete(f"/api/libraries/{lib}/entity-types/does_not_exist")
        assert r.status_code == 404

    def test_delete_then_get_empty(self, et_client):
        client, pkg = et_client
        lib = _lib(pkg)
        client.post(f"/api/libraries/{lib}/entity-types?entity_type_key=concept")
        client.delete(f"/api/libraries/{lib}/entity-types/concept")

        r = client.get(f"/api/libraries/{lib}/entity-types")
        assert r.status_code == 200
        assert r.json()["items"] == []
        assert r.json()["count"] == 0
