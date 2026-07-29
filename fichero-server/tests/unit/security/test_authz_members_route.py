"""Route tests for the #2869 A1 library-membership read/role-set API.

Exercises ``GET /api/authz/members`` (owner-gated join of roles + accounts) and
``PUT /api/authz/members`` (typed surface over the audited ``acl.set`` action).
The handlers are called directly with a fake request so no live server or
uvicorn lock is involved.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import fichero_server.api.routes.actions_registry  # noqa: F401 - registers acl.set
from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.actions.registry import ActionContext
from fichero_server.api.routes.authz import (
    list_library_members,
    revoke_library_member_role,
    set_library_member_role,
)
from fichero_server.models import AccountUser, SetLibraryRoleRequest


@pytest.fixture
def users(app_db):
    owner = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    viewer = app_db.create_user(
        username="viewer",
        display_name="Viewer",
        password_hash=accounts.hash_password("password"),
    )
    return SimpleNamespace(owner=owner, viewer=viewer)


def _request(user: AccountUser | None):
    return SimpleNamespace(state=SimpleNamespace(user=user))


def _grant(app_db, user: AccountUser, library_path: str, role: str) -> None:
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


def test_members_join_returns_display_names(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    _grant(app_db, users.owner, library_path, authz.ROLE_OWNER)
    _grant(app_db, users.viewer, library_path, authz.ROLE_VIEWER)

    resp = list_library_members(_request(users.owner), library_path)

    by_user = {m.user_id: m for m in resp.members}
    assert resp.count == 2
    assert by_user[users.owner.id].display_name == "Owner"
    assert by_user[users.owner.id].is_owner_account is True
    assert by_user[users.viewer.id].display_name == "Viewer"
    assert by_user[users.viewer.id].role == authz.ROLE_VIEWER


def test_members_denies_non_owner(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    _grant(app_db, users.owner, library_path, authz.ROLE_OWNER)
    _grant(app_db, users.viewer, library_path, authz.ROLE_VIEWER)

    with pytest.raises(HTTPException) as exc:
        list_library_members(_request(users.viewer), library_path)
    assert exc.value.status_code == 403


def test_members_ungated_when_multiuser_off(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    library_path = str(db.path.parent)
    _grant(app_db, users.viewer, library_path, authz.ROLE_VIEWER)

    # No session user, no owner check — single-user mode still returns rows.
    resp = list_library_members(_request(None), library_path)
    assert resp.count == 1
    assert resp.members[0].role == authz.ROLE_VIEWER


def test_set_role_goes_through_audited_action(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    normalized = authz.normalize_library_path(library_path)
    _grant(app_db, users.owner, library_path, authz.ROLE_OWNER)
    _grant(app_db, users.viewer, library_path, authz.ROLE_VIEWER)

    ctx = ActionContext(actor=users.owner.id, library_path=normalized)
    body = SetLibraryRoleRequest(user=users.viewer.id, role=authz.ROLE_EDITOR)

    resp = set_library_member_role(body, _request(users.owner), db, ctx, library_path)

    by_user = {m.user_id: m for m in resp.members}
    assert by_user[users.viewer.id].role == authz.ROLE_EDITOR
    # The mutation went through the registry choke point → an audit row exists.
    from fichero_server.models import ActionAudit

    audits = [a for a in db.all(ActionAudit) if a.action_name == "acl.set"]
    assert audits, "acl.set should have produced an audit row"


def test_set_role_denies_non_owner_actor(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    normalized = authz.normalize_library_path(library_path)
    _grant(app_db, users.owner, library_path, authz.ROLE_OWNER)
    _grant(app_db, users.viewer, library_path, authz.ROLE_VIEWER)

    # viewer tries to promote themselves — acl.set require_owner rejects.
    ctx = ActionContext(actor=users.viewer.id, library_path=normalized)
    body = SetLibraryRoleRequest(user=users.viewer.id, role=authz.ROLE_OWNER)

    with pytest.raises(HTTPException) as exc:
        set_library_member_role(body, _request(users.viewer), db, ctx, library_path)
    assert exc.value.status_code == 403


def test_revoke_removes_member_via_typed_endpoint(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    normalized = authz.normalize_library_path(library_path)
    _grant(app_db, users.owner, library_path, authz.ROLE_OWNER)
    _grant(app_db, users.viewer, library_path, authz.ROLE_VIEWER)

    ctx = ActionContext(actor=users.owner.id, library_path=normalized)
    resp = revoke_library_member_role(
        _request(users.owner), users.viewer.id, db, ctx, library_path
    )

    # Viewer is gone from the member list and their role row is deleted.
    assert users.viewer.id not in {m.user_id for m in resp.members}
    assert app_db.get_library_role(users.viewer.id, normalized) is None


def test_revoke_denies_non_owner_actor(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    normalized = authz.normalize_library_path(library_path)
    _grant(app_db, users.owner, library_path, authz.ROLE_OWNER)
    _grant(app_db, users.viewer, library_path, authz.ROLE_VIEWER)

    # viewer cannot revoke the owner (require_owner rejects) — owner keeps role.
    ctx = ActionContext(actor=users.viewer.id, library_path=normalized)
    with pytest.raises(HTTPException) as exc:
        revoke_library_member_role(
            _request(users.viewer), users.owner.id, db, ctx, library_path
        )
    assert exc.value.status_code == 403
    assert app_db.get_library_role(users.owner.id, normalized) is not None
