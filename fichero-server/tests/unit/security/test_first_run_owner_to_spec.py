"""multiuser.first-launch-creates-owner-and-key (slice 4, #2403): `POST /api/auth/first-run` makes the owner once.

Spec: docs/contributor_manual/specs/transport/multiuser-always-on.md. The route works only while the library has no
owner, only over the Unix socket, and only with the launch secret (`X-Fichero-Launch-Secret`), never the old bearer
token. It registers the person's public key as the app client; the app then signs in by challenge like any client.

Slice 4 of the plan: the held strict xfails of the red commit are gone now the route is built.
"""

import pytest

from fichero_server.security import accounts
from tests.signed_in import new_key, signature_for, uds_client
from tests.unit.security.test_sharing_probe_2026_10_01 import harness  # noqa: F401

SECRET = "ab" * 32


@pytest.fixture
def engine_secret():
    from fichero_server.security import launch_secret

    launch_secret.set_secret(SECRET)
    yield SECRET
    launch_secret.set_secret(None)


def _first_run(http, pem, *, secret=SECRET, headers=None):
    sent = {"X-Fichero-Launch-Secret": secret} if secret else {}
    sent.update(headers or {})
    return http.post(
        "/api/auth/first-run",
        json={"display_name": "Daniel Tubb", "client": {"kind": "app", "name": "Fichero", "host": "MacBook Pro"}, "public_key_pem": pem},
        headers=sent,
    )


def test_first_run_works_once_then_409(harness, engine_secret):
    _key, pem = new_key()
    first = _first_run(uds_client(harness), pem)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["user"]["is_owner"] is True and body["user"]["display_name"] == "Daniel Tubb"
    assert body["client"]["kind"] == "app"
    _key2, pem2 = new_key()
    assert _first_run(uds_client(harness), pem2).status_code == 409


def test_the_new_owner_signs_in_by_challenge(harness, engine_secret):
    key, pem = new_key()
    client_id = _first_run(uds_client(harness), pem).json()["client"]["id"]
    http = harness.client()
    issued = http.post("/api/auth/challenge", json={"client_id": client_id}).json()
    signed = http.post(
        "/api/auth/sign-in",
        json={"client_id": client_id, "nonce": issued["nonce"], "signature": signature_for(key, client_id, issued)},
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["user"]["is_owner"] is True


def test_first_run_is_refused_over_tcp_even_with_the_secret(harness, engine_secret):
    _key, pem = new_key()
    refused = _first_run(harness.client(), pem)
    assert refused.status_code == 403
    assert not [u for u in harness.app_db.list_users() if u.is_owner]


def test_first_run_needs_the_launch_secret(harness, engine_secret):
    _key, pem = new_key()
    for wrong in (None, "", "cd" * 32, SECRET[:-2]):
        assert _first_run(uds_client(harness), pem, secret=wrong).status_code == 401
    assert not [u for u in harness.app_db.list_users() if u.is_owner]


def test_the_bootstrap_token_is_not_the_launch_secret(harness, engine_secret):
    _key, pem = new_key()
    as_header = _first_run(uds_client(harness), pem, secret=harness.bootstrap)
    as_bearer = _first_run(uds_client(harness), pem, secret=None, headers={"Authorization": "Bearer " + harness.bootstrap})
    assert (as_header.status_code, as_bearer.status_code) == (401, 401)


def test_an_engine_without_a_launch_secret_refuses_first_run(harness):
    from fichero_server.security import launch_secret

    launch_secret.set_secret(None)
    _key, pem = new_key()
    assert _first_run(uds_client(harness), pem).status_code == 401


def test_first_run_is_409_when_an_owner_already_exists(harness, engine_secret):
    harness.app_db.create_user(
        username="owner", display_name="Owner", password_hash=accounts.hash_password("x"), is_owner=True
    )
    _key, pem = new_key()
    assert _first_run(uds_client(harness), pem).status_code == 409


def test_a_non_owner_already_called_owner_gives_409_not_500(harness, engine_secret):
    harness.app_db.create_user(
        username="owner", display_name="Not the owner", password_hash=accounts.hash_password("x"), is_owner=False
    )
    _key, pem = new_key()
    assert _first_run(uds_client(harness), pem).status_code == 409
