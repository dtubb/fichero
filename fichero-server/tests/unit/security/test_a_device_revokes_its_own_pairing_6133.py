"""`m2p.ios.forget-revokes-on-the-mac` (#6133): a paired device can revoke its own pairing with its own token, so the
Mac stops listing it and its token stops working; Forget This Mac on iOS calls it before clearing the device locally.

WHY: Forget This Mac only cleared the device's token, pin and host; the Mac kept listing the device as paired, and its
token stayed valid, until the owner removed it in Sharing.
"""
# ruff: noqa: F811  (fixtures imported from the adversarial suite are taken as parameters)
from __future__ import annotations

from tests.unit.security.test_pairing_auth_fork_adversarial import (  # noqa: F401  (fixtures and helpers)
    _bearer,
    _owner_session_token,
    clear_pairing_state,
    pairing_client,
)


def _pair(client, session_token, name="Owner iPad"):
    code = client.post("/api/pair/code", headers=_bearer(session_token)).json()["code"]
    paired = client.post("/api/pair", json={"code": code, "device_name": name})
    return paired.json()["device_id"], paired.json()["device_token"]


def test_a_device_revokes_itself_and_its_token_stops_working(pairing_client, app_db):
    session = _owner_session_token(pairing_client, app_db)
    device_id, token = _pair(pairing_client, session)
    assert pairing_client.get("/api/auth/me", headers=_bearer(token)).status_code == 200

    gone = pairing_client.post("/api/pair/devices/revoke-self", headers=_bearer(token))

    assert gone.status_code == 200 and gone.json() == {"status": "ok"}
    assert pairing_client.get("/api/auth/me", headers=_bearer(token)).status_code == 401
    assert app_db.get_device(device_id).revoked
    listed = pairing_client.get("/api/pair/devices", headers=_bearer(session)).json()["items"]
    assert [d for d in listed if d["id"] == device_id and not d.get("revoked")] == []
    audits = [a for a in app_db.list_action_audits() if a.action_name == "device.revoke_self"]
    assert len(audits) == 1 and audits[0].target_ids == [device_id]


def test_it_revokes_only_the_device_that_asked_and_never_another(pairing_client, app_db):
    session = _owner_session_token(pairing_client, app_db)
    mine, my_token = _pair(pairing_client, session, "Mine")
    other, other_token = _pair(pairing_client, session, "Other")

    assert pairing_client.post("/api/pair/devices/revoke-self", headers=_bearer(my_token)).status_code == 200

    assert app_db.get_device(mine).revoked
    assert not app_db.get_device(other).revoked
    assert pairing_client.get("/api/auth/me", headers=_bearer(other_token)).status_code == 200


def test_it_needs_a_device_token_and_a_revoked_one_cannot_revoke_again(pairing_client, app_db):
    session = _owner_session_token(pairing_client, app_db)
    assert pairing_client.post("/api/pair/devices/revoke-self").status_code == 401
    assert pairing_client.post("/api/pair/devices/revoke-self", headers=_bearer(session)).status_code == 401
    _, token = _pair(pairing_client, session)
    assert pairing_client.post("/api/pair/devices/revoke-self", headers=_bearer(token)).status_code == 200
    assert pairing_client.post("/api/pair/devices/revoke-self", headers=_bearer(token)).status_code == 401
