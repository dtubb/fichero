from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient

from fichero.security import accounts


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pairing_client(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")

    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero.api.routes.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    with TestClient(api_main.app) as client:
        yield client
    api_main.app.dependency_overrides.clear()
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
    importlib.reload(api_main)


def _login(client: TestClient, username: str, password: str = "password") -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["session_token"]


def test_non_owner_can_pair_own_device_and_owner_can_revoke(pairing_client, app_db):
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    member = app_db.create_user(
        username="ann",
        display_name="Ann",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    member_token = _login(pairing_client, "ann")

    code_response = pairing_client.post("/api/pair/code", headers=_bearer(member_token))
    assert code_response.status_code == 200

    pair_response = pairing_client.post(
        "/api/pair",
        json={"code": code_response.json()["code"], "device_name": "Ann iPhone"},
    )

    assert pair_response.status_code == 200
    device = app_db.get_device(pair_response.json()["device_id"])
    assert device is not None
    assert device.user_id == member.id

    member_devices = pairing_client.get("/api/pair/devices", headers=_bearer(member_token))
    assert member_devices.status_code == 200
    assert [item["id"] for item in member_devices.json()["items"]] == [device.id]

    owner_token = _login(pairing_client, "owner")
    revoke = pairing_client.post(
        f"/api/pair/devices/{device.id}/revoke",
        headers=_bearer(owner_token),
    )

    assert revoke.status_code == 200
    assert app_db.get_device(device.id).revoked is True
    owner_devices = pairing_client.get("/api/pair/devices", headers=_bearer(owner_token))
    assert owner_devices.status_code == 200
    assert {item["user_id"] for item in owner_devices.json()["items"]} == {member.id}


def test_deactivated_or_invalid_user_cannot_mint_pairing_code(pairing_client, app_db):
    member = app_db.create_user(
        username="ann",
        display_name="Ann",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    token = _login(pairing_client, "ann")
    app_db.revoke_all_for_user(member.id)
    app_db.set_active(member.id, False)

    deactivated = pairing_client.post("/api/pair/code", headers=_bearer(token))
    invalid = pairing_client.post("/api/pair/code", headers=_bearer("not-a-real-token"))

    assert deactivated.status_code == 401
    assert invalid.status_code == 401


def test_non_owner_cannot_revoke_another_users_device(pairing_client, app_db):
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    app_db.create_user(
        username="ann",
        display_name="Ann",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    app_db.create_user(
        username="bob",
        display_name="Bob",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    ann_token = _login(pairing_client, "ann")
    bob_token = _login(pairing_client, "bob")

    ann_code = pairing_client.post("/api/pair/code", headers=_bearer(ann_token)).json()["code"]
    ann_pair = pairing_client.post(
        "/api/pair",
        json={"code": ann_code, "device_name": "Ann iPhone"},
    )
    assert ann_pair.status_code == 200
    device_id = ann_pair.json()["device_id"]

    denied = pairing_client.post(
        f"/api/pair/devices/{device_id}/revoke",
        headers=_bearer(bob_token),
    )
    self_revoke = pairing_client.post(
        f"/api/pair/devices/{device_id}/revoke",
        headers=_bearer(ann_token),
    )

    assert denied.status_code == 403
    assert denied.json()["detail"] == "owner access required"
    assert self_revoke.status_code == 200
