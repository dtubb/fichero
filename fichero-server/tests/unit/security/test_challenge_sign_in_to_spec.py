"""multiuser.sign-in-by-challenge (slice 1, #2403): a client proves it holds a person's key.

RED until slice 1 lands (specs/transport/multiuser-always-on.md). Additive: login, pairing and the bootstrap
token keep working; this only adds `clients`/`credentials` and the two routes. Written to run on the M4.

Contract the tests fix:
- `app_db.create_client(user_id, kind, name, host, public_key_pem)` -> object with `.id`, `.revoked_at`;
  `app_db.revoke_client(client_id)`; `app_db.get_client(client_id)`.
- `POST /api/auth/challenge {client_id}` -> 200 {nonce, expires_in}. Unknown or revoked client: 401, same body.
- `POST /api/auth/sign-in {client_id, nonce, signature}` (signature = base64 ECDSA-P256-SHA256 over the nonce
  bytes) -> 200 {session_token, user, client}. Anything else: 401 {"detail": "sign-in refused"}.
- The session carries the client: `sessions.client_id`; `GET /api/auth/identity` shows `client.id`.
"""

import base64
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _multiuser_on,
    harness,
)


def _new_key():
    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    return key, pem


def _sign(key, nonce: str) -> str:
    return base64.b64encode(key.sign(nonce.encode(), ec.ECDSA(hashes.SHA256()))).decode()


@pytest.fixture
def alice_client(harness, monkeypatch):
    users = _multiuser_on(harness, monkeypatch)
    key, pem = _new_key()
    client = harness.app_db.create_client(
        user_id=users["alice"].id, kind="device", name="Alice's iPhone", host="iPhone", public_key_pem=pem
    )
    return harness, users, key, client


def _challenge(harness, client_id):
    return harness.client().post("/api/auth/challenge", json={"client_id": client_id})


def _sign_in(harness, client_id, nonce, signature):
    return harness.client().post(
        "/api/auth/sign-in", json={"client_id": client_id, "nonce": nonce, "signature": signature}
    )


def test_a_client_row_round_trips_and_can_be_revoked(alice_client):
    harness, users, _key, client = alice_client
    stored = harness.app_db.get_client(client.id)
    assert stored.user_id == users["alice"].id
    assert (stored.kind, stored.name, stored.host) == ("device", "Alice's iPhone", "iPhone")
    assert stored.revoked_at is None
    harness.app_db.revoke_client(client.id)
    assert harness.app_db.get_client(client.id).revoked_at is not None


def test_the_right_key_signs_in_as_that_person_through_that_client(alice_client):
    harness, users, key, client = alice_client
    nonce = _challenge(harness, client.id).json()["nonce"]
    signed = _sign_in(harness, client.id, nonce, _sign(key, nonce))
    assert signed.status_code == 200, signed.text
    body = signed.json()
    assert body["user"]["username"] == "alice"
    assert body["client"]["id"] == client.id
    who = harness.client().get("/api/auth/identity", headers=_bearer(body["session_token"])).json()
    assert who["user"]["username"] == "alice"
    assert who["client"]["id"] == client.id


def test_a_nonce_is_single_use(alice_client):
    harness, _users, key, client = alice_client
    nonce = _challenge(harness, client.id).json()["nonce"]
    assert _sign_in(harness, client.id, nonce, _sign(key, nonce)).status_code == 200
    assert _sign_in(harness, client.id, nonce, _sign(key, nonce)).status_code == 401


def test_a_nonce_expires(alice_client, monkeypatch):
    harness, _users, key, client = alice_client
    issued = _challenge(harness, client.id).json()
    assert 0 < issued["expires_in"] <= 120
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + issued["expires_in"] + 5)
    late = _sign_in(harness, client.id, issued["nonce"], _sign(key, issued["nonce"]))
    assert late.status_code == 401


def test_a_signature_from_another_key_is_refused(alice_client):
    harness, _users, _key, client = alice_client
    nonce = _challenge(harness, client.id).json()["nonce"]
    other_key, _ = _new_key()
    refused = _sign_in(harness, client.id, nonce, _sign(other_key, nonce))
    assert refused.status_code == 401
    assert refused.json()["detail"] == "sign-in refused"


def test_a_nonce_made_for_one_client_does_not_work_for_another(alice_client):
    harness, users, key, client = alice_client
    other_key, other_pem = _new_key()
    other = harness.app_db.create_client(
        user_id=users["bob"].id, kind="device", name="Bob's Mac", host="Mac", public_key_pem=other_pem
    )
    nonce = _challenge(harness, client.id).json()["nonce"]
    # Bob's key signs a nonce that was issued to Alice's client.
    assert _sign_in(harness, other.id, nonce, _sign(other_key, nonce)).status_code == 401
    # And Alice's key cannot be presented as Bob's client.
    assert _sign_in(harness, other.id, nonce, _sign(key, nonce)).status_code == 401


def test_a_revoked_client_gets_no_challenge_and_no_session(alice_client):
    harness, _users, key, client = alice_client
    nonce = _challenge(harness, client.id).json()["nonce"]
    harness.app_db.revoke_client(client.id)
    assert _sign_in(harness, client.id, nonce, _sign(key, nonce)).status_code == 401
    assert _challenge(harness, client.id).status_code == 401


def test_an_unknown_client_looks_like_a_revoked_one(alice_client):
    harness, _users, _key, client = alice_client
    harness.app_db.revoke_client(client.id)
    revoked = _challenge(harness, client.id)
    unknown = _challenge(harness, "no-such-client")
    assert (revoked.status_code, revoked.json()) == (unknown.status_code, unknown.json())


def test_revoking_a_client_ends_its_sessions(alice_client):
    harness, _users, key, client = alice_client
    nonce = _challenge(harness, client.id).json()["nonce"]
    token = _sign_in(harness, client.id, nonce, _sign(key, nonce)).json()["session_token"]
    assert harness.client().get("/api/auth/me", headers=_bearer(token)).status_code == 200
    harness.app_db.revoke_client(client.id)
    assert harness.client().get("/api/auth/me", headers=_bearer(token)).status_code == 401


def test_repeated_bad_signatures_are_rate_limited(alice_client):
    harness, _users, _key, client = alice_client
    other_key, _ = _new_key()
    codes = []
    for _ in range(12):
        nonce = _challenge(harness, client.id).json().get("nonce", "x")
        codes.append(_sign_in(harness, client.id, nonce, _sign(other_key, nonce)).status_code)
    assert codes[0] == 401
    assert 429 in codes


def test_slice_one_removes_nothing_password_login_still_works(alice_client):
    harness, _users, _key, _client = alice_client
    logged_in = harness.client().post(
        "/api/auth/login", json={"username": "alice", "password": "pw-alice"}
    )
    assert logged_in.status_code == 200
