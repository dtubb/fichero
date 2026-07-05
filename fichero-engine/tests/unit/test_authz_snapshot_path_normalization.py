"""#2869 fix — ACL snapshot normalizes the library path before role lookups.

Regression: roles are stored under the normalized library path, but the
snapshot route used the raw ``X-Fichero-Library-Path`` header for
``get_library_role`` / ``list_library_roles`` while ``can_read``/``can_write``
normalized internally. An owner whose client sent an un-normalized path (a
trailing slash, or a /var → /private/var symlink) was shown
``can_manage_roles=False`` and an empty roster while ``target_can_write`` stayed
True — the Users & Sharing pane would refuse to let the real owner manage.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero import accounts, authz
from fichero.api.routes.authz import get_library_authz_snapshot


@pytest.fixture
def owner(app_db):
    return app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("pw"),
        is_owner=True,
    )


def _request(user):
    return SimpleNamespace(state=SimpleNamespace(user=user))


def test_unnormalized_header_still_resolves_owner_role(db, app_db, owner, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    normalized = authz.normalize_library_path(str(db.path.parent))
    app_db.set_library_role(user_id=owner.id, library_path=normalized, role=authz.ROLE_OWNER)

    # Client sends a trailing-slash (un-normalized) path — normalize() collapses
    # it to the stored key, so the owner is still recognized.
    unnormalized = normalized + "/"
    snap = get_library_authz_snapshot(_request(owner), unnormalized)

    assert snap.auth_kind == "unknown"
    assert snap.current_user_role == authz.ROLE_OWNER
    assert snap.can_manage_roles is True
    assert {r.user_id for r in snap.roles} == {owner.id}
    # Manage-rights and data-write agree (the inconsistency the bug caused).
    assert snap.can_manage_roles == snap.target_can_write
    # Response echoes the normalized path.
    assert snap.library_path == normalized
