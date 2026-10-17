"""library-sharing: an owner account owns every library on that Mac (#5755; maintainer ruling 2026-10-17).

A person created (or promoted) as an owner gets the owner role on the libraries the host already has,
and a library opened later is owned by every owner account, so the same steps give the same result on
every engine.
"""

from __future__ import annotations

from fichero_server.security import accounts, authz

LIB = "/tmp/lib-5755"


def _make(app_db, name, owner=False):
    return app_db.create_user(
        username=name, display_name=name, password_hash=accounts.hash_password("pw"), is_owner=owner
    )


def test_a_new_owner_account_owns_the_existing_libraries(app_db):
    first = _make(app_db, "owner1", owner=True)
    app_db.set_library_role(user_id=first.id, library_path=LIB, role=authz.ROLE_OWNER)
    alice = _make(app_db, "alice", owner=True)
    assert app_db.get_library_role(alice.id, LIB).role == authz.ROLE_OWNER


def test_promoting_an_account_to_owner_grants_the_existing_libraries(app_db):
    first = _make(app_db, "owner1", owner=True)
    app_db.set_library_role(user_id=first.id, library_path=LIB, role=authz.ROLE_OWNER)
    bob = _make(app_db, "bob")
    assert app_db.get_library_role(bob.id, LIB) is None
    app_db.set_is_owner(bob.id, True)
    assert app_db.get_library_role(bob.id, LIB).role == authz.ROLE_OWNER


def test_a_non_owner_account_gets_nothing(app_db):
    first = _make(app_db, "owner1", owner=True)
    app_db.set_library_role(user_id=first.id, library_path=LIB, role=authz.ROLE_OWNER)
    carol = _make(app_db, "carol")
    assert app_db.get_library_role(carol.id, LIB) is None


def test_a_library_opened_later_is_owned_by_every_owner_account(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    a = _make(app_db, "owner1", owner=True)
    b = _make(app_db, "alice", owner=True)
    assert authz.ensure_owner_role(a, "/tmp/lib-5755-new")
    path = authz.normalize_library_path("/tmp/lib-5755-new")
    assert app_db.get_library_role(b.id, path).role == authz.ROLE_OWNER
