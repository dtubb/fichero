"""multiuser.person-bound-invite (#2403 slice 10, release bar #5910 item 6): a pairing code minted FOR a named person
binds the device that redeems it to that person, with no password and no way to become anyone else."""

from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _clear_pairing_state,
    _login,
    _multiuser_on,
    harness,
)


def _invite(harness, username, client=None):
    return (client or harness.host()).post("/api/pair/code", json={"username": username})


def _redeem(harness, code, **extra):
    return harness.remote().post("/api/pair", json={"code": code, "device_name": "Ann's Mac", **extra})


def test_a_code_for_a_named_person_binds_the_device_to_that_person_with_no_password(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    minted = _invite(harness, "alice")
    assert minted.status_code == 200, minted.text
    assert minted.json()["person"] == "alice"

    paired = _redeem(harness, minted.json()["code"])
    assert paired.status_code == 200, paired.text
    assert harness.app_db.get_device(paired.json()["device_id"]).user_id == users["alice"].id


def test_two_people_two_codes_each_device_is_its_own_person(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    ids = {}
    for name in ("alice", "bob"):
        ids[name] = _redeem(harness, _invite(harness, name).json()["code"]).json()["device_id"]
    assert harness.app_db.get_device(ids["alice"]).user_id == users["alice"].id
    assert harness.app_db.get_device(ids["bob"]).user_id == users["bob"].id


def test_redeeming_as_someone_else_is_refused_and_spends_nothing(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "alice").json()["code"]
    refused = _redeem(harness, code, username="bob", password="pw-bob")
    assert refused.status_code == 403
    assert "for another person" in refused.json()["detail"]
    assert harness.app_db.list_devices() == []
    assert _redeem(harness, code).status_code == 200, "the invitation is still good for the person it names"


def test_a_code_is_good_once(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "alice").json()["code"]
    assert _redeem(harness, code).status_code == 200
    assert _redeem(harness, code).status_code == 401


def test_only_the_host_or_an_owner_may_name_a_person(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    alice = harness.client()
    alice.headers.update(_bearer(_login(harness, "alice")))
    assert _invite(harness, "bob", client=alice).status_code == 403
    owner = harness.client()
    owner.headers.update(_bearer(_login(harness, "owner")))
    assert _invite(harness, "bob", client=owner).status_code == 200


def test_an_unknown_or_disabled_person_gets_no_code(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    assert _invite(harness, "nobody").status_code == 404
    harness.app_db.set_active(users["bob"].id, False)
    assert _invite(harness, "bob").status_code == 403


def test_naming_a_person_needs_multi_user_on(harness):
    assert _invite(harness, "alice").status_code == 422


def test_a_code_that_names_no_person_is_as_before(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    minted = harness.host().post("/api/pair/code")
    assert minted.json()["person"] is None
    assert _redeem(harness, minted.json()["code"]).status_code == 401, "person required, as sharing.device-chooses-person"
