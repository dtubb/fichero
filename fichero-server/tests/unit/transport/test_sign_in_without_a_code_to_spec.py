"""sharing.people.sign-in-without-a-code (Step 8.9, #2083, #2403): with accounts on, a person reaches the host with only its
address, their username and their password. `POST /api/pair/sign-in` makes a device bound to that person and hands back its
token, as a code-bound pairing does; the pair code stays for a device with no person (accounts off).
"""

from fichero_server.api.routes.auth import pairing
from tests.unit.security import test_sharing_probe_2026_10_01 as probe

# The probe's fixtures, bound here so pytest finds them (the pairing state is cleared around every test).
harness = probe.harness
_clear_pairing_state = probe._clear_pairing_state
_multiuser_on = probe._multiuser_on


def _sign_in(harness, **body):
    return harness.remote().post("/api/pair/sign-in", json={"device_name": "Air", **body})


def test_a_person_signs_in_with_no_code_and_the_device_is_theirs(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    signed = _sign_in(harness, username="alice", password="pw-alice")
    assert signed.status_code == 200, signed.text
    device = harness.app_db.get_device(signed.json()["device_id"])
    assert device.user_id == users["alice"].id
    assert signed.json()["device_token"]


def test_the_token_reaches_only_that_persons_libraries(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    token = _sign_in(harness, username="alice", password="pw-alice").json()["device_token"]
    listed = harness.remote().get("/api/authz/libraries", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200, listed.text


def test_a_wrong_password_makes_no_device_and_counts_as_a_try(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    refused = _sign_in(harness, username="alice", password="nope")
    assert refused.status_code == 401
    assert refused.json()["detail"] == "invalid username or password"
    assert harness.app_db.list_devices() == []
    assert sum(len(v) for v in pairing._PAIRING_ATTEMPTS.values()) == 1


def test_an_unknown_person_reads_as_a_wrong_password(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    assert _sign_in(harness, username="nobody", password="x").json()["detail"] == "invalid username or password"


def test_a_disabled_person_is_refused(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    harness.app_db.set_active(users["alice"].id, False)
    assert _sign_in(harness, username="alice", password="pw-alice").status_code == 403


def test_with_accounts_off_signing_in_is_refused_and_the_code_stays(harness):
    refused = _sign_in(harness, username="alice", password="pw-alice")
    assert refused.status_code == 409
    assert "pairing link" in refused.json()["detail"]
