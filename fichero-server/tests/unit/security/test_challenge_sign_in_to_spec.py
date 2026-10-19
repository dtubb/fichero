"""multiuser.sign-in-by-challenge (slice 1, #2403): a client proves it holds a person's key.

Slice 1 of docs/contributor_manual/specs/transport/multiuser-always-on.md. Additive: login, pairing and the bootstrap
token keep working; this only adds `clients`/`credentials` and the two routes. Written to run on the M4.

Contract the tests fix:
- `app_db.create_client(user_id, kind, name, host, public_key_pem)` -> object with `.id`, `.revoked_at`;
  `app_db.revoke_client(client_id)`; `app_db.get_client(client_id)`.
- `POST /api/auth/challenge {client_id}` -> 200 {nonce, expires_in, expires_at, engine_id}. Unknown or revoked
  client: 401, same body.
- `POST /api/auth/sign-in {client_id, nonce, signature}`: the signature (base64 ECDSA-P256-SHA256) is over the
  domain-separated message `"fichero-sign-in-v1" 0x00 engine_id 0x00 client_id 0x00 nonce 0x00 expires_at`, never
  the bare nonce (review 98: cross-engine relay). -> 200 {session_token, user, client}. Else 401 {"detail": "sign-in refused"}.
- The session carries the client: `sessions.client_id`; `GET /api/auth/identity` shows `client.id`.
"""

import base64
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tests.signed_in import new_key, signature_for
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _multiuser_on,
    harness,
)


def _new_key():
    return new_key()


def _sign(key, client_id: str, issued: dict, **overrides) -> str:
    return signature_for(key, client_id, issued, **overrides)


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


def _issue(harness, client_id) -> dict:
    return _challenge(harness, client_id).json()


def _sign_in(harness, client_id, issued, signature):
    return harness.client().post(
        "/api/auth/sign-in", json={"client_id": client_id, "nonce": issued["nonce"], "signature": signature}
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
    harness, _users, key, client = alice_client
    issued = _issue(harness, client.id)
    signed = _sign_in(harness, client.id, issued, _sign(key, client.id, issued))
    assert signed.status_code == 200, signed.text
    body = signed.json()
    assert body["user"]["username"] == "alice"
    assert body["client"]["id"] == client.id
    who = harness.client().get("/api/auth/identity", headers=_bearer(body["session_token"])).json()
    assert who["user"]["username"] == "alice"
    assert who["client"]["id"] == client.id


def test_a_nonce_is_single_use(alice_client):
    harness, _users, key, client = alice_client
    issued = _issue(harness, client.id)
    assert _sign_in(harness, client.id, issued, _sign(key, client.id, issued)).status_code == 200
    assert _sign_in(harness, client.id, issued, _sign(key, client.id, issued)).status_code == 401


def test_a_nonce_expires(alice_client, monkeypatch):
    harness, _users, key, client = alice_client
    issued = _issue(harness, client.id)
    assert 0 < issued["expires_in"] <= 120
    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + issued["expires_in"] + 5)
    late = _sign_in(harness, client.id, issued, _sign(key, client.id, issued))
    assert late.status_code == 401


def test_a_signature_from_another_key_is_refused(alice_client):
    harness, _users, _key, client = alice_client
    issued = _issue(harness, client.id)
    other_key, _ = _new_key()
    refused = _sign_in(harness, client.id, issued, _sign(other_key, client.id, issued))
    assert refused.status_code == 401
    assert refused.json()["detail"] == "sign-in refused"


def test_the_bare_nonce_is_not_what_is_signed(alice_client):
    # Review 98: signing only the nonce is the relay hole; it must not verify.
    harness, _users, key, client = alice_client
    issued = _issue(harness, client.id)
    bare = base64.b64encode(key.sign(issued["nonce"].encode(), ec.ECDSA(hashes.SHA256()))).decode()
    assert _sign_in(harness, client.id, issued, bare).status_code == 401


def test_a_signature_made_for_another_engine_is_refused(alice_client):
    # The same synced key is registered on every engine a person belongs to; a host that relays
    # engine A's nonce to her client must not get a signature that engine B accepts, and vice versa.
    harness, _users, key, client = alice_client
    issued = _issue(harness, client.id)
    assert issued["engine_id"]
    relayed = _sign(key, client.id, issued, engine_id="some-other-engine")
    assert _sign_in(harness, client.id, issued, relayed).status_code == 401


