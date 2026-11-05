"""sharing.people.settings-screen (#2083): one read gives every person's access across every library.

Acceptance (the spec's): with libraries L1 and L2 and a person Maya, editor on L1 and no access on L2, the matrix says
exactly that, `GET /api/authz/libraries` as Maya lists L1 only, and only an owner may read the matrix.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.auth.authz import access_matrix, list_accessible_libraries
from fichero_server.db import Database
from fichero_server.models import KnownLibrary
from fichero_server.security import accounts, authz


@pytest.fixture
def people(app_db):
    def make(name, is_owner=False):
        return app_db.create_user(
            username=name, display_name=name.title(), password_hash=accounts.hash_password("pw"), is_owner=is_owner
        )

    return SimpleNamespace(owner=make("owner", True), maya=make("maya"), sam=make("sam"))


@pytest.fixture
def global_db(tmp_path):
    return Database(tmp_path / "global.fichero" / "fichero.duckdb")


def _request(user=None, *, bootstrap=False):
    return SimpleNamespace(state=SimpleNamespace(user=user, bootstrap_auth=bootstrap, device=None))


def _two_libraries(global_db, app_db, people):
    l1, l2 = KnownLibrary(path="/tmp/l1.fichero", name="L1"), KnownLibrary(path="/tmp/l2.fichero", name="L2")
    for lib in (l1, l2):
        global_db.save(lib)
    p1, p2 = (authz.normalize_library_path(x.path) for x in (l1, l2))
    app_db.set_library_role(user_id=people.maya.id, library_path=p1, role=authz.ROLE_EDITOR)
    app_db.set_library_role(user_id=people.sam.id, library_path=p2, role=authz.ROLE_VIEWER)
    return p1, p2


def test_the_matrix_says_each_persons_role_per_library_and_null_for_no_access(app_db, global_db, people, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    p1, p2 = _two_libraries(global_db, app_db, people)

    matrix = access_matrix(_request(people.owner), global_db)

    assert {lib.library_path for lib in matrix.libraries} == {p1, p2}
    cells = {p.username: {c.library_path: c.role for c in p.access} for p in matrix.people}
    assert cells["maya"] == {p1: "editor", p2: None}
    assert cells["sam"] == {p1: None, p2: "viewer"}


def test_mayas_own_library_list_agrees_with_the_matrix(app_db, global_db, people, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    p1, _ = _two_libraries(global_db, app_db, people)
    listed = list_accessible_libraries(_request(people.maya), global_db)
    assert [(lib.library_path, lib.role) for lib in listed.items] == [(p1, "editor")]


def test_only_an_owner_reads_the_matrix(app_db, global_db, people, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    _two_libraries(global_db, app_db, people)
    with pytest.raises(HTTPException) as refused:
        access_matrix(_request(people.maya), global_db)
    assert refused.value.status_code == 403
    assert access_matrix(_request(bootstrap=True), global_db).people
