from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import fichero_server.api.routes.actions_registry  # noqa: F401
from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.actions.registry import ActionContext
from fichero_server.api.routes.actions_registry import undo_action
from fichero_server.api.routes.auth.authz import (
    set_library_member_role,
    share_library_object,
)
from fichero_server.models import ActionAudit, AccountUser, SetLibraryRoleRequest, ShareRequest


def _request(user: AccountUser | None, base_url="https://engine.local:8765/"):
    return SimpleNamespace(state=SimpleNamespace(user=user), base_url=base_url)


def _grant(app_db, user, library_path, role):
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


def _undo(db, audit_id: str, actor: str, library_path: str):
    return asyncio.run(
        undo_action(
            audit_id,
            _request(None),
            db=db,
            ctx=ActionContext(actor=actor, library_path=library_path),
            x_fichero_library_path=library_path,
            x_fichero_origin_window=None,
        )
    )


@pytest.fixture
def users(app_db):
    def mk(username, display, owner=False):
        return app_db.create_user(
            username=username,
            display_name=display,
            password_hash=accounts.hash_password("pw"),
            is_owner=owner,
        )

    return SimpleNamespace(
        owner=mk("owner", "Owner", owner=True),
        alice=mk("alice", "Alice"),
        viewer=mk("viewer", "Viewer"),
    )


@pytest.fixture
def seeded(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    normalized = authz.normalize_library_path(library_path)
    _grant(app_db, users.owner, library_path, authz.ROLE_OWNER)
    return SimpleNamespace(library_path=library_path, normalized=normalized)


def test_share_route_undo_revokes_granted_access(db, app_db, users, seeded, monkeypatch):
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.library_path)

    share_library_object(
        ShareRequest(user=users.alice.id, role="viewer", object_type="library"),
        _request(users.owner),
        db,
        ctx,
        seeded.library_path,
    )

    forward = db.all(ActionAudit)[-1]
    assert forward.action_name == "acl.set"
    assert forward.before == {"user_id": users.alice.id, "role": None}
    assert app_db.get_library_role(users.alice.id, seeded.normalized).role == "viewer"

    inverse = _undo(db, forward.id, users.owner.id, seeded.library_path)

    assert app_db.get_library_role(users.alice.id, seeded.normalized) is None
    inverse_audit = db.get(ActionAudit, inverse.audit_id)
    assert inverse_audit is not None
    assert inverse_audit.action_name == "acl.set"
    assert inverse_audit.inverse_of == forward.id
    assert calls[-1][1]["type"] == "authz.changed"


def test_member_role_change_undo_restores_previous_role(
    db, app_db, users, seeded, monkeypatch
):
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    _grant(app_db, users.viewer, seeded.library_path, authz.ROLE_VIEWER)
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.library_path)

    set_library_member_role(
        SetLibraryRoleRequest(user=users.viewer.id, role=authz.ROLE_EDITOR),
        _request(users.owner),
        db,
        ctx,
        seeded.library_path,
    )

    forward = db.all(ActionAudit)[-1]
    assert forward.action_name == "acl.set"
    assert forward.before == {"user_id": users.viewer.id, "role": authz.ROLE_VIEWER}
    assert app_db.get_library_role(users.viewer.id, seeded.normalized).role == "editor"

    inverse = _undo(db, forward.id, users.owner.id, seeded.library_path)

    assert app_db.get_library_role(users.viewer.id, seeded.normalized).role == "viewer"
    inverse_audit = db.get(ActionAudit, inverse.audit_id)
    assert inverse_audit is not None
    assert inverse_audit.action_name == "acl.set"
    assert inverse_audit.inverse_of == forward.id
    assert calls[-1][1]["type"] == "authz.changed"
