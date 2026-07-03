"""#2869 hardening — the ACL snapshot must not leak the member roster.

`GET /api/authz/library` is loaded by every user (Share/Users settings, the
document inspector). It may tell you YOUR own role and access, but it must not
disclose WHO ELSE has access unless you can manage roles (owner). This pins
that the ``roles`` list stays empty for non-owners even when the library is
full of members, and that a stranger learns nothing about others.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero import accounts, authz
from fichero.api.routes.authz import get_library_authz_snapshot


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


def _request(user):
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
    # The snapshot route looks up roles by the raw header path; roles are stored
    # under the normalized path. A correct client sends the resolved path, so
    # pass the normalized form here to test the no-leak logic deterministically
    # (not the raw-vs-normalized quirk, which tmp_path symlinks could otherwise
    # make flaky).
    library_path = authz.normalize_library_path(str(db.path.parent))
    _grant(app_db, users.owner, library_path, authz.ROLE_OWNER)
    _grant(app_db, users.editor, library_path, authz.ROLE_EDITOR)
    _grant(app_db, users.viewer, library_path, authz.ROLE_VIEWER)
    return SimpleNamespace(library_path=library_path)


def test_owner_snapshot_lists_members(db, app_db, users, seeded):
    snap = get_library_authz_snapshot(_request(users.owner), seeded.library_path)
    assert snap.can_manage_roles is True
    assert snap.current_user_role == authz.ROLE_OWNER
    # Owner may see the roster.
    assert {r.user_id for r in snap.roles} == {users.owner.id, users.editor.id, users.viewer.id}


@pytest.mark.parametrize("who", ["editor", "viewer"])
def test_non_owner_snapshot_hides_roster_but_shows_own_role(db, app_db, users, seeded, who):
    actor = getattr(users, who)
    snap = get_library_authz_snapshot(_request(actor), seeded.library_path)
    assert snap.can_manage_roles is False
    # You learn YOUR own role and id...
    assert snap.current_user_role == who
    assert snap.current_user_id == actor.id
    # ...but NOT who else has access.
    assert snap.roles == []


def test_stranger_snapshot_leaks_nothing(db, app_db, users, seeded):
    snap = get_library_authz_snapshot(_request(users.stranger), seeded.library_path)
    assert snap.can_manage_roles is False
    assert snap.current_user_role is None
    assert snap.roles == []
    # No read/write either — fail-closed.
    assert snap.target_can_read is False
    assert snap.target_can_write is False


def test_unauthenticated_snapshot_leaks_nothing(db, app_db, users, seeded):
    snap = get_library_authz_snapshot(_request(None), seeded.library_path)
    assert snap.can_manage_roles is False
    assert snap.current_user_id is None
    assert snap.current_user_role is None
    assert snap.roles == []
    assert snap.target_can_read is False
    assert snap.target_can_write is False
