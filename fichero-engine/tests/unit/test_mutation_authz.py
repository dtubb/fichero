from __future__ import annotations

import importlib
from types import SimpleNamespace
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

from fichero import accounts, authz
from fichero.knowledge_models import Note
from fichero.models import ActionAudit, AccountUser, Document, KnowledgeClaim, KnowledgeEntity


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
    return SimpleNamespace(owner=owner, editor=editor, viewer=viewer)


def _grant(app_db, user: AccountUser, library_path: str, role: str) -> None:
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


@pytest.fixture
def multiuser_client(test_package, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")

    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    client = TestClient(
        api_main.app,
        headers={"X-Fichero-Library-Path": quote(str(test_package), safe="/")},
    )

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
        importlib.reload(api_main)


CASES = [
    {
        "id": "note",
        "path": "/api/notes",
        "payload": {"title": "ACL Note", "body": "Denied for viewer"},
        "status_code": 200,
        "action_name": "note.create",
        "snapshot": lambda db: len(db.all(Note)),
    },
    {
        "id": "document",
        "path": "/api/documents",
        "payload": {"name": "ACL Document"},
        "status_code": 201,
        "action_name": "document.create",
        "snapshot": lambda db: len(db.all(Document)),
    },
    {
        "id": "claim",
        "path": "/api/claims",
        "payload": {"text": "ACL Claim"},
        "status_code": 200,
        "action_name": "claim.create",
        "snapshot": lambda db: len(db.all(KnowledgeClaim)),
    },
    {
        "id": "entity",
        "path": "/api/entities",
        "payload": {"canonical_name": "ACL Entity", "entity_type": "person"},
        "status_code": 200,
        "action_name": "entity.create",
        "snapshot": lambda db: len(db.all(KnowledgeEntity)),
    },
]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_audited_create_mutations_enforce_multiuser_write_authz(
    case, db, app_db, users, multiuser_client
):
    client, login, library_path = multiuser_client
    _grant(app_db, users.viewer, library_path, "viewer")
    _grant(app_db, users.editor, library_path, "editor")

    viewer_headers = login("viewer")
    editor_headers = login("editor")

    before_state = case["snapshot"](db)
    before_audits = len(db.all(ActionAudit))

    denied = client.post(case["path"], headers=viewer_headers, json=case["payload"])
    assert denied.status_code == 403
    assert case["snapshot"](db) == before_state
    assert len(db.all(ActionAudit)) == before_audits

    allowed = client.post(case["path"], headers=editor_headers, json=case["payload"])
    assert allowed.status_code == case["status_code"]
    assert case["snapshot"](db) != before_state

    audits = db.all(ActionAudit)
    assert len(audits) == before_audits + 1
    assert audits[-1].action_name == case["action_name"]
    assert audits[-1].actor == "editor"
