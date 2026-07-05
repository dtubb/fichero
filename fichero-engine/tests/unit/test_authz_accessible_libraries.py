from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero import accounts, authz
from fichero.api.routes.authz import list_accessible_libraries
from fichero.db import Database
from fichero.models import KnownLibrary


@pytest.fixture
def users(app_db):
    owner = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    editor = app_db.create_user(
        username="editor",
        display_name="Editor",
        password_hash=accounts.hash_password("password"),
    )
    viewer = app_db.create_user(
        username="viewer",
        display_name="Viewer",
        password_hash=accounts.hash_password("password"),
    )
    stranger = app_db.create_user(
        username="stranger",
        display_name="Stranger",
        password_hash=accounts.hash_password("password"),
    )
    return SimpleNamespace(owner=owner, editor=editor, viewer=viewer, stranger=stranger)


@pytest.fixture
def global_db(tmp_path):
    return Database(tmp_path / "global.fichero" / "fichero.duckdb")


def _request(user=None, *, bootstrap=False):
    return SimpleNamespace(state=SimpleNamespace(user=user, bootstrap_auth=bootstrap))


def _known_library(registry_db, path: str, name: str) -> KnownLibrary:
    library = KnownLibrary(path=path, name=name)
    registry_db.save(library)
    return library


def _grant(app_db, user, library_path: str, role: str) -> None:
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


def test_bootstrap_sees_all_known_libraries_as_owner(global_db):
    first = _known_library(global_db, "/tmp/alpha.fichero", "Alpha")
    second = _known_library(global_db, "/tmp/beta.fichero", "Beta")
    first_path = authz.normalize_library_path(first.path)
    second_path = authz.normalize_library_path(second.path)

    libraries = list_accessible_libraries(_request(bootstrap=True), global_db)

    assert libraries.count == 2
    assert [
        (library.library_path, library.library_name, library.role)
        for library in libraries.items
    ] == [
        (second_path, "Beta", authz.ROLE_OWNER),
        (first_path, "Alpha", authz.ROLE_OWNER),
    ]


def test_user_sees_only_their_grants_with_correct_roles(app_db, global_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    visible = _known_library(global_db, "/tmp/visible.fichero", "Visible")
    hidden = _known_library(global_db, "/tmp/hidden.fichero", "Hidden")
    _grant(app_db, users.viewer, visible.path, authz.ROLE_VIEWER)
    _grant(app_db, users.editor, hidden.path, authz.ROLE_EDITOR)
    visible_path = authz.normalize_library_path(visible.path)

    libraries = list_accessible_libraries(_request(users.viewer), global_db)

    assert libraries.count == 1
    assert [
        (library.library_path, library.library_name, library.role)
        for library in libraries.items
    ] == [
        (visible_path, "Visible", authz.ROLE_VIEWER),
    ]


def test_user_with_zero_grants_gets_empty_list(app_db, global_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    _known_library(global_db, "/tmp/visible.fichero", "Visible")

    libraries = list_accessible_libraries(_request(users.stranger), global_db)

    assert libraries.count == 0
    assert libraries.items == []


def test_no_credential_is_401(global_db):
    with pytest.raises(HTTPException) as exc:
        list_accessible_libraries(_request(None), global_db)

    assert exc.value.status_code == 401


def test_user_a_never_sees_library_only_granted_to_user_b(
    app_db, global_db, users, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_a = _known_library(global_db, "/tmp/a.fichero", "A")
    library_b = _known_library(global_db, "/tmp/b.fichero", "B")
    _grant(app_db, users.viewer, library_a.path, authz.ROLE_VIEWER)
    _grant(app_db, users.editor, library_b.path, authz.ROLE_EDITOR)
    library_a_path = authz.normalize_library_path(library_a.path)
    library_b_path = authz.normalize_library_path(library_b.path)

    visible_paths = [
        library.library_path
        for library in list_accessible_libraries(_request(users.viewer), global_db).items
    ]

    assert visible_paths == [library_a_path]
    assert library_b_path not in visible_paths


def test_role_row_without_registry_name_falls_back_to_package_name(
    app_db, global_db, users, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    path = str(Path("/tmp/nameless.fichero"))
    _grant(app_db, users.viewer, path, authz.ROLE_VIEWER)

    libraries = list_accessible_libraries(_request(users.viewer), global_db)

    assert [(library.library_name, library.role) for library in libraries.items] == [
        ("nameless.fichero", authz.ROLE_VIEWER),
    ]
