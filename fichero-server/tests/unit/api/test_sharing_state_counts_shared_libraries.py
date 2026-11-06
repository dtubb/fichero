"""sharing.host.asks-which-projects-when-nothing-is-shared (#6366): the engine counts the projects someone can open, so the
app asks "Which projects do you want to share?" only when the answer is none. With accounts: the projects a person other
than the owner holds a role on. With no accounts: once a device is paired, this Mac's known projects. Each project once.
"""

from fichero_server.api.routes.auth.pairing import _shared_library_count
from fichero_server.security import accounts


def _person(app_db, name, owner=False):
    return app_db.create_user(username=name, display_name=name.title(), password_hash=accounts.hash_password("pw"),
                              is_owner=owner)


def test_no_grants_is_zero(app_db):
    _person(app_db, "owner", owner=True)
    assert _shared_library_count(app_db, multiuser=True) == 0


def test_one_person_role_on_one_of_two_libraries_is_one(app_db):
    owner = _person(app_db, "owner", owner=True)
    maya = _person(app_db, "maya")
    app_db.set_library_role(user_id=owner.id, library_path="/L1", role="owner")
    app_db.set_library_role(user_id=owner.id, library_path="/L2", role="owner")
    app_db.set_library_role(user_id=maya.id, library_path="/L1", role="editor")
    assert _shared_library_count(app_db, multiuser=True) == 1


def test_a_library_given_twice_counts_once(app_db):
    _person(app_db, "owner", owner=True)
    for name in ("maya", "sam"):
        app_db.set_library_role(user_id=_person(app_db, name).id, library_path="/L1", role="viewer")
    assert _shared_library_count(app_db, multiuser=True) == 1


def test_with_no_accounts_nothing_counts_until_a_device_is_paired(app_db, monkeypatch):
    from types import SimpleNamespace

    from fichero_server.api.routes.library import registry

    known = [SimpleNamespace(path="/A"), SimpleNamespace(path="/B")]
    monkeypatch.setattr(registry, "get_global_database", lambda: SimpleNamespace(query=lambda _model: known))
    owner = _person(app_db, "owner", owner=True)
    assert _shared_library_count(app_db, multiuser=False) == 0
    app_db.create_device(name="Air", user_id=owner.id, token_hash=accounts.hash_token("t"))
    assert _shared_library_count(app_db, multiuser=False) == 2
