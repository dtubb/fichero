"""signin.own.mac-writes-the-keychain-item / off-ends-enrolment-not-devices (#6568): the Mac's own app mints the
enrollment secret over its Unix socket; the engine keeps only a hash; turning it off or on again retires the old one
(a redeem is 401); devices already enrolled keep their tokens."""
from __future__ import annotations

from fichero_server.security import accounts
from tests.signed_in import mac_app_client, tcp_app_client
from tests.unit.security.test_sharing_probe_2026_10_01 import harness  # noqa: F401

# ruff: noqa: F811  -- pytest fixtures are passed by name

ROUTE = "/api/pair/own-devices"


def _owner(harness):
    return harness.app_db.create_user(
        username="owner", display_name="Owner", password_hash=accounts.hash_password("a chosen one"), is_owner=True
    )


def _redeem(harness, secret, name="Owner iPhone"):
    return mac_app_client(harness).post("/api/pair/enroll", json={"enrollment_secret": secret, "device_name": name})


def test_on_mints_a_32_byte_secret_stored_only_as_a_hash(harness):
    owner = _owner(harness)
    answer = mac_app_client(harness).put(ROUTE, json={"enabled": True})
    assert answer.status_code == 200, answer.text
    secret = answer.json()["enrollment_secret"]
    assert len(secret) >= 43  # 32 random bytes, url-safe base64
    stored = harness.app_db.get_enrollment_secret_by_token_hash(accounts.hash_token(secret))
    assert stored is not None and stored.user_id == owner.id and stored.token_hash != secret
    redeemed = _redeem(harness, secret)
    assert redeemed.status_code == 200, redeemed.text


def test_off_then_a_redeem_of_the_old_secret_is_401_and_enrolled_devices_stay(harness):
    _owner(harness)
    secret = mac_app_client(harness).put(ROUTE, json={"enabled": True}).json()["enrollment_secret"]
    device = _redeem(harness, secret).json()
    off = mac_app_client(harness).put(ROUTE, json={"enabled": False})
    assert off.status_code == 200 and off.json() == {"enabled": False, "enrollment_secret": None}
    assert _redeem(harness, secret).status_code == 401
    assert harness.app_db.get_device(device["device_id"]) is not None


def test_on_again_mints_a_new_secret_and_retires_the_old(harness):
    _owner(harness)
    first = mac_app_client(harness).put(ROUTE, json={"enabled": True}).json()["enrollment_secret"]
    second = mac_app_client(harness).put(ROUTE, json={"enabled": True}).json()["enrollment_secret"]
    assert first != second
    assert _redeem(harness, first).status_code == 401
    assert _redeem(harness, second).status_code == 200


def test_only_the_macs_own_app_over_the_socket_may(harness):
    _owner(harness)
    assert tcp_app_client(harness).put(ROUTE, json={"enabled": True}).status_code == 403
