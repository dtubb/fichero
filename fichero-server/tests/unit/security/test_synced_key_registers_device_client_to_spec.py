"""multiuser.second-device-by-synced-key / remote-flow-no-pairing-code (#2403): a device holding the person's synced key
signs in by challenge with no password and no code; the engine registers it as its own `device` client."""
from __future__ import annotations


from tests.signed_in import new_key, signature_for
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401

# ruff: noqa: F811  -- pytest fixtures are passed by name


def _setup(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    key, pem = new_key()
    first = harness.app_db.create_client(user_id=users["alice"].id, kind="app", name="Alice's Mac", public_key_pem=pem)
    return harness, users, key, pem, first


def _sign_in(harness, key, pem, name="Alice's iPhone"):
    issued = harness.client().post("/api/auth/key-challenge", json={"public_key_pem": pem})
    assert issued.status_code == 200, issued.text
    holder_id = harness.app_db.live_clients_by_public_key(pem)[0].id
    signature = signature_for(key, holder_id, issued.json())
    return harness.client().post(
        "/api/auth/sign-in-by-key",
        json={"public_key_pem": pem, "nonce": issued.json()["nonce"], "signature": signature,
              "client": {"name": name, "host": "iPhone"}},
    )


def test_a_new_device_with_the_synced_key_signs_in_and_gets_its_own_client(harness, monkeypatch):
    harness, users, key, pem, first = _setup(harness, monkeypatch)
    answer = _sign_in(harness, key, pem)
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["user"]["id"] == users["alice"].id
    assert body["client"]["name"] == "Alice's iPhone" and body["client"]["id"] != first.id
    me = harness.client().get("/api/auth/identity", headers={"Authorization": f"Bearer {body['session_token']}"})
    assert me.json()["client"]["id"] == body["client"]["id"]


def test_the_same_device_again_reuses_its_client_and_another_device_gets_another(harness, monkeypatch):
    harness, _users, key, pem, _first = _setup(harness, monkeypatch)
    one = _sign_in(harness, key, pem).json()["client"]["id"]
    assert _sign_in(harness, key, pem).json()["client"]["id"] == one
    assert _sign_in(harness, key, pem, name="Alice's iPad").json()["client"]["id"] != one


def test_revoking_the_device_client_ends_its_session(harness, monkeypatch):
    harness, _users, key, pem, _first = _setup(harness, monkeypatch)
    body = _sign_in(harness, key, pem).json()
    harness.app_db.revoke_client(body["client"]["id"])
    me = harness.client().get("/api/auth/identity", headers={"Authorization": f"Bearer {body['session_token']}"})
    assert me.status_code == 401


def test_a_key_nobody_holds_and_a_wrong_signature_are_refused(harness, monkeypatch):
    harness, _users, key, pem, _first = _setup(harness, monkeypatch)
    other_key, other_pem = new_key()
    assert harness.client().post("/api/auth/key-challenge", json={"public_key_pem": other_pem}).status_code == 401
    issued = harness.client().post("/api/auth/key-challenge", json={"public_key_pem": pem}).json()
    forged = signature_for(other_key, harness.app_db.live_clients_by_public_key(pem)[0].id, issued)
    refused = harness.client().post(
        "/api/auth/sign-in-by-key",
        json={"public_key_pem": pem, "nonce": issued["nonce"], "signature": forged, "client": {"name": "Thief"}},
    )
    assert refused.status_code == 401
    assert [c.name for c in harness.app_db.live_clients_by_public_key(pem)] == ["Alice's Mac"]
