"""#2869 hardening — role-escalation attempts through the members routes.

`test_authz_management_adversarial.py` pins the authz *functions*; this pins the
*route + action* choke points the UI hits: a non-owner must not be able to
grant, change, or revoke roles — not even to escalate themselves — and the
actor is taken from the request context, never the body, so it cannot be
forged. Bad input fails loudly (422) rather than silently granting.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import fichero.api.routes.actions_registry  # noqa: F401 - registers acl.set
from fichero.security import accounts
from fichero.security import authz
from fichero.actions.registry import ActionContext
from fichero.api.routes.authz import (
    list_library_members,
    revoke_library_member_role,
    set_library_member_role,
)
from fichero.models import AccountUser, SetLibraryRoleRequest


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
        editor=mk("editor", "Editor"),
        viewer=mk("viewer", "Viewer"),
        stranger=mk("stranger", "Stranger"),
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


def test_editor_cannot_grant_themselves_owner(db, app_db, users, seeded):
    ctx = ActionContext(actor=users.editor.id, library_path=seeded.normalized)
    body = SetLibraryRoleRequest(user=users.editor.id, role=authz.ROLE_OWNER)

    with pytest.raises(HTTPException) as exc:
        set_library_member_role(body, _request(users.editor), db, ctx, seeded.library_path)
    assert exc.value.status_code == 403
    # Role unchanged — still editor, not owner.
    assert app_db.get_library_role(users.editor.id, seeded.normalized).role == authz.ROLE_EDITOR


def test_viewer_cannot_change_another_users_role(db, app_db, users, seeded):
    ctx = ActionContext(actor=users.viewer.id, library_path=seeded.normalized)
    body = SetLibraryRoleRequest(user=users.editor.id, role=authz.ROLE_VIEWER)

    with pytest.raises(HTTPException) as exc:
        set_library_member_role(body, _request(users.viewer), db, ctx, seeded.library_path)
    assert exc.value.status_code == 403
    assert app_db.get_library_role(users.editor.id, seeded.normalized).role == authz.ROLE_EDITOR


def test_editor_cannot_revoke_the_owner(db, app_db, users, seeded):
    ctx = ActionContext(actor=users.editor.id, library_path=seeded.normalized)
    with pytest.raises(HTTPException) as exc:
        revoke_library_member_role(
            _request(users.editor), users.owner.id, db, ctx, seeded.library_path
        )
    assert exc.value.status_code == 403
    assert app_db.get_library_role(users.owner.id, seeded.normalized) is not None


def test_actor_is_from_context_not_body(db, app_db, users, seeded):
    # The attacker (viewer) puts the OWNER's id in the request as `user`, hoping
    # the handler trusts the body for authority. It doesn't — authority is
    # ctx.actor (the viewer), so require_owner still rejects.
    ctx = ActionContext(actor=users.viewer.id, library_path=seeded.normalized)
    body = SetLibraryRoleRequest(user=users.stranger.id, role=authz.ROLE_OWNER)

    with pytest.raises(HTTPException) as exc:
        set_library_member_role(body, _request(users.viewer), db, ctx, seeded.library_path)
    assert exc.value.status_code == 403
    # Stranger gained nothing.
    assert app_db.get_library_role(users.stranger.id, seeded.normalized) is None


def test_invalid_role_is_rejected_not_granted(db, app_db, users, seeded):
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.normalized)
    body = SetLibraryRoleRequest(user=users.stranger.id, role="superadmin")

    with pytest.raises(HTTPException) as exc:
        set_library_member_role(body, _request(users.owner), db, ctx, seeded.library_path)
    assert exc.value.status_code == 422
    # No bogus role landed.
    assert app_db.get_library_role(users.stranger.id, seeded.normalized) is None


def test_unknown_target_user_fails_loudly(db, app_db, users, seeded):
    ctx = ActionContext(actor=users.owner.id, library_path=seeded.normalized)
    body = SetLibraryRoleRequest(user="does-not-exist", role=authz.ROLE_EDITOR)

    with pytest.raises(HTTPException) as exc:
        set_library_member_role(body, _request(users.owner), db, ctx, seeded.library_path)
    assert exc.value.status_code == 422


def test_non_owner_cannot_list_members_no_leak(db, app_db, users, seeded):
    # A non-owner must not learn who else has access.
    for attacker in (users.editor, users.viewer, users.stranger):
        with pytest.raises(HTTPException) as exc:
            list_library_members(_request(attacker), seeded.library_path)
        assert exc.value.status_code == 403
