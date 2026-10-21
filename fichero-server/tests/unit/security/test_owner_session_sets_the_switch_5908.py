"""multiuser.owner-session-sets-the-switch (#5908): while Multi-user is off the owner's own key session may choose the owner's
password and set the switch; the start-up key and another person's session may not. Through the real middleware."""
from __future__ import annotations

from fichero_server.security import accounts, authz
from tests.signed_in import signed_in_client
from tests.unit.security.test_sharing_probe_2026_10_01 import harness  # noqa: F401


def _people(harness, monkeypatch):
    monkeypatch.delenv("FICHERO_MULTIUSER", raising=False)  # the persisted setting decides
    db = harness.app_db
    owner = db.create_user(username="owner", display_name="Owner", password_hash=accounts.hash_password("random-" * 5), is_owner=True)
    ann = db.create_user(username="ann", display_name="Ann", password_hash=accounts.hash_password("x"), is_owner=False)
    # a library's owner holds its owner role (`authz` registers it); the action layer's owner check reads that role
    db.set_library_role(user_id=owner.id, library_path=authz.normalize_library_path(harness.library), role=authz.ROLE_OWNER)
    return owner, ann


def test_the_owners_key_session_chooses_the_password_then_turns_multiuser_on(harness, monkeypatch):
    owner, _ann = _people(harness, monkeypatch)
    who = signed_in_client(harness, owner)
    client = harness.client()
    assert client.put("/api/pair/multiuser", json={"enabled": True}, headers=who.headers).status_code == 409, "no password chosen yet"
    chosen = client.patch(f"/api/users/{owner.id}", json={"password": "a chosen one"}, headers=who.headers)
    assert chosen.status_code == 200, chosen.text
    on = client.put("/api/pair/multiuser", json={"enabled": True}, headers=who.headers)
    assert on.status_code == 200, on.text
    assert harness.app_db.get_setting("multiuser.enabled") == "true"


def test_the_start_up_key_is_refused_for_both_steps(harness, monkeypatch):
    owner, _ann = _people(harness, monkeypatch)
    app = harness.host()  # loopback plus the bootstrap token
    password = app.patch(f"/api/users/{owner.id}", json={"password": "p"})
    assert (password.status_code, password.json()["detail"]) == (404, "multi-user auth is disabled"), "the guard's own refusal, not a routing 404"
    switch = app.put("/api/pair/multiuser", json={"enabled": True})
    assert (switch.status_code, switch.json()["detail"]) == (403, "sign in as the owner to change Multi-user")
    assert harness.app_db.get_setting("multiuser.enabled") != "true"


def test_another_persons_session_is_refused_for_both_steps(harness, monkeypatch):
    owner, ann = _people(harness, monkeypatch)
    theirs = signed_in_client(harness, ann)
    client = harness.client()
    for refused in (client.patch(f"/api/users/{owner.id}", json={"password": "p"}, headers=theirs.headers),
                    client.put("/api/pair/multiuser", json={"enabled": True}, headers=theirs.headers)):
        assert (refused.status_code, refused.json()["detail"]) == (401, "missing or invalid Authorization header")
    assert harness.app_db.get_setting("multiuser.enabled") != "true"


def test_the_allowlist_is_exactly_the_two_calls():
    from fichero_server.api.auth import _owner_session_route_while_off as allowed

    assert allowed("PATCH", "/api/users/abc") and allowed("PUT", "/api/pair/multiuser")
    for method, path in (("GET", "/api/users/abc"), ("DELETE", "/api/users/abc"), ("PATCH", "/api/users"), ("PATCH", "/api/users/abc/x"),
                         ("PATCH", "/api/auth/users/abc"), ("POST", "/api/pair/multiuser"), ("PUT", "/api/pair/multiuser/x")):
        assert not allowed(method, path), (method, path)


def test_the_owners_session_is_not_honoured_elsewhere_while_off(harness, monkeypatch):
    owner, _ann = _people(harness, monkeypatch)
    who = signed_in_client(harness, owner)
    assert harness.client().get("/api/pair/devices", headers=who.headers).status_code == 401, "only the two steps, nothing else"


def test_choosing_the_password_ends_the_owners_other_sessions_but_not_the_one_that_chose_it(harness, monkeypatch):
    owner, _ann = _people(harness, monkeypatch)
    mine = signed_in_client(harness, owner, name="this one")
    other = signed_in_client(harness, owner, name="another device")
    client = harness.client()
    assert client.patch(f"/api/users/{owner.id}", json={"password": "a chosen one"}, headers=mine.headers).status_code == 200
    assert client.put("/api/pair/multiuser", json={"enabled": True}, headers=mine.headers).status_code == 200, "the same session carries on"
    assert client.put("/api/pair/multiuser", json={"enabled": False}, headers=other.headers).status_code == 401, "the other one ended"


def test_an_owner_setting_another_owners_password_ends_all_of_that_persons_sessions(harness, monkeypatch):
    owner, _ann = _people(harness, monkeypatch)
    bo = harness.app_db.create_user(username="bo", display_name="Bo", password_hash=accounts.hash_password("x" * 8), is_owner=True)
    mine = signed_in_client(harness, owner)
    theirs = signed_in_client(harness, bo)
    client = harness.client()
    assert client.patch(f"/api/users/{bo.id}", json={"password": "set for them"}, headers=mine.headers).status_code == 200
    assert client.put("/api/pair/multiuser", json={"enabled": False}, headers=theirs.headers).status_code == 401, "their session ended"
    assert client.put("/api/pair/multiuser", json={"enabled": False}, headers=mine.headers).status_code != 401, "the admin's own stays"
