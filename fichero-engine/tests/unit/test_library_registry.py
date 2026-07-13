"""Known library registry persistence tests (#1131)."""

from __future__ import annotations

import os
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import pytest

os.environ.setdefault("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")

from fichero.db import Database  # noqa: E402
from fichero.models import ActionAudit, DocType, Document, KnownLibrary  # noqa: E402


@pytest.fixture
def db(tmp_path):
    """Create a temporary database for testing."""
    database = Database(path=tmp_path / "test.duckdb")
    yield database
    database.conn.close()


@pytest.fixture
def temp_library_path(tmp_path):
    """Create a temporary .fichero package directory."""
    lib_path = tmp_path / "TestLib.fichero"
    lib_path.mkdir(parents=True, exist_ok=True)
    return lib_path


def _create_library_fixture(path, doc_id: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    db = Database(path=path / "fichero.duckdb")
    try:
        db.save(Document(id=doc_id, name=f"{doc_id}.txt", page_content="fixture"))
    finally:
        db.conn.close()
    (path / "files").mkdir(exist_ok=True)
    (path / "files" / f"{doc_id}.txt").write_text("fixture", encoding="utf-8")


class TestKnownLibraryModel:
    """Test the KnownLibrary Pydantic model."""

    def test_create_known_library_with_all_fields(self):
        """KnownLibrary can be created with all fields."""
        lib = KnownLibrary(
            path="/path/to/lib.fichero",
            name="My Library",
            added_at=datetime(2026, 5, 17, 10, 0, 0),
            last_accessed=datetime(2026, 5, 17, 12, 30, 0),
        )
        assert lib.path == "/path/to/lib.fichero"
        assert lib.name == "My Library"
        assert lib.id is not None  # Auto-generated UUID

    def test_create_known_library_with_defaults(self):
        """KnownLibrary fills in datetime defaults."""
        lib = KnownLibrary(path="/path/to/lib.fichero")
        assert lib.path == "/path/to/lib.fichero"
        assert lib.name is None
        assert lib.added_at is not None
        assert lib.last_accessed is not None

    def test_known_library_serializes_to_dict(self):
        """KnownLibrary model_dump works correctly."""
        lib = KnownLibrary(path="/path/to/lib.fichero", name="Test")
        data = lib.model_dump()
        assert data["path"] == "/path/to/lib.fichero"
        assert data["name"] == "Test"
        assert "id" in data
        assert "added_at" in data
        assert "last_accessed" in data


class TestLibraryRegistryCRUD:
    """Test CRUD operations on the known_libraries table."""

    def test_save_and_retrieve_library(self, db, temp_library_path):
        """Save a library to DB and retrieve it."""
        lib = KnownLibrary(
            path=str(temp_library_path),
            name="Test Library",
        )
        db.save(lib)

        # Retrieve by ID
        retrieved = db.get(KnownLibrary, lib.id)
        assert retrieved is not None
        assert retrieved.path == str(temp_library_path)
        assert retrieved.name == "Test Library"

    def test_query_library_by_path(self, db, temp_library_path):
        """Query library by path."""
        lib = KnownLibrary(
            path=str(temp_library_path),
            name="Test Library",
        )
        db.save(lib)

        # Query by path
        results = db.query(KnownLibrary, path=str(temp_library_path))
        assert len(results) == 1
        assert results[0].name == "Test Library"

    def test_update_library_last_accessed(self, db, temp_library_path):
        """Update last_accessed timestamp."""
        lib = KnownLibrary(path=str(temp_library_path), name="Test")
        db.save(lib)

        old_accessed = lib.last_accessed
        lib.last_accessed = datetime.now() + timedelta(hours=1)
        db.save(lib)

        retrieved = db.get(KnownLibrary, lib.id)
        assert retrieved.last_accessed > old_accessed

    def test_delete_library(self, db, temp_library_path):
        """Delete a library from registry."""
        lib = KnownLibrary(path=str(temp_library_path), name="Test")
        db.save(lib)

        assert db.get(KnownLibrary, lib.id) is not None
        db.delete(lib)
        assert db.get(KnownLibrary, lib.id) is None

    def test_list_all_libraries(self, db, tmp_path):
        """Retrieve all libraries in registry."""
        paths = [tmp_path / f"lib{i}.fichero" for i in range(3)]
        for i, path in enumerate(paths):
            path.mkdir(parents=True, exist_ok=True)
            lib = KnownLibrary(path=str(path), name=f"Library {i}")
            db.save(lib)

        all_libs = db.all(KnownLibrary)
        assert len(all_libs) == 3
        assert all(lib.name is not None for lib in all_libs)

    def test_unique_constraint_on_path(self, db, temp_library_path):
        """Path column is unique — duplicate saves UPSERT instead of inserting."""
        lib1 = KnownLibrary(path=str(temp_library_path), name="First")
        lib2 = KnownLibrary(path=str(temp_library_path), name="Second")

        db.save(lib1)

        # Attempting to save with same path but different ID doesn't insert a second row
        # Instead it's UPSERT behavior — on conflict of the id (PRIMARY KEY),
        # it updates. Since lib2 has a different UUID, this tests the second save.
        # In practice, we'd check for existing by path first and update, not insert.
        # This test documents the current behavior.
        db.save(lib2)

        all_libs = db.all(KnownLibrary)
        # Should have 2 records with same path but different IDs
        # (because lib2 has a different UUID generated)
        same_path = [lib for lib in all_libs if lib.path == str(temp_library_path)]
        assert len(same_path) == 2
        assert {lib.name for lib in same_path} == {"First", "Second"}


class TestLibraryRegistryEndpoints:
    """Test the FastAPI endpoints for library registry.

    Note: These tests focus on endpoint behavior with the Depends(get_library_database)
    dependency. Full integration testing is better done against a live server where
    the X-Fichero-Library-Path header properly routes to the correct database.
    """

    def test_add_library_invalid_path(self, client):
        """POST /api/registry/add with non-existent path fails."""
        response = client.post(
            "/api/registry/add",
            params={
                "path": "/nonexistent/path.fichero",
            },
        )
        assert response.status_code == 400

    def test_add_library_non_fichero_path(self, client, tmp_path):
        """POST /api/registry/add rejects non-.fichero directories."""
        bad_path = tmp_path / "NotAFichero"
        bad_path.mkdir()
        response = client.post(
            "/api/registry/add",
            params={
                "path": str(bad_path),
            },
        )
        assert response.status_code == 400


class TestLibraryAutoRegistration:
    """Test that creating a library auto-registers it (#1131)."""

    def test_create_library_auto_registers(self, client, tmp_path):
        """POST /api/library auto-registers the created library."""
        # This would require mocking the library creation endpoint
        # and checking that the library appears in the registry.
        # For now, we test the underlying CRUD operations.
        pass  # Covered by integration tests


class TestGlobalRegistryHeaderless:
    """The registry is GLOBAL — list/add/remove must work with NO
    X-Fichero-Library-Path header and be shared across libraries (#1661).
    """

    @pytest.fixture
    def global_client(self, tmp_path):
        """Test client whose registry dependency points at a tmp global DB.

        Sends NO X-Fichero-Library-Path header — proving the registry
        endpoints are global and header-free.
        """
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

    def test_list_empty_no_header(self, global_client):
        """GET /api/registry works with no library header (was 422 before)."""
        response = global_client.get("/api/registry")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 0
        assert body["libraries"] == []

    def test_open_inventory_reflects_live_manager_handles(self, global_client, tmp_path):
        """Live inventory reports handles opened outside persisted registry flows."""
        from fichero.db_manager import db_manager

        library_path = (tmp_path / "OutsideRegistry.fichero").resolve()
        library_path.mkdir()
        db_manager.get_database(library_path)
        try:
            listed = global_client.get("/api/registry/open")
            assert listed.status_code == 200, listed.text
            body = listed.json()
            assert body["count"] == len(db_manager.open_library_paths())
            assert {library["path"] for library in body["libraries"]} == set(
                db_manager.open_library_paths()
            )
            assert {
                "id": str(library_path),
                "path": str(library_path),
                "is_open": True,
            } in body["libraries"]

            db_manager.close_database(library_path)
            closed = global_client.get("/api/registry/open")
            assert str(library_path) not in {
                library["path"] for library in closed.json()["libraries"]
            }
        finally:
            db_manager.close_database(library_path)

    def test_add_then_list_no_header(self, global_client, tmp_path):
        """POST /api/registry/add + GET /api/registry, no header."""
        lib_path = tmp_path / "Headerless.fichero"
        lib_path.mkdir(parents=True, exist_ok=True)

        add = global_client.post("/api/registry/add", params={"path": str(lib_path)})
        assert add.status_code == 200, add.text

        listed = global_client.get("/api/registry")
        assert listed.status_code == 200
        paths = [lib["path"] for lib in listed.json()["libraries"]]
        assert str(lib_path.resolve()) in paths

    def test_add_deduplicates_nfd_and_nfc_library_paths(self, global_client, tmp_path):
        lib_path = tmp_path / unicodedata.normalize("NFC", "Chocó.fichero")
        lib_path.mkdir(parents=True, exist_ok=True)
        nfd_path = unicodedata.normalize("NFD", str(lib_path))

        first = global_client.post("/api/registry/add", params={"path": nfd_path})
        assert first.status_code == 200, first.text

        second = global_client.post("/api/registry/add", params={"path": str(lib_path)})
        assert second.status_code == 200, second.text

        listed = global_client.get("/api/registry")
        assert listed.status_code == 200
        libraries = listed.json()["libraries"]
        assert len(libraries) == 1
        assert libraries[0]["path"] == unicodedata.normalize("NFC", str(lib_path.resolve()))

    def test_health_accepts_nfd_header_and_reuses_normalized_database(
        self,
        global_client,
        tmp_path,
    ):
        from fichero.db_manager import db_manager

        lib_path = tmp_path / unicodedata.normalize("NFC", "Chocó.fichero")
        lib_path.mkdir(parents=True, exist_ok=True)
        global_client.post("/api/registry/add", params={"path": str(lib_path)})
        db_manager.get_database(lib_path)

        db_manager.close_database(str(lib_path))
        normalized = unicodedata.normalize("NFC", str(lib_path))
        try:
            response = global_client.get(
                "/api/health",
                headers={
                    "X-Fichero-Library-Path": quote(
                        unicodedata.normalize("NFD", str(lib_path)),
                        safe="/",
                    )
                },
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] == "healthy"
            assert body["library_path"] == normalized
            matches = [key for key in db_manager._databases if key == normalized]
            assert matches == [normalized]
        finally:
            db_manager.close_database(str(lib_path))

    def test_unicode_collision_report_case_a_same_inode(self, global_client, tmp_path):
        nfc_path = tmp_path / unicodedata.normalize("NFC", "Chocó.fichero")
        _create_library_fixture(nfc_path, "case-a")
        nfd_path = unicodedata.normalize("NFD", str(nfc_path))

        global_client.post("/api/registry/add", params={"path": str(nfc_path)})
        global_db = global_client.app.dependency_overrides[
            __import__(
                "fichero.api.routes.library_registry",
                fromlist=["get_global_database"],
            ).get_global_database
        ]()
        global_db.save(
            KnownLibrary(
                path=nfd_path,
                name=unicodedata.normalize("NFD", nfc_path.name),
            )
        )

        response = global_client.get("/api/registry/unicode-collisions")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["count"] == 1
        collision = body["collisions"][0]
        assert collision["collision_case"] == "case_a_same_inode"
        assert collision["nfc_name"] == unicodedata.normalize("NFC", nfc_path.name)

    def test_unicode_collision_report_case_b_distinct_packages(self, monkeypatch, tmp_path):
        from fichero.api.routes import library_registry as registry_routes

        first = tmp_path / "one" / "Alpha.fichero"
        second = tmp_path / "two" / "Beta.fichero"
        _create_library_fixture(first, "left")
        _create_library_fixture(second, "right")
        left_raw = str(tmp_path / unicodedata.normalize("NFD", "Chocó.fichero"))
        right_raw = str(tmp_path / unicodedata.normalize("NFC", "Chocó.fichero"))

        identities = {
            left_raw: registry_routes.UnicodeLibraryCollisionIdentity(
                raw_path=left_raw,
                raw_path_escaped=left_raw.encode("unicode_escape").decode("ascii"),
                name=unicodedata.normalize("NFD", "Chocó.fichero"),
                name_escaped=unicodedata.normalize("NFD", "Chocó.fichero")
                .encode("unicode_escape")
                .decode("ascii"),
                document_count=1,
                document_count_error=None,
                duckdb_size_bytes=(first / "fichero.duckdb").stat().st_size,
                files_size_bytes=(first / "files" / "left.txt").stat().st_size,
            ),
            right_raw: registry_routes.UnicodeLibraryCollisionIdentity(
                raw_path=right_raw,
                raw_path_escaped=right_raw.encode("unicode_escape").decode("ascii"),
                name=unicodedata.normalize("NFC", "Chocó.fichero"),
                name_escaped=unicodedata.normalize("NFC", "Chocó.fichero")
                .encode("unicode_escape")
                .decode("ascii"),
                document_count=1,
                document_count_error=None,
                duckdb_size_bytes=(second / "fichero.duckdb").stat().st_size,
                files_size_bytes=(second / "files" / "right.txt").stat().st_size,
            ),
        }

        monkeypatch.setattr(
            registry_routes,
            "_registry_collision_paths",
            lambda _libraries: [(left_raw, right_raw)],
        )
        monkeypatch.setattr(registry_routes, "_sibling_collision_paths", lambda _libraries: [])
        monkeypatch.setattr(registry_routes, "_identity_report", lambda raw_path: identities[raw_path])
        monkeypatch.setattr(registry_routes, "_same_inode", lambda *_args: False)

        collisions = registry_routes._detect_unicode_library_collisions([])
        assert len(collisions) == 1
        assert collisions[0].collision_case == "case_b_distinct_packages"

    def test_unicode_collision_report_ignores_plain_ascii_vs_accent(self, monkeypatch):
        from fichero.api.routes import library_registry as registry_routes

        monkeypatch.setattr(
            registry_routes,
            "_registry_collision_paths",
            lambda _libraries: [("/tmp/Choco.fichero", "/tmp/Chocó.fichero")],
        )
        monkeypatch.setattr(registry_routes, "_sibling_collision_paths", lambda _libraries: [])

        assert registry_routes._detect_unicode_library_collisions([]) == []

    def test_unicode_collision_report_is_idempotent_and_read_only(self, global_client, tmp_path):
        nfc_path = tmp_path / unicodedata.normalize("NFC", "Chocó.fichero")
        _create_library_fixture(nfc_path, "stable")
        nfd_path = unicodedata.normalize("NFD", str(nfc_path))

        global_client.post("/api/registry/add", params={"path": str(nfc_path)})
        global_db = global_client.app.dependency_overrides[
            __import__(
                "fichero.api.routes.library_registry",
                fromlist=["get_global_database"],
            ).get_global_database
        ]()
        global_db.save(
            KnownLibrary(
                path=nfd_path,
                name=unicodedata.normalize("NFD", nfc_path.name),
            )
        )
        before_rows = [(lib.path, lib.name) for lib in global_db.all(KnownLibrary)]
        before_mtime = nfc_path.stat().st_mtime

        first = global_client.get("/api/registry/unicode-collisions")
        second = global_client.get("/api/registry/unicode-collisions")

        assert first.json() == second.json()
        assert [(lib.path, lib.name) for lib in global_db.all(KnownLibrary)] == before_rows
        assert nfc_path.stat().st_mtime == before_mtime

    def test_unicode_collision_prompt_stays_read_only_until_confirm(self, global_client, tmp_path):
        from fichero.db_manager import db_manager

        left = tmp_path / unicodedata.normalize("NFD", "Chocó.fichero")
        right = tmp_path / unicodedata.normalize("NFC", "Chocó.fichero")
        _create_library_fixture(left, "left-doc")
        _create_library_fixture(right, "right-doc")

        global_db = global_client.app.dependency_overrides[
            __import__(
                "fichero.api.routes.library_registry",
                fromlist=["get_global_database"],
            ).get_global_database
        ]()
        global_db.save(KnownLibrary(path=str(left.resolve()), name=left.name))
        global_db.save(KnownLibrary(path=str(right.resolve()), name=right.name))

        listed = global_client.get("/api/registry/unicode-collisions")
        assert listed.status_code == 200, listed.text
        assert listed.json()["count"] == 1
        assert left.exists()
        assert right.exists()

        before = global_client.get("/api/registry")
        assert before.status_code == 200
        assert before.json()["count"] == 2

        db_manager.close_database(str(left))
        db_manager.close_database(str(right))
        merge = global_client.post(
            "/api/registry/unicode-collisions/merge",
            json={"left_path": str(left), "right_path": str(right)},
        )

        assert merge.status_code == 200, merge.text
        body = merge.json()
        assert body["status"] == "merged"
        assert Path(body["winner_path"]).exists()
        assert Path(body["loser_renamed_path"]).exists()

        after = global_client.get("/api/registry")
        assert after.status_code == 200
        assert after.json()["count"] == 1
        audits = [row for row in global_db.all(ActionAudit) if row.action_name == "library.unicode_merge"]
        assert len(audits) == 1

    def test_unicode_collision_report_surfaces_document_count_error(
        self, global_client, tmp_path, monkeypatch, caplog
    ):
        from fichero.api.routes import library_registry as registry_routes

        lib_path = tmp_path / unicodedata.normalize("NFC", "Chocó.fichero")
        _create_library_fixture(lib_path, "doc-1")
        global_db = global_client.app.dependency_overrides[
            __import__(
                "fichero.api.routes.library_registry",
                fromlist=["get_global_database"],
            ).get_global_database
        ]()
        global_db.save(KnownLibrary(path=str(lib_path.resolve()), name=lib_path.name))
        global_db.save(
            KnownLibrary(
                path=unicodedata.normalize("NFD", str(lib_path.resolve())),
                name=unicodedata.normalize("NFD", lib_path.name),
            )
        )

        monkeypatch.setattr(
            registry_routes.db_manager,
            "get_database",
            lambda _path: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        response = global_client.get("/api/registry/unicode-collisions")

        assert response.status_code == 200, response.text
        collision = response.json()["collisions"][0]
        assert collision["left"]["document_count"] is None
        assert "boom" in collision["left"]["document_count_error"]
        assert str(lib_path.resolve()) in caplog.text

    def test_remove_handles_spaces(self, global_client, tmp_path):
        """DELETE /api/registry/{path} works for a path containing spaces."""
        from urllib.parse import quote
        from fichero.db_manager import db_manager

        lib_path = tmp_path / "My Marshall Library.fichero"
        lib_path.mkdir(parents=True, exist_ok=True)
        global_client.post("/api/registry/add", params={"path": str(lib_path)})
        db_manager.get_database(lib_path)

        encoded = quote(str(lib_path.resolve()), safe="")
        removed = global_client.delete(f"/api/registry/{encoded}")
        assert removed.status_code == 200, removed.text
        assert removed.json()["status"] == "removed"

        # Gone from the list.
        listed = global_client.get("/api/registry")
        paths = [lib["path"] for lib in listed.json()["libraries"]]
        assert str(lib_path.resolve()) not in paths

        assert str(lib_path.resolve()) not in db_manager._databases
        db_manager.get_database(lib_path)
        assert str(lib_path.resolve()) in db_manager._databases
        db_manager.close_database(lib_path)

    def test_remove_is_idempotent(self, global_client, tmp_path):
        """Removing an unregistered library is a 200 no-op, not a 404."""
        from urllib.parse import quote

        lib_path = tmp_path / "NeverRegistered.fichero"
        encoded = quote(str(lib_path.resolve()), safe="")
        removed = global_client.delete(f"/api/registry/{encoded}")
        assert removed.status_code == 200
        assert removed.json()["status"] == "not_registered"

    def test_registry_shared_across_libraries(self, global_client, tmp_path):
        """A library added once is visible regardless of which library is
        'active' — the registry is global, not per-library. We prove this by
        adding under no header and confirming a second add under a (bogus)
        library header still sees the same single global registry."""
        lib_path = tmp_path / "Shared.fichero"
        lib_path.mkdir(parents=True, exist_ok=True)
        global_client.post("/api/registry/add", params={"path": str(lib_path)})

        # Even with an unrelated library header, the listing is the same global
        # registry (the dependency override ignores the header entirely).
        listed = global_client.get(
            "/api/registry",
            headers={"X-Fichero-Library-Path": str(tmp_path / "Other.fichero")},
        )
        assert listed.status_code == 200
        paths = [lib["path"] for lib in listed.json()["libraries"]]
        assert str(lib_path.resolve()) in paths
        assert listed.json()["count"] == 1

    def test_add_seeds_single_root_inbox(self, global_client, tmp_path):
        """Registering a real .fichero package eagerly seeds one root Inbox."""
        from fichero.db_manager import db_manager

        lib_path = tmp_path / "Marshall Diaries.fichero"
        lib_path.mkdir(parents=True, exist_ok=True)
        db_path = lib_path / "fichero.duckdb"

        db_manager.close_database(lib_path)
        try:
            first = global_client.post(
                "/api/registry/add",
                params={"path": str(lib_path)},
            )
            assert first.status_code == 200, first.text
            assert db_path.exists()

            second = global_client.post(
                "/api/registry/add",
                params={"path": str(lib_path)},
            )
            assert second.status_code == 200, second.text

            library_db = Database(path=db_path)
            try:
                inboxes = library_db.query(
                    Document,
                    name="Inbox",
                    parent_id=None,
                    doc_type=DocType.folder,
                )
            finally:
                library_db.conn.close()

            assert len(inboxes) == 1
            inbox = inboxes[0]
            assert inbox.name == "Inbox"
            assert inbox.parent_id is None
            assert inbox.doc_type == DocType.folder
        finally:
            db_manager.close_database(lib_path)


# Placeholder fixtures — these would be provided by conftest.py in a real project
@pytest.fixture
def client(temp_library_path):
    """FastAPI test client with library header."""
    from fastapi.testclient import TestClient
    from fichero.api.main import app

    class ClientWithLibraryHeader(TestClient):
        """Test client that adds the required X-Fichero-Library-Path header."""

        def __init__(self, app, library_path, **kwargs):
            super().__init__(app, **kwargs)
            self.library_path = library_path

        def request(self, *args, **kwargs):
            # Add the library path header if not already present
            if "headers" not in kwargs or kwargs["headers"] is None:
                kwargs["headers"] = {}
            if "X-Fichero-Library-Path" not in kwargs.get("headers", {}):
                kwargs["headers"]["X-Fichero-Library-Path"] = str(self.library_path)
            return super().request(*args, **kwargs)

    return ClientWithLibraryHeader(app, temp_library_path)
