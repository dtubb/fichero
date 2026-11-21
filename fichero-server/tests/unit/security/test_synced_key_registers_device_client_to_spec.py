"""multiuser.second-device-by-synced-key / remote-flow-no-pairing-code (#2403): a device holding the person's synced key
signs in by challenge with no password and no code; the engine registers it as its own `device` client. The signature
covers the key (its hash), never a client id, so a device with no client here signs from what the challenge returns."""
from __future__ import annotations

import hashlib

from tests.signed_in import new_key, signature_for
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401

# ruff: noqa: F811  -- pytest fixtures are passed by name


def _setup(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    key, pem = new_key()
    first = harness.app_db.create_client(user_id=users["alice"].id, kind="app", name="Alice's Mac", public_key_pem=pem)
    return harness, users, key, pem, first


def _body(key, pem, issued, name="Alice's iPhone", **overrides):
    """Everything is read from the challenge's answer and the device's own key: no database read."""
    signature = signature_for(
        key, hashlib.sha256(pem.encode()).hexdigest(), issued, purpose="fichero-key-sign-in-v1", **overrides
    )
    return {"public_key_pem": pem, "nonce": issued["nonce"], "signature": signature, "client": {"name": name, "host": "iPhone"}}


def _sign_in(harness, key, pem, name="Alice's iPhone"):
    issued = harness.client().post("/api/auth/key-challenge", json={"public_key_pem": pem})
    assert issued.status_code == 200, issued.text
    assert set(issued.json()) == {"nonce", "expires_in", "expires_at", "engine_id"}  # no client id is revealed
    return harness.client().post("/api/auth/sign-in-by-key", json=_body(key, pem, issued.json(), name))


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


def test_revoking_the_device_client_ends_its_session_and_it_cannot_sign_back_in(harness, monkeypatch):
    harness, _users, key, pem, _first = _setup(harness, monkeypatch)
    body = _sign_in(harness, key, pem).json()
    harness.app_db.revoke_client(body["client"]["id"])
    me = harness.client().get("/api/auth/identity", headers={"Authorization": f"Bearer {body['session_token']}"})
    assert me.status_code == 401
    assert _sign_in_status(harness, key, pem) == 401
    assert [c.name for c in harness.app_db.live_clients_by_public_key(pem)] == ["Alice's Mac"]


def _sign_in_status(harness, key, pem):
    issued = harness.client().post("/api/auth/key-challenge", json={"public_key_pem": pem}).json()
    return harness.client().post("/api/auth/sign-in-by-key", json=_body(key, pem, issued)).status_code


def test_a_key_nobody_holds_looks_the_same_as_one_somebody_holds_and_is_refused(harness, monkeypatch):
    harness, _users, key, pem, _first = _setup(harness, monkeypatch)
    other_key, other_pem = new_key()
    assert harness.client().post("/api/auth/key-challenge", json={"public_key_pem": other_pem}).status_code == 200
    assert _sign_in_status(harness, other_key, other_pem) == 401
    assert [c.name for c in harness.app_db.live_clients_by_public_key(other_pem)] == []


def test_a_wrong_signature_or_a_replayed_nonce_is_refused(harness, monkeypatch):
    harness, _users, key, pem, _first = _setup(harness, monkeypatch)
    other_key, _ = new_key()
    issued = harness.client().post("/api/auth/key-challenge", json={"public_key_pem": pem}).json()
    forged = _body(other_key, pem, issued, name="Thief")
    assert harness.client().post("/api/auth/sign-in-by-key", json=forged).status_code == 401
    good = _body(key, pem, issued)  # the nonce was spent by the failed try
    assert harness.client().post("/api/auth/sign-in-by-key", json=good).status_code == 401
    assert [c.name for c in harness.app_db.live_clients_by_public_key(pem)] == ["Alice's Mac"]


def test_failed_key_sign_ins_do_not_lock_the_macs_own_client_out(harness, monkeypatch):
    harness, _users, key, pem, first = _setup(harness, monkeypatch)
    other_key, _ = new_key()
    for _ in range(12):
        issued = harness.client().post("/api/auth/key-challenge", json={"public_key_pem": pem}).json()
        harness.client().post("/api/auth/sign-in-by-key", json=_body(other_key, pem, issued))
    issued = harness.client().post("/api/auth/challenge", json={"client_id": first.id}).json()
    signed = harness.client().post(
        "/api/auth/sign-in",
        json={"client_id": first.id, "nonce": issued["nonce"], "signature": signature_for(key, first.id, issued)},
    )
    assert signed.status_code == 200, signed.text


def test_failures_for_keys_nobody_holds_are_not_remembered(harness, monkeypatch):
    # The key routes are reachable over TCP: keys nobody holds must not grow engine memory, as sign-in does for ids.
    from fichero_server.api.routes.auth import accounts as routes

    harness, _users, _key, _pem, _first = _setup(harness, monkeypatch)
    before = dict(routes._key_sign_in_failures)
    for _ in range(5):
        other_key, other_pem = new_key()
        assert _sign_in_status(harness, other_key, other_pem) == 401
    assert routes._key_sign_in_failures == before
