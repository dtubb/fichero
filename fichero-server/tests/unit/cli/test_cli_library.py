"""Unit tests for CLI library lifecycle commands (#1130).

Tests the 8 new library registry commands: list, add, remove, create, delete, open, close, reset.
These commands call the backend registry endpoints, unlike the older filesystem-walk `library list`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_server.models import (
    KnownLibrary,
    LibraryRegistryResponse,
    LibrarySnapshot,
    UnicodeLibraryCollision,
    UnicodeLibraryCollisionIdentity,
    UnicodeLibraryCollisionResponse,
)

runner = CliRunner()


class RegistryFakeClient:
    """Fake client for registry operations."""

    instances: list["RegistryFakeClient"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls: list[tuple] = []
        RegistryFakeClient.instances.append(self)
        # Simulated registry state
        self.libraries = [
            KnownLibrary(
                id="lib-1",
                path="/Users/daniel/Documents/Test.fichero",
                name="Test Library",
                added_at=datetime(2026, 5, 15),
                last_accessed=datetime(2026, 5, 17),
            )
        ]

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def close(self):
        pass

    def list_known_libraries(self) -> LibraryRegistryResponse:
        self.calls.append(("list_known_libraries",))
        return LibraryRegistryResponse(libraries=self.libraries, count=len(self.libraries))

    def add_known_library(self, path: str, name: str | None = None) -> KnownLibrary:
        self.calls.append(("add_known_library", path, name))
        lib = KnownLibrary(
            id="lib-new",
            path=path,
            name=name or Path(path).name,
            added_at=datetime.now(),
            last_accessed=datetime.now(),
        )
        self.libraries.append(lib)
        return lib

    def remove_known_library(self, path: str) -> dict:
        self.calls.append(("remove_known_library", path))
        self.libraries = [lib for lib in self.libraries if lib.path != path]
        return {"status": "removed", "path": path}

    def update_library_access(self, path: str) -> KnownLibrary:
        self.calls.append(("update_library_access", path))
        for lib in self.libraries:
            if lib.path == path:
                lib.last_accessed = datetime.now()
                return lib
        raise ValueError(f"Library not found: {path}")

    def create_library(self, path: str):
        self.calls.append(("create_library", path))
        return {"created": True, "path": path, "tables_initialized": True}

    def create_library_snapshot(
        self,
        path: str,
        *,
        reason: str = "",
        initiator: str = "user",
    ) -> LibrarySnapshot:
        self.calls.append(("create_library_snapshot", path, reason, initiator))
        return LibrarySnapshot(
            id="snap-1",
            library_path=path,
            library_name=Path(path).stem,
            reason=reason,
            snapshot_path="/tmp/snap-1",
            duckdb_path="Test/snap-1/duckdb_file",
            lance_path="Test/snap-1/vectors_copy",
            duckdb_size_bytes=123,
            lance_size_bytes=456,
        )

    def list_library_snapshots(
        self,
        *,
        library_name: str | None = None,
        include_expired: bool = False,
    ) -> dict:
        self.calls.append(("list_library_snapshots", library_name, include_expired))
        return {
            "snapshots": [
                {
                    "id": "snap-1",
                    "library_name": library_name or "Test",
                    "reason": "manual checkpoint",
                }
            ],
            "total": 1,
        }

    def restore_library_snapshot(self, snapshot_id: str) -> dict:
        self.calls.append(("restore_library_snapshot", snapshot_id))
        return {
            "snapshot_id": snapshot_id,
            "library_path": "/Users/daniel/Documents/Test.fichero",
            "duckdb_restored_path": "/Users/daniel/Documents/Test.fichero/fichero.duckdb",
            "lance_restored_path": "/Users/daniel/Documents/Test.fichero/vectors",
            "note": "restored",
        }

    def list_unicode_library_collisions(self) -> UnicodeLibraryCollisionResponse:
        self.calls.append(("list_unicode_library_collisions",))
        collision = UnicodeLibraryCollision(
            left=UnicodeLibraryCollisionIdentity(
                raw_path="/tmp/Choco\u0301.fichero",
                raw_path_escaped="/tmp/Choco\\u0301.fichero",
                name="Choco\u0301.fichero",
                name_escaped="Choco\\u0301.fichero",
                document_count=1,
                document_count_error=None,
                duckdb_size_bytes=12,
                files_size_bytes=34,
            ),
            right=UnicodeLibraryCollisionIdentity(
                raw_path="/tmp/Chocó.fichero",
                raw_path_escaped="/tmp/Choc\\xf3.fichero",
                name="Chocó.fichero",
                name_escaped="Choc\\xf3.fichero",
                document_count=2,
                document_count_error=None,
                duckdb_size_bytes=56,
                files_size_bytes=78,
            ),
            nfc_path="/tmp/Chocó.fichero",
            nfc_name="Chocó.fichero",
            collision_case="case_b_distinct_packages",
        )
        return UnicodeLibraryCollisionResponse(collisions=[collision], count=1)


def _last_client() -> RegistryFakeClient:
    return RegistryFakeClient.instances[-1]


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    RegistryFakeClient.instances = []
    monkeypatch.setattr(cli, "FicheroClient", RegistryFakeClient)


# -- library list --
def test_library_list_shows_all_registered():
    """List shows registered libraries sorted by last_accessed."""
    result = runner.invoke(cli.app, ["library", "list"])
    assert result.exit_code == 0
    assert ("list_known_libraries",) in _last_client().calls
    # Should show the library from the fake client
    assert "Test Library" in result.output or "Test.fichero" in result.output


def test_library_list_empty(monkeypatch):
    """When no libraries are registered, display '(no libraries)'."""

    class EmptyRegistryFakeClient(RegistryFakeClient):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.libraries = []  # Start empty

    monkeypatch.setattr(cli, "FicheroClient", EmptyRegistryFakeClient)
    result = runner.invoke(cli.app, ["library", "list"])
    assert result.exit_code == 0
    assert "(no libraries)" in result.output


def test_library_list_json():
    """List with --json flag returns JSON array."""
    result = runner.invoke(cli.app, ["--json", "library", "list"])
    assert result.exit_code == 0
    # Should be a list of KnownLibrary objects rendered as JSON
    assert "Test" in result.output or "fichero" in result.output


def test_library_unicode_collisions():
    result = runner.invoke(cli.app, ["library", "unicode-collisions"])
    assert result.exit_code == 0
    assert ("list_unicode_library_collisions",) in _last_client().calls


# -- library add --
def test_library_add():
    """Add registers a new library path."""
    result = runner.invoke(cli.app, ["library", "add", "~/Documents/MyLib.fichero"])
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "add_known_library")
    # Path should be expanded
    assert "MyLib.fichero" in call[1]
    assert "Added:" in result.output


def test_library_add_json():
    """Add with --json returns JSON response."""
    result = runner.invoke(
        cli.app, ["--json", "library", "add", "~/Documents/MyLib.fichero"]
    )
    assert result.exit_code == 0
    assert "status" in result.output


# -- library remove --
def test_library_remove():
    """Remove unregisters a library."""
    result = runner.invoke(
        cli.app, ["library", "remove", "/Users/daniel/Documents/Test.fichero"]
    )
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "remove_known_library")
    assert "Test.fichero" in call[1]
    assert "Removed:" in result.output


# -- library create --
def test_library_create():
    """Create makes a new library and registers it."""
    result = runner.invoke(cli.app, ["library", "create", "~/Documents/NewLib.fichero"])
    assert result.exit_code == 0
    calls = _last_client().calls
    # Should call both create_library and add_known_library
    assert any(c[0] == "create_library" for c in calls)
    assert any(c[0] == "add_known_library" for c in calls)
    assert "Created and registered:" in result.output


def test_library_snapshot_uses_global_library_path():
    """Snapshot creates a point-in-time snapshot for the active library."""
    result = runner.invoke(
        cli.app,
        [
            "--library",
            "/Users/daniel/Documents/Test.fichero",
            "library",
            "snapshot",
            "--reason",
            "before migration",
        ],
    )
    assert result.exit_code == 0
    assert (
        "create_library_snapshot",
        "/Users/daniel/Documents/Test.fichero",
        "before migration",
        "user",
    ) in _last_client().calls
    assert "snap-1" in result.output


def test_library_snapshots_lists_snapshots():
    """Snapshots lists available library snapshots."""
    result = runner.invoke(
        cli.app,
        ["library", "snapshots", "--library-name", "Test"],
    )
    assert result.exit_code == 0
    assert ("list_library_snapshots", "Test", False) in _last_client().calls
    assert "snap-1" in result.output


def test_library_restore_requires_confirmation():
    """Restore aborts when confirmation is declined."""
    result = runner.invoke(cli.app, ["library", "restore", "snap-1"], input="n\n")
    assert result.exit_code == 1


def test_library_restore_yes():
    """Restore calls the backend when confirmed by flag."""
    result = runner.invoke(cli.app, ["library", "restore", "snap-1", "--yes"])
    assert result.exit_code == 0
    assert ("restore_library_snapshot", "snap-1") in _last_client().calls
    assert "snap-1" in result.output


# -- library delete --
def test_library_delete_yes():
    """Delete removes a library with --yes flag."""
    result = runner.invoke(
        cli.app,
        ["library", "delete", "/Users/daniel/Documents/Test.fichero", "--yes"],
    )
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "remove_known_library")
    assert "Test.fichero" in call[1]
    assert "Deleted:" in result.output


def test_library_delete_no_confirm():
    """Delete aborts when user declines confirmation."""
    result = runner.invoke(
        cli.app, ["library", "delete", "~/Documents/MyLib.fichero"], input="n\n"
    )
    assert result.exit_code == 1


def test_library_delete_yes_confirm():
    """Delete proceeds when user confirms."""
    result = runner.invoke(
        cli.app, ["library", "delete", "/Users/daniel/Documents/Test.fichero"], input="y\n"
    )
    assert result.exit_code == 0
    assert "Deleted:" in result.output


# -- library open --
def test_library_open():
    """Open marks a library as accessed."""
    result = runner.invoke(
        cli.app, ["library", "open", "/Users/daniel/Documents/Test.fichero"]
    )
    assert result.exit_code == 0
    call = next(c for c in _last_client().calls if c[0] == "update_library_access")
    assert "Test.fichero" in call[1]
    assert "Activated:" in result.output


# -- library close --
def test_library_close():
    """Close is a no-op but should not error."""
    result = runner.invoke(
        cli.app, ["library", "close", "~/Documents/MyLib.fichero"]
    )
    assert result.exit_code == 0
    assert "Closed:" in result.output


# -- library reset --
def test_library_reset_yes():
    """Reset clears all registry entries with --yes flag."""
    result = runner.invoke(cli.app, ["library", "reset", "--yes"])
    assert result.exit_code == 0
    calls = _last_client().calls
    # Should list all libraries and remove each one
    assert ("list_known_libraries",) in calls
    assert any(c[0] == "remove_known_library" for c in calls)
    assert "Reset complete" in result.output


def test_library_reset_no_confirm():
    """Reset aborts when user declines confirmation."""
    result = runner.invoke(cli.app, ["library", "reset"], input="n\n")
    assert result.exit_code == 1


def test_library_reset_yes_confirm():
    """Reset proceeds when user confirms."""
    result = runner.invoke(cli.app, ["library", "reset"], input="y\n")
    assert result.exit_code == 0
    assert "Reset complete" in result.output
