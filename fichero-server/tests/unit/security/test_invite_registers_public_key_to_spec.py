"""multiuser.invite-registers-public-key (slice 8a, #2403): accepting an invite can register the person's key.

`POST /api/auth/invites/redeem` takes a password (as before) OR `public_key_pem` + `client`. With a key the person has
no usable password; a client row holds the key and they sign in by challenge. Nothing existing changes.
"""

import pytest

from tests.signed_in import new_key, signature_for
from tests.unit.security.test_sharing_probe_2026_10_01 import (  # noqa: F401
    _bearer,
    _login,
    _multiuser_on,
    harness,
)


@pytest.fixture(autouse=True)
def _fresh_redeem_rate_limit():
    # Redemption is rate limited per address; every test here redeems from the same one.
    from fichero_server.api.routes.auth import accounts as routes

    routes._INVITE_REDEEM_ATTEMPTS_BY_IP.clear()
    yield
    routes._INVITE_REDEEM_ATTEMPTS_BY_IP.clear()


def _invite(harness, username="ann"):
    token = _login(harness, "owner")
    r = harness.client().post(
        "/api/auth/invites", headers=_bearer(token), json={"username": username, "display_name": username.title()}
    )
    assert r.status_code == 200, r.text
    return r.json()["invite_token"]


def _redeem(harness, invite, **body):
    return harness.client().post("/api/auth/invites/redeem", json={"invite_token": invite, **body})


def test_a_key_redeems_an_invite_and_signs_in_by_challenge(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    key, pem = new_key()
    redeemed = _redeem(harness, _invite(harness), public_key_pem=pem, client={"kind": "app", "name": "Ann's Mac"})
    assert redeemed.status_code == 200, redeemed.text
    body = redeemed.json()
    assert body["user"]["username"] == "ann" and body["client"]["name"] == "Ann's Mac"
    issued = harness.client().post("/api/auth/challenge", json={"client_id": body["client"]["id"]}).json()
    signed = harness.client().post(
        "/api/auth/sign-in",
        json={
            "client_id": body["client"]["id"],
            "nonce": issued["nonce"],
            "signature": signature_for(key, body["client"]["id"], issued),
        },
    )
    assert signed.status_code == 200 and signed.json()["user"]["username"] == "ann"


def test_a_key_redemption_sets_no_usable_password(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    _key, pem = new_key()
    assert _redeem(harness, _invite(harness), public_key_pem=pem, client={"kind": "app", "name": "m"}).status_code == 200
    for guess in ("", "password", "ann"):
        assert harness.client().post("/api/auth/login", json={"username": "ann", "password": guess}).status_code in (401, 422)


def test_a_password_still_redeems_as_before(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    redeemed = _redeem(harness, _invite(harness), new_password="correct horse battery staple")
    assert redeemed.status_code == 200 and redeemed.json()["client"] is None
    assert harness.client().post(
        "/api/auth/login", json={"username": "ann", "password": "correct horse battery staple"}
    ).status_code == 200


def test_neither_password_nor_key_is_refused_and_keeps_the_invite(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    invite = _invite(harness)
    assert _redeem(harness, invite).status_code == 422
    assert _redeem(harness, invite, new_password="long enough password").status_code == 200


def test_a_key_that_is_not_p256_is_refused(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    invite = _invite(harness)
    bad = _redeem(harness, invite, public_key_pem="not a key", client={"kind": "app", "name": "m"})
    assert bad.status_code == 422
    assert _redeem(harness, invite, new_password="long enough password").status_code == 200


def test_a_key_without_a_client_is_refused(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    _key, pem = new_key()
    assert _redeem(harness, _invite(harness), public_key_pem=pem).status_code == 422


def test_the_redeem_session_is_the_new_client_s(harness, monkeypatch):
    _multiuser_on(harness, monkeypatch)
    _key, pem = new_key()
    body = _redeem(harness, _invite(harness), public_key_pem=pem, client={"kind": "app", "name": "Ann's Mac"}).json()
    who = harness.client().get("/api/auth/identity", headers=_bearer(body["session_token"])).json()
    assert who["client"]["id"] == body["client"]["id"]
