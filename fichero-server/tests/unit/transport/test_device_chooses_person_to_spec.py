"""sharing.device-chooses-person (#2403): a paired device chooses and authenticates a person.

`POST /api/pair` takes an optional username + password (Multi-user on): the device is then bound to that
person, not to whoever minted the code, so the host's owner is never ambient on a remote device.
"""

from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _clear_pairing_state,
    _multiuser_on,
    harness,
)


def _pair(harness, **credentials):
    code = harness.host().post("/api/pair/code").json()["code"]
    return harness.remote().post("/api/pair", json={"code": code, "device_name": "B", **credentials})


def test_the_device_is_bound_to_the_person_who_signed_in_not_the_code_minter(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    paired = _pair(harness, username="alice", password="pw-alice")
    assert paired.status_code == 200, paired.text
    assert harness.app_db.get_device(paired.json()["device_id"]).user_id == users["alice"].id


def test_a_wrong_password_pairs_nothing(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    refused = _pair(harness, username="alice", password="nope")
    assert refused.status_code == 401
    assert harness.app_db.list_devices() == []


def test_choosing_a_person_needs_multi_user_on(harness):
    assert _pair(harness, username="alice", password="x").status_code == 409


def test_multi_user_on_a_pairing_that_names_no_person_is_asked_who_it_is(harness, monkeypatch):
    # S8: the Mac drawer reveals username/password on exactly this answer.
    _multiuser_on(harness, monkeypatch)
    refused = _pair(harness)
    assert refused.status_code == 401
    assert refused.json()["detail"] == "person required: this library uses Multi-user, sign in as a person"
    assert harness.app_db.list_devices() == []
