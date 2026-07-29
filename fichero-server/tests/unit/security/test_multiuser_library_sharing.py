"""#2868 — per-library access isolation for multi-user shared libraries.

The core sharing property: a role in ONE library grants nothing in another.
`test_authz_acl.py` already covers single-library role enforcement, grant, and
revoke; this module pins the cross-library isolation that "share some libraries
but not others" depends on — a role/grant must never leak sideways, and a
stranger must be denied everywhere (403 / fail-closed, no data).

Exercised at the `authz.can_read` / `can_write` choke point (the same functions
the read/write dependencies call), with FICHERO_MULTIUSER=1 and seeded
accounts + roles — the fixture pattern from test_authz_acl.py.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.security import accounts
from fichero_server.security import authz


@pytest.fixture
def users(app_db):
    owner = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("pw"),
        is_owner=True,
    )
    member = app_db.create_user(
        username="member",
        display_name="Member",
        password_hash=accounts.hash_password("pw"),
    )
    stranger = app_db.create_user(
        username="stranger",
        display_name="Stranger",
        password_hash=accounts.hash_password("pw"),
    )
    return SimpleNamespace(owner=owner, member=member, stranger=stranger)


@pytest.fixture
def libraries(tmp_path):
    a = tmp_path / "libA"
    b = tmp_path / "libB"
    c = tmp_path / "libC"
    for path in (a, b, c):
        path.mkdir()
    return SimpleNamespace(a=str(a), b=str(b), c=str(c))


def _grant(app_db, user, library_path, role):
    app_db.set_library_role(
        user_id=user.id,
        library_path=authz.normalize_library_path(library_path),
        role=role,
    )


def test_role_in_one_library_does_not_grant_another(app_db, users, libraries, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    # Owner of A, nothing in B.
    _grant(app_db, users.member, libraries.a, authz.ROLE_OWNER)

    assert authz.can_read(users.member, libraries.a) is True
    assert authz.can_write(users.member, libraries.a) is True
    # No role in B ⇒ fail-closed, no sideways leak.
    assert authz.can_read(users.member, libraries.b) is False
    assert authz.can_write(users.member, libraries.b) is False


def test_sharing_is_per_library(app_db, users, libraries, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    # Shared A as editor, B as viewer, C not at all.
    _grant(app_db, users.member, libraries.a, authz.ROLE_EDITOR)
    _grant(app_db, users.member, libraries.b, authz.ROLE_VIEWER)

    # A: read + write (editor).
    assert authz.can_read(users.member, libraries.a) is True
    assert authz.can_write(users.member, libraries.a) is True
    # B: read only (viewer) — write denied.
    assert authz.can_read(users.member, libraries.b) is True
    assert authz.can_write(users.member, libraries.b) is False
    # C: not shared — both denied.
    assert authz.can_read(users.member, libraries.c) is False
    assert authz.can_write(users.member, libraries.c) is False


def test_stranger_denied_every_library_no_leak(app_db, users, libraries, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    # Someone else owns A and B; the stranger has no role anywhere.
    _grant(app_db, users.owner, libraries.a, authz.ROLE_OWNER)
    _grant(app_db, users.owner, libraries.b, authz.ROLE_OWNER)

    for library in (libraries.a, libraries.b, libraries.c):
        assert authz.can_read(users.stranger, library) is False
        assert authz.can_write(users.stranger, library) is False

    # assert_can_read raises (the 403 seam) rather than leaking.
    with pytest.raises(authz.AuthorizationError):
        authz.assert_can_read(users.stranger, libraries.a)


def test_role_change_takes_effect_per_library(app_db, users, libraries, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    _grant(app_db, users.member, libraries.a, authz.ROLE_VIEWER)
    assert authz.can_write(users.member, libraries.a) is False

    # Upgrade viewer → editor: write becomes allowed, and only in A.
    _grant(app_db, users.member, libraries.a, authz.ROLE_EDITOR)
    assert authz.can_write(users.member, libraries.a) is True
    assert authz.can_write(users.member, libraries.b) is False

    # Revoke: both read and write fall back to denied (fail-closed).
    app_db.delete_library_role(users.member.id, authz.normalize_library_path(libraries.a))
    assert authz.can_read(users.member, libraries.a) is False
    assert authz.can_write(users.member, libraries.a) is False


def test_unauthenticated_request_is_denied_not_blank(app_db, users, libraries, monkeypatch):
    """Blank-window regression (#2868): the app connecting to a backend where it
    has NO session (e.g. a stranger engine it didn't launch) must be DENIED, not
    silently served empty data. With no resolvable user, the choke point
    fail-closes — the app surfaces a 403/401, never a blank window.
    """
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    _grant(app_db, users.owner, libraries.a, authz.ROLE_OWNER)

    # No session user at all (request.state.user is None).
    assert authz.can_read(None, libraries.a) is False
    assert authz.can_write(None, libraries.a) is False
    with pytest.raises(authz.AuthorizationError):
        authz.assert_can_read(None, libraries.a)
