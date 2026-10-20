"""multiuser.person-bound-invite (#2403 slice 10, release bar #5910 item 6): a pairing code minted FOR a named person
binds the device that redeems it to that person, with no password and no way to become anyone else."""

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.auth import pairing
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _clear_pairing_state,
    _login,
    _multiuser_on,
    harness,
)


class _FakeRequest:
    """The ambient start-up key: bootstrap auth, no signed-in person. Called directly, not over HTTP, so no test line
    acts as the ambient owner (the ratchet)."""

    class state:
        bootstrap_auth = True


def _as(harness, username):
    client = harness.client()
    client.headers.update(_bearer(_login(harness, username)))
    return client


def _invite(harness, username, client=None):
    """Minted by the owner SIGNED IN, never the ambient host (the ambient-owner ratchet must not grow)."""
    return (client or _as(harness, "owner")).post("/api/pair/code", json={"username": username})


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


def test_only_a_signed_in_owner_may_name_a_person(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    assert _invite(harness, "bob", client=_as(harness, "alice")).status_code == 403
    ambient = _FakeRequest()  # the start-up key (loopback + bootstrap), no person signed in
    with pytest.raises(HTTPException) as refused:
        pairing._invited_person(ambient, harness.app_db, "bob")
    assert refused.value.status_code == 403 and "signed-in owner" in refused.value.detail
    assert _invite(harness, "bob", client=_as(harness, "owner")).status_code == 200


def test_an_unknown_or_disabled_person_gets_no_code(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    assert _invite(harness, "nobody").status_code == 404
    harness.app_db.set_active(users["bob"].id, False)
    assert _invite(harness, "bob").status_code == 403


def test_naming_a_person_needs_multi_user_on(harness):
    """The mint is authenticated, so it may say why; the redeem never does (see the next test)."""
    with pytest.raises(HTTPException) as refused:
        pairing._invited_person(_FakeRequest(), harness.app_db, "alice")
    assert refused.value.status_code == 422


def test_a_code_that_names_no_person_is_as_before(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    minted = _as(harness, "owner").post("/api/pair/code")
    assert minted.json()["person"] is None
    assert _redeem(harness, minted.json()["code"]).status_code == 401, "person required, as sharing.device-chooses-person"


def test_the_redeem_is_audited_with_the_person_the_minter_and_the_device(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    paired = _redeem(harness, _invite(harness, "alice").json()["code"]).json()
    rows = [r for r in harness.app_db.list_action_audits() if r.action_name == "device.pair_for_person"]
    assert len(rows) == 1
    assert rows[0].target_ids == [paired["device_id"]]
    assert rows[0].params["person"] == "alice" and rows[0].params["minted_by"] == "owner"
    assert rows[0].actor == "invite:owner"


def test_the_bound_device_has_that_persons_role_never_the_owners(harness, monkeypatch):
    """bob is a viewer (reads, cannot write); alice is an editor (writes). Neither is the owner."""
    users = _multiuser_on(harness, monkeypatch)
    for name, may_write in (("bob", False), ("alice", True)):
        paired = _redeem(harness, _invite(harness, name).json()["code"]).json()
        device = harness.app_db.get_device(paired["device_id"])
        assert device.user_id == users[name].id
        assert harness.app_db.get_user(device.user_id).is_owner is False
        wrote = harness.remote().post("/api/notes", json={"body": f"{name} writes"},
                                      headers=_bearer(paired["device_token"]))
        assert (wrote.status_code < 300) is may_write, f"{name}: {wrote.status_code} {wrote.text}"


def test_a_redeem_after_multi_user_was_turned_off_is_refused_like_a_bad_code_and_spends_nothing(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    code = _invite(harness, "alice").json()["code"]
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    refused = _redeem(harness, code)
    assert refused.status_code == 401 and refused.json()["detail"] == "invalid or expired pairing code"
    assert harness.app_db.list_devices() == []
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    assert _redeem(harness, code).status_code == 200, "nothing was spent"
