"""signin.own.ios-finds-it-and-connects (#6568): a fresh iPhone holds no token, so `POST /api/pair/enroll` must be
reachable without one. Each redeem of the synced secret makes ONE device row, named by the device, and its own token."""
from __future__ import annotations

from fichero_server.security import accounts
from tests.signed_in import mac_app_client
from tests.unit.security.test_sharing_probe_2026_10_01 import harness  # noqa: F401

# ruff: noqa: F811  -- pytest fixtures are passed by name


def _secret(harness):
    harness.app_db.create_user(
        username="owner", display_name="Owner", password_hash=accounts.hash_password("a chosen one"), is_owner=True
    )
    return mac_app_client(harness).put("/api/pair/own-devices", json={"enabled": True}).json()["enrollment_secret"]


def test_a_device_with_no_token_redeems_the_secret(harness):
    secret = _secret(harness)
    answer = harness.remote().post("/api/pair/enroll", json={"enrollment_secret": secret, "device_name": "Daniel's iPhone"})
    assert answer.status_code == 200, answer.text
    assert answer.json()["device_token"]


def test_two_redeems_are_two_devices_with_two_tokens(harness):
    secret = _secret(harness)
    first = harness.remote().post("/api/pair/enroll", json={"enrollment_secret": secret, "device_name": "iPhone"}).json()
    second = harness.remote().post("/api/pair/enroll", json={"enrollment_secret": secret, "device_name": "iPad"}).json()
    assert first["device_id"] != second["device_id"]
    assert first["device_token"] != second["device_token"]
    assert {d.name for d in harness.app_db.list_devices()} == {"iPhone", "iPad"}


def test_a_wrong_secret_is_401_with_no_token(harness):
    _secret(harness)
    answer = harness.remote().post("/api/pair/enroll", json={"enrollment_secret": "nope", "device_name": "iPhone"})
    assert answer.status_code == 401
