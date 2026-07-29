"""#2869 hardening — concurrent grant/revoke must not corrupt the ACL.

`AppDatabase` serializes writes under ``self._lock`` and ``library_roles`` has a
unique (user_id, library_path) constraint (the ON CONFLICT upsert target). These
stress tests pin that concurrent role writes can't produce duplicate rows, lost
grants, or a crash — the failure modes that would silently break per-library
access under real multi-user load.
"""

from __future__ import annotations

import threading


from fichero_server.security import accounts
from fichero_server.security import authz


def _mk(app_db, username):
    return app_db.create_user(
        username=username,
        display_name=username.title(),
        password_hash=accounts.hash_password("pw"),
    )


def _roles_for(app_db, library_path, user_id):
    return [r for r in app_db.list_library_roles(library_path) if r.user_id == user_id]


def _run_concurrently(fns):
    barrier = threading.Barrier(len(fns))
    errors: list[BaseException] = []

    def wrap(fn):
        def inner():
            try:
                barrier.wait()
                fn()
            except BaseException as exc:  # noqa: BLE001 - surface any thread error
                errors.append(exc)
        return inner

    threads = [threading.Thread(target=wrap(fn)) for fn in fns]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return errors


def test_concurrent_grants_for_distinct_users_all_land(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library = authz.normalize_library_path("/tmp/fichero-conc-lib-a")
    members = [_mk(app_db, f"user{i}") for i in range(20)]

    def grant(user):
        return lambda: app_db.set_library_role(
            user_id=user.id, library_path=library, role=authz.ROLE_EDITOR
        )

    errors = _run_concurrently([grant(u) for u in members])
    assert not errors, errors
    # Every distinct user landed exactly one editor row.
    for user in members:
        rows = _roles_for(app_db, library, user.id)
        assert len(rows) == 1 and rows[0].role == authz.ROLE_EDITOR


def test_concurrent_upsert_same_user_leaves_exactly_one_row(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library = authz.normalize_library_path("/tmp/fichero-conc-lib-b")
    user = _mk(app_db, "contended")
    roles = [authz.ROLE_EDITOR, authz.ROLE_VIEWER]

    def upsert(i):
        return lambda: app_db.set_library_role(
            user_id=user.id, library_path=library, role=roles[i % 2]
        )

    errors = _run_concurrently([upsert(i) for i in range(30)])
    assert not errors, errors
    # The unique constraint + lock guarantee a single row with one valid role.
    rows = _roles_for(app_db, library, user.id)
    assert len(rows) == 1
    assert rows[0].role in roles


def test_concurrent_grant_and_revoke_ends_consistent(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    library = authz.normalize_library_path("/tmp/fichero-conc-lib-c")
    user = _mk(app_db, "flapping")

    def grant():
        for _ in range(25):
            app_db.set_library_role(
                user_id=user.id, library_path=library, role=authz.ROLE_EDITOR
            )

    def revoke():
        for _ in range(25):
            app_db.delete_library_role(user.id, library)

    errors = _run_concurrently([grant, revoke])
    assert not errors, errors
    # Whichever wins last, the state is valid: at most one row, and if present a
    # real role — never a duplicate or a corrupt value.
    rows = _roles_for(app_db, library, user.id)
    assert len(rows) <= 1
    if rows:
        assert rows[0].role in authz.VALID_ROLES
