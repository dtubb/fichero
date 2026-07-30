"""#2869 hardening — revoke edge cases (grant/revoke lifecycle corners).

Pins the corners of role revocation: idempotency, immediate loss of access,
re-grant after revoke, isolation (revoking one member leaves others), the
self-revoke guard, and the two-owner rule that keeps a library from ever
losing its last owner.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import fichero_server.api.routes.actions_registry  # noqa: F401 - registers acl.set
from fichero_server.security import accounts
from fichero_server.security import authz
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.auth.authz import revoke_library_member_role
from fichero_server.models import AccountUser


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
        owner2=mk("owner2", "Owner Two", owner=True),
        editor=mk("editor", "Editor"),
        viewer=mk("viewer", "Viewer"),
    )


def _request(user: AccountUser | None):
    return SimpleNamespace(state=SimpleNamespace(user=user))


def _grant(app_db, user, library_path, role):
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


@pytest.fixture
def seeded(db, app_db, users, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library_path = str(db.path.parent)
    normalized = authz.normalize_library_path(library_path)
    _grant(app_db, users.owner, library_path, authz.ROLE_OWNER)
    _grant(app_db, users.editor, library_path, authz.ROLE_EDITOR)
    _grant(app_db, users.viewer, library_path, authz.ROLE_VIEWER)
    return SimpleNamespace(library_path=library_path, normalized=normalized)


def _revoke(db, app_db, actor, target, seeded):
    ctx = ActionContext(actor=actor.id, library_path=seeded.normalized)
    return revoke_library_member_role(_request(actor), target.id, db, ctx, seeded.library_path)


def test_revoke_then_access_is_denied_immediately(db, app_db, users, seeded):
    assert authz.can_write(users.editor, seeded.library_path) is True
    _revoke(db, app_db, users.owner, users.editor, seeded)
    assert authz.can_read(users.editor, seeded.library_path) is False
    assert authz.can_write(users.editor, seeded.library_path) is False


def test_double_revoke_is_idempotent(db, app_db, users, seeded):
    _revoke(db, app_db, users.owner, users.viewer, seeded)
    # Second revoke of an already-role-less user must not raise.
    resp = _revoke(db, app_db, users.owner, users.viewer, seeded)
    assert users.viewer.id not in {m.user_id for m in resp.members}
    assert app_db.get_library_role(users.viewer.id, seeded.normalized) is None


def test_revoke_never_granted_user_is_noop(db, app_db, users, seeded):
    # owner2 has an account but no role in this library — revoking is a no-op.
    resp = _revoke(db, app_db, users.owner, users.owner2, seeded)
    assert app_db.get_library_role(users.owner2.id, seeded.normalized) is None
    # Existing members are untouched.
    assert {users.owner.id, users.editor.id, users.viewer.id} <= {m.user_id for m in resp.members}


def test_revoke_then_regrant_restores_access(db, app_db, users, seeded):
    _revoke(db, app_db, users.owner, users.editor, seeded)
    assert authz.can_write(users.editor, seeded.library_path) is False

    ctx = ActionContext(actor=users.owner.id, library_path=seeded.normalized)
    registry.invoke(
        db, "acl.set", {"user": users.editor.id, "role": authz.ROLE_EDITOR}, ctx
    )
    assert authz.can_write(users.editor, seeded.library_path) is True


def test_revoke_isolates_to_target(db, app_db, users, seeded):
    _revoke(db, app_db, users.owner, users.editor, seeded)
    # Only the editor lost their role; viewer and owner keep theirs.
    assert app_db.get_library_role(users.editor.id, seeded.normalized) is None
    assert app_db.get_library_role(users.viewer.id, seeded.normalized).role == authz.ROLE_VIEWER
    assert app_db.get_library_role(users.owner.id, seeded.normalized).role == authz.ROLE_OWNER


def test_sole_owner_cannot_revoke_themselves(db, app_db, users, seeded):
    with pytest.raises(HTTPException) as exc:
        _revoke(db, app_db, users.owner, users.owner, seeded)
    assert exc.value.status_code == 403
    assert app_db.get_library_role(users.owner.id, seeded.normalized) is not None


def test_second_owner_can_remove_the_first(db, app_db, users, seeded):
    # Promote owner2 to owner, then owner2 revokes owner — allowed, and the
    # library still has an owner (owner2). No last-owner lockout.
    _grant(app_db, users.owner2, seeded.library_path, authz.ROLE_OWNER)

    _revoke(db, app_db, users.owner2, users.owner, seeded)

    assert app_db.get_library_role(users.owner.id, seeded.normalized) is None
    assert app_db.get_library_role(users.owner2.id, seeded.normalized).role == authz.ROLE_OWNER
