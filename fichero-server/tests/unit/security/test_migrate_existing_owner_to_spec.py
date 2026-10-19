"""multiuser.migrate-owner (slice 5, #2403): a library that already has an owner row gets its first key, once.

Spec: docs/contributor_manual/specs/transport/multiuser-always-on.md. `POST /api/auth/migrate-owner` registers a key
for the OWNER row only, only while the owner has no key, only over the Unix socket, only with the launch secret (the
old bootstrap token is refused). First-run is the path for a library with no owner.

Built in slice 5.
"""

import pytest

from fichero_server.security import accounts
from tests.signed_in import new_key, signature_for, uds_client
from tests.unit.security.test_sharing_probe_2026_10_01 import harness  # noqa: F401

SECRET = "cd" * 32


@pytest.fixture
def engine_secret():
    from fichero_server.security import launch_secret

    launch_secret.set_secret(SECRET)
    yield SECRET
    launch_secret.set_secret(None)


def _users(harness):
    owner = harness.app_db.create_user(
        username="owner", display_name="Owner", password_hash=accounts.hash_password("x"), is_owner=True
    )
    alice = harness.app_db.create_user(
        username="alice", display_name="Alice", password_hash=accounts.hash_password("x"), is_owner=False
    )
    return owner, alice


def _migrate(http, pem, *, secret=SECRET, headers=None):
    sent = {"X-Fichero-Launch-Secret": secret} if secret else {}
    sent.update(headers or {})
    return http.post(
        "/api/auth/migrate-owner",
        json={"public_key_pem": pem, "client": {"kind": "app", "name": "Fichero", "host": "MacBook Pro"}},
        headers=sent,
    )


def test_the_owner_row_gets_its_first_key_and_signs_in_by_it(harness, engine_secret):
    owner, _alice = _users(harness)
    key, pem = new_key()
    done = _migrate(uds_client(harness), pem)
    assert done.status_code == 200, done.text
    client_id = done.json()["client"]["id"]
    assert harness.app_db.get_client(client_id).user_id == owner.id
    http = harness.client()
    issued = http.post("/api/auth/challenge", json={"client_id": client_id}).json()
    signed = http.post(
        "/api/auth/sign-in",
        json={"client_id": client_id, "nonce": issued["nonce"], "signature": signature_for(key, client_id, issued)},
    )
    assert signed.status_code == 200 and signed.json()["user"]["id"] == owner.id


def test_it_works_once_then_409(harness, engine_secret):
    _users(harness)
    _key, pem = new_key()
    assert _migrate(uds_client(harness), pem).status_code == 200
    _key2, pem2 = new_key()
    assert _migrate(uds_client(harness), pem2).status_code == 409


def test_without_an_owner_row_it_is_refused(harness, engine_secret):
    _key, pem = new_key()
    assert _migrate(uds_client(harness), pem).status_code == 404


def test_it_is_refused_over_tcp_and_without_the_secret(harness, engine_secret):
    _users(harness)
    _key, pem = new_key()
    assert _migrate(harness.client(), pem).status_code == 403
    assert _migrate(uds_client(harness), pem, secret="ef" * 32).status_code == 401
    assert _migrate(uds_client(harness), pem, secret=None).status_code == 401


def test_the_bootstrap_token_is_not_the_launch_secret(harness, engine_secret):
    _users(harness)
    _key, pem = new_key()
    as_bearer = _migrate(uds_client(harness), pem, secret=None, headers={"Authorization": "Bearer " + harness.bootstrap})
    assert as_bearer.status_code == 401


def test_the_key_goes_to_the_owner_never_to_another_person(harness, engine_secret):
    owner, alice = _users(harness)
    _key, pem = new_key()
    client_id = _migrate(uds_client(harness), pem).json()["client"]["id"]
    assert harness.app_db.get_client(client_id).user_id == owner.id != alice.id


def test_several_owner_rows_are_refused_not_guessed(harness, engine_secret):
    _users(harness)
    harness.app_db.create_user(
        username="second", display_name="Second", password_hash=accounts.hash_password("x"), is_owner=True
    )
    _key, pem = new_key()
    assert _migrate(uds_client(harness), pem).status_code == 409
