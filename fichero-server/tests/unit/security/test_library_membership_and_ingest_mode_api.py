from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.models import AccountUser, Document


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
    return SimpleNamespace(
        owner=owner,
        editor=editor,
        viewer=viewer,
        stranger=stranger,
    )


def _grant(app_db, user: AccountUser, library_path: str | Path, role: str) -> None:
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


@pytest.fixture
def multiuser_client(app_db, test_package, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")

    import fichero_server.api.main as api_main

    api_main = __import__("importlib").reload(api_main)
    from fichero_server.api.routes.ai.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    client = TestClient(api_main.app)

    def _login(username: str) -> dict[str, str]:
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": "password"},
        )
        assert response.status_code == 200
        token = response.json()["session_token"]
        return {"Authorization": f"Bearer {token}"}

    try:
        yield client, _login, str(test_package)
    finally:
        client.close()
        api_main.app.dependency_overrides.clear()
        monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
        __import__("importlib").reload(api_main)


def _headers(auth_headers: dict[str, str], library_path: str | Path) -> dict[str, str]:
    return {
        **auth_headers,
        "X-Fichero-Library-Path": quote(str(library_path), safe="/"),
    }


def test_library_membership_owner_sees_members_and_roles(
    app_db, users, multiuser_client
):
    client, login, library_path = multiuser_client
    _grant(app_db, users.owner, library_path, "owner")
    _grant(app_db, users.editor, library_path, "editor")
    _grant(app_db, users.viewer, library_path, "viewer")

    response = client.get(
        "/api/authz/members",
        headers=_headers(login("owner"), library_path),
    )

    assert response.status_code == 200
    members = response.json()["members"]
    assert {member["username"]: member["role"] for member in members} == {
        "owner": "owner",
        "editor": "editor",
        "viewer": "viewer",
    }


def test_library_membership_non_member_gets_403_without_leak(
    app_db, users, multiuser_client
):
    client, login, library_path = multiuser_client
    _grant(app_db, users.owner, library_path, "owner")
    _grant(app_db, users.editor, library_path, "editor")

    denied = client.get(
        "/api/authz/members",
        headers=_headers(login("stranger"), library_path),
    )

    assert denied.status_code == 403
    assert users.owner.id not in denied.text
    assert users.editor.id not in denied.text


def test_library_membership_my_role_endpoint_returns_current_role(
    app_db, users, multiuser_client
):
    client, login, library_path = multiuser_client
    _grant(app_db, users.editor, library_path, "editor")

    response = client.get(
        "/api/authz/library",
        headers=_headers(login("editor"), library_path),
    )

    assert response.status_code == 200
    assert response.json()["current_user_role"] == "editor"


def test_ingest_file_mode_link_copy_move_apply(client, db, test_package, tmp_path):
    link_src = tmp_path / "link.txt"
    copy_src = tmp_path / "copy.txt"
    move_src = tmp_path / "move.txt"
    link_src.write_text("link me", encoding="utf-8")
    copy_src.write_text("copy me", encoding="utf-8")
    move_src.write_text("move me", encoding="utf-8")

    link_response = client.post(
        "/api/ingest/file",
        json={"path": str(link_src), "mode": "link"},
    )
    copy_response = client.post(
        "/api/ingest/file",
        json={"path": str(copy_src), "mode": "copy"},
    )
    move_response = client.post(
        "/api/ingest/file",
        json={"path": str(move_src), "mode": "move"},
    )

    assert link_response.status_code == 200, link_response.text
    assert copy_response.status_code == 200, copy_response.text
    assert move_response.status_code == 200, move_response.text

    link_doc = db.get(Document, link_response.json()["id"])
    copy_doc = db.get(Document, copy_response.json()["id"])
    move_doc = db.get(Document, move_response.json()["id"])

    assert link_doc is not None
    assert copy_doc is not None
    assert move_doc is not None

    assert link_src.exists()
    assert copy_src.exists()
    assert not move_src.exists()

    assert link_doc.path == str(link_src)
    assert (link_doc.metadata or {}).get("ingest_mode") == "link"

    assert copy_doc.path != str(copy_src)
    assert (copy_doc.metadata or {}).get("ingest_mode") == "copy"
    assert copy_doc.bookmark is None
    assert (Path(test_package) / copy_doc.path).exists()

    assert move_doc.path != str(move_src)
    assert (move_doc.metadata or {}).get("ingest_mode") == "move"
    assert move_doc.bookmark is None
    assert (Path(test_package) / move_doc.path).exists()