def test_a_signature_over_a_different_expiry_is_refused(alice_client):
    harness, _users, key, client = alice_client
    issued = _issue(harness, client.id)
    longer = _sign(key, client.id, issued, expires_at=int(issued["expires_at"]) + 3600)
    assert _sign_in(harness, client.id, issued, longer).status_code == 401


def test_a_signature_for_another_purpose_is_refused(alice_client):
    # A reset signature (or any other purpose) can never be replayed as a sign-in.
    harness, _users, key, client = alice_client
    issued = _issue(harness, client.id)
    reset = _sign(key, client.id, issued, purpose="fichero-reset-v1")
    assert _sign_in(harness, client.id, issued, reset).status_code == 401


def test_a_nonce_made_for_one_client_does_not_work_for_another(alice_client):
    harness, users, key, client = alice_client
    other_key, other_pem = _new_key()
    other = harness.app_db.create_client(
        user_id=users["bob"].id, kind="device", name="Bob's Mac", host="Mac", public_key_pem=other_pem
    )
    issued = _issue(harness, client.id)
    # Bob's key signs a nonce that was issued to Alice's client.
    assert _sign_in(harness, other.id, issued, _sign(other_key, other.id, issued)).status_code == 401
    # And Alice's key cannot be presented as Bob's client.
    assert _sign_in(harness, other.id, issued, _sign(key, other.id, issued)).status_code == 401


def test_a_revoked_client_gets_no_challenge_and_no_session(alice_client):
    harness, _users, key, client = alice_client
    issued = _issue(harness, client.id)
    harness.app_db.revoke_client(client.id)
    assert _sign_in(harness, client.id, issued, _sign(key, client.id, issued)).status_code == 401
    assert _challenge(harness, client.id).status_code == 401


def test_an_unknown_client_looks_like_a_revoked_one(alice_client):
    harness, _users, _key, client = alice_client
    harness.app_db.revoke_client(client.id)
    revoked = _challenge(harness, client.id)
    unknown = _challenge(harness, "no-such-client")
    assert (revoked.status_code, revoked.json()) == (unknown.status_code, unknown.json())


def test_revoking_a_client_ends_its_sessions(alice_client):
    harness, _users, key, client = alice_client
    issued = _issue(harness, client.id)
    token = _sign_in(harness, client.id, issued, _sign(key, client.id, issued)).json()["session_token"]
    assert harness.client().get("/api/auth/me", headers=_bearer(token)).status_code == 200
    harness.app_db.revoke_client(client.id)
    assert harness.client().get("/api/auth/me", headers=_bearer(token)).status_code == 401


def test_repeated_bad_signatures_are_rate_limited(alice_client):
    harness, _users, _key, client = alice_client
    other_key, _ = _new_key()
    codes = []
    for _ in range(12):
        issued = _issue(harness, client.id)
        if "nonce" not in issued:  # already refused at the challenge
            codes.append(429)
            continue
        codes.append(_sign_in(harness, client.id, issued, _sign(other_key, client.id, issued)).status_code)
    assert codes[0] == 401
    assert 429 in codes


def test_slice_one_removes_nothing_password_login_still_works(alice_client):
    harness, _users, _key, _client = alice_client
    logged_in = harness.client().post("/api/auth/login", json={"username": "alice", "password": "pw-alice"})
    assert logged_in.status_code == 200


def test_failures_for_unknown_clients_are_not_remembered(alice_client):
    # Review 101: sign-in is reachable over TCP, so ids nobody registered must not grow engine memory.
    from fichero_server.api.routes.auth import accounts as routes

    harness, _users, _key, _client = alice_client
    before = dict(routes._sign_in_failures)
    for i in range(5):
        harness.client().post(
            "/api/auth/sign-in", json={"client_id": f"nobody-{i}", "nonce": "x", "signature": "eA=="}
        )
    assert routes._sign_in_failures == before


def test_only_a_few_challenges_stay_outstanding_per_client(alice_client):
    harness, _users, key, client = alice_client
    first = _issue(harness, client.id)
    for _ in range(8):
        _issue(harness, client.id)
    # The oldest nonce was dropped, so even a correct signature over it is refused.
    assert _sign_in(harness, client.id, first, _sign(key, client.id, first)).status_code == 401
