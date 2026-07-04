from __future__ import annotations

import unicodedata
from datetime import datetime
from pathlib import Path

from fichero.api.routes import library_registry as registry_routes
from fichero.models import KnownLibrary, UnicodeLibraryCollisionIdentity


def _identity(raw_path: str) -> UnicodeLibraryCollisionIdentity:
    name = Path(raw_path).name
    return UnicodeLibraryCollisionIdentity(
        raw_path=raw_path,
        raw_path_escaped=raw_path.encode("unicode_escape").decode("ascii"),
        name=name,
        name_escaped=name.encode("unicode_escape").decode("ascii"),
        document_count=0,
        document_count_error=None,
        duckdb_size_bytes=0,
        files_size_bytes=0,
        modified_at=datetime(2026, 7, 4, 12, 0, 0),
    )


def test_detect_unicode_collisions_returns_empty_for_empty_registry() -> None:
    assert registry_routes._detect_unicode_library_collisions([]) == []


def test_detect_unicode_collisions_flags_composed_and_decomposed_paths(
    monkeypatch,
) -> None:
    left = "/tmp/" + unicodedata.normalize("NFD", "Chocó.fichero")
    right = "/tmp/" + unicodedata.normalize("NFC", "Chocó.fichero")

    monkeypatch.setattr(
        registry_routes,
        "_registry_collision_paths",
        lambda _libraries: [(left, right)],
    )
    monkeypatch.setattr(registry_routes, "_sibling_collision_paths", lambda _libraries: [])
    monkeypatch.setattr(
        registry_routes,
        "_identity_report",
        lambda raw_path: _identity(raw_path),
    )
    monkeypatch.setattr(registry_routes, "_same_inode", lambda *_args: False)

    collisions = registry_routes._detect_unicode_library_collisions([])

    assert len(collisions) == 1
    assert collisions[0].collision_case == "case_b_distinct_packages"
    assert collisions[0].nfc_name == unicodedata.normalize("NFC", "Chocó.fichero")
    assert collisions[0].nfc_path == right


def test_detect_unicode_collisions_marks_same_inode_aliases_case_a(
    monkeypatch,
) -> None:
    left = "/tmp/" + unicodedata.normalize("NFD", "Chocó.fichero")
    right = "/tmp/" + unicodedata.normalize("NFC", "Chocó.fichero")

    monkeypatch.setattr(
        registry_routes,
        "_registry_collision_paths",
        lambda _libraries: [(left, right)],
    )
    monkeypatch.setattr(registry_routes, "_sibling_collision_paths", lambda _libraries: [])
    monkeypatch.setattr(
        registry_routes,
        "_identity_report",
        lambda raw_path: _identity(raw_path),
    )
    monkeypatch.setattr(registry_routes, "_same_inode", lambda *_args: True)

    collisions = registry_routes._detect_unicode_library_collisions([])

    assert len(collisions) == 1
    assert collisions[0].collision_case == "case_a_same_inode"


def test_detect_unicode_collisions_ignores_ascii_vs_latin1_mojibake(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        registry_routes,
        "_registry_collision_paths",
        lambda _libraries: [("/tmp/Choco.fichero", "/tmp/ChocoÌ\x81.fichero")],
    )
    monkeypatch.setattr(registry_routes, "_sibling_collision_paths", lambda _libraries: [])

    assert registry_routes._detect_unicode_library_collisions([]) == []


def test_registry_collision_paths_skips_already_normalized_singletons() -> None:
    library = KnownLibrary(path="/tmp/Library.fichero", name="Library.fichero")

    assert registry_routes._registry_collision_paths([library]) == []
