from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta
import importlib

import pytest
from fastapi.testclient import TestClient

from fichero import accounts
from fichero.actions import registry
from fichero.api.auth import initialize_token
from fichero.api.routes import auth_accounts, pairing


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _enable_multiuser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")


def _disable_multiuser(monkeypatch: pytest.MonkeyPatch) -> None:
    # multiuser is default-ON (fichero/multiuser.py), so `delenv` is a no-op —
    # it would leave multiuser enabled. Set the explicit off-switch instead.
    # (Mirrors the 6be649fd fix to test_authz_acl.py for the same class.)
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")


@pytest.fixture(autouse=True)
def clear_pairing_state():
    auth_accounts._LOGIN_ATTEMPTS_BY_IP.clear()
    auth_accounts._LOGIN_ATTEMPTS_BY_ACCOUNT.clear()
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    yield
    auth_accounts._LOGIN_ATTEMPTS_BY_IP.clear()
    auth_accounts._LOGIN_ATTEMPTS_BY_ACCOUNT.clear()
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()


@contextmanager
def _client_for_address(app_db, client_addr: tuple[str, int] = ("testclient", 50000)):
    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero.api.routes.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    with TestClient(api_main.app, client=client_addr) as test_client:
        yield test_client
    api_main.app.dependency_overrides.clear()


@pytest.fixture
def client(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    import fichero.api.main as api_main

    api_main = importlib.reload(api_main)
    from fichero.api.routes.providers import get_app_database

    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    with TestClient(api_main.app) as test_client:
        yield test_client
    api_main.app.dependency_overrides.clear()
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
    importlib.reload(api_main)


def test_bootstrap_first_user_creates_owner(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)

    response = client.post(
        "/api/users",
        headers=_bearer(initialize_token()),
        json={
            "username": "owner",
            "display_name": "Owner",
            "password": "password-1",
            "is_owner": False,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "owner"
    assert data["is_owner"] is True
    assert app_db.get_user_by_username("owner").is_owner is True


def test_login_success_returns_session_and_me(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("correct horse battery staple"),
        is_owner=True,
    )

    response = client.post(
        "/api/auth/login",
        json={
            "username": "alice",
            "password": "correct horse battery staple",
            "device_label": "MacBook Pro",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["username"] == "alice"
    assert payload["session_token"]

    me = client.get("/api/auth/me", headers=_bearer(payload["session_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "alice"

    identity = client.get("/api/auth/identity", headers=_bearer(payload["session_token"]))
    assert identity.status_code == 200
    assert identity.json() == {
        "multiuser_enabled": True,
        "auth_kind": "session",
        "user": {
            "id": app_db.get_user_by_username("alice").id,
            "username": "alice",
            "display_name": "Alice",
            "is_owner": True,
        },
        "is_owner_access": True,
    }


def test_login_unknown_user_and_bad_password_both_return_401(
    client, app_db, monkeypatch
):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("correct horse battery staple"),
        is_owner=True,
    )

    missing = client.post(
        "/api/auth/login",
        json={"username": "missing", "password": "whatever"},
    )
    wrong = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )

    assert missing.status_code == 401
    assert wrong.status_code == 401


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("alice", "wrong-password"),
        ("missing", "anything"),
    ],
)
def test_login_rejects_bad_credentials(client, app_db, monkeypatch, username, password):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("correct horse battery staple"),
        is_owner=True,
    )

    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )

    assert response.status_code == 401


def test_login_rate_limit_locks_sixth_attempt(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("correct horse battery staple"),
        is_owner=True,
    )

    for _ in range(auth_accounts.LOGIN_RATE_LIMIT):
        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong-password"},
        )
        assert response.status_code == 401

    locked = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )

    assert locked.status_code == 429
    assert locked.headers["retry-after"].isdigit()


def test_successful_login_resets_rate_limit_counter(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )

    for _ in range(auth_accounts.LOGIN_RATE_LIMIT - 1):
        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong-password"},
        )
        assert response.status_code == 401

    assert auth_accounts._LOGIN_ATTEMPTS_BY_ACCOUNT["alice"]

    success = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password"},
    )

    assert success.status_code == 200
    assert "alice" not in auth_accounts._LOGIN_ATTEMPTS_BY_ACCOUNT

    follow_up = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert follow_up.status_code == 401


def test_login_lockout_applies_per_account_and_per_ip(app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    app_db.create_user(
        username="bob",
        display_name="Bob",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )

    with _client_for_address(app_db, ("198.51.100.10", 5000)) as ip_one:
        for _ in range(auth_accounts.LOGIN_RATE_LIMIT):
            response = ip_one.post(
                "/api/auth/login",
                json={"username": "alice", "password": "wrong-password"},
            )
            assert response.status_code == 401

        same_account_new_ip = None
        with _client_for_address(app_db, ("198.51.100.11", 5000)) as ip_two:
            same_account_new_ip = ip_two.post(
                "/api/auth/login",
                json={"username": "alice", "password": "wrong-password"},
            )
        assert same_account_new_ip.status_code == 429

        same_ip_other_account = ip_one.post(
            "/api/auth/login",
            json={"username": "bob", "password": "wrong-password"},
        )
        assert same_ip_other_account.status_code == 429


def test_login_rate_limit_window_expiry_frees_account(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    base_now = datetime(2026, 1, 1, 12, 0, 0)

    class FrozenDateTime(datetime):
        current = base_now

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz is None else tz.fromutc(cls.current.replace(tzinfo=tz))

    monkeypatch.setattr(auth_accounts, "datetime", FrozenDateTime)

    for _ in range(auth_accounts.LOGIN_RATE_LIMIT):
        response = client.post(
            "/api/auth/login",
            json={"username": "alice", "password": "wrong-password"},
        )
        assert response.status_code == 401

    locked = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert locked.status_code == 429

    FrozenDateTime.current = base_now + auth_accounts.LOGIN_RATE_WINDOW + timedelta(seconds=1)
    freed = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert freed.status_code == 401


def test_expired_session_is_rejected(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
        device_label="test-device",
        ttl=timedelta(seconds=-1),
    )

    response = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert response.status_code == 401


def test_session_last_seen_touch_is_throttled(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_token = accounts.new_session_token()
    token_hash = accounts.hash_token(raw_token)
    app_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        device_label="test-device",
        ttl=timedelta(days=1),
    )
    app_db.touch_session(token_hash, when=datetime.now() - timedelta(minutes=5))
    original_touch = app_db.touch_session
    touches = []

    def touch_spy(*args, **kwargs):
        touches.append((args, kwargs))
        return original_touch(*args, **kwargs)

    monkeypatch.setattr(app_db, "touch_session", touch_spy)

    first = client.get("/api/auth/me", headers=_bearer(raw_token))
    after_first = app_db.get_session_by_token_hash(token_hash).last_seen_at
    second = client.get("/api/auth/me", headers=_bearer(raw_token))
    after_second = app_db.get_session_by_token_hash(token_hash).last_seen_at
    original_touch(token_hash, when=datetime.now() - timedelta(minutes=5))
    third = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert len(touches) == 2
    assert after_second == after_first




def test_revoked_session_is_rejected(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )
    raw_token = accounts.new_session_token()
    token_hash = accounts.hash_token(raw_token)
    app_db.create_session(
        user_id=user.id,
        token_hash=token_hash,
        device_label="test-device",
        ttl=timedelta(days=1),
    )
    app_db.revoke_session(token_hash)

    response = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert response.status_code == 401


def test_multiple_concurrent_sessions_per_user(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )

    first = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password"},
    )
    second = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password", "device_label": "iPad"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_token = first.json()["session_token"]
    second_token = second.json()["session_token"]
    assert first_token != second_token

    assert client.get("/api/auth/me", headers=_bearer(first_token)).status_code == 200
    assert client.get("/api/auth/me", headers=_bearer(second_token)).status_code == 200


def test_owner_only_admin_rejects_non_owner(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    app_db.create_user(
        username="member",
        display_name="Member",
        password_hash=accounts.hash_password("password"),
        is_owner=False,
    )

    login = client.post(
        "/api/auth/login",
        json={"username": "member", "password": "password"},
    )
    assert login.status_code == 200

    response = client.get(
        "/api/users",
        headers=_bearer(login.json()["session_token"]),
    )

    assert response.status_code == 403


def test_multiuser_flag_off_leaves_shared_secret_behavior_unchanged(
    client,
    app_db,
    monkeypatch,
):
    _disable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
        device_label="test-device",
        ttl=timedelta(days=1),
    )

    login = client.post(
        "/api/auth/login",
        json={"username": "alice", "password": "password"},
    )
    assert login.status_code == 404

    session_auth = client.get("/api/providers", headers=_bearer(raw_token))
    assert session_auth.status_code == 401

    shared_secret = client.get("/api/providers", headers=_bearer(initialize_token()))
    assert shared_secret.status_code == 200
    identity = client.get("/api/auth/identity", headers=_bearer(initialize_token()))
    assert identity.status_code == 200
    assert identity.json() == {
        "multiuser_enabled": False,
        "auth_kind": "bootstrap",
        "user": None,
        "is_owner_access": True,
    }


def test_pairing_valid_code_returns_device_token_that_authenticates(
    client,
    app_db,
    monkeypatch,
):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    session_token = login.json()["session_token"]

    code_response = client.post("/api/pair/code", headers=_bearer(session_token))
    assert code_response.status_code == 200

    pair_response = client.post(
        "/api/pair",
        json={
            "code": code_response.json()["code"],
            "device_name": "Alice iPad",
        },
    )

    assert pair_response.status_code == 200
    device_token = pair_response.json()["device_token"]
    me = client.get("/api/auth/me", headers=_bearer(device_token))
    assert me.status_code == 200
    assert me.json()["username"] == "owner"
    identity = client.get("/api/auth/identity", headers=_bearer(device_token))
    assert identity.status_code == 200
    assert identity.json()["auth_kind"] == "device"
    assert identity.json()["user"]["username"] == "owner"


def test_identity_requires_authenticated_credential(client, monkeypatch):
    _enable_multiuser(monkeypatch)

    response = client.get("/api/auth/identity", headers=_bearer("not-a-real-token"))

    assert response.status_code == 401
    assert response.json() == {"detail": "missing or invalid Authorization header"}


def test_pairing_flow_works_with_bootstrap_auth_when_multiuser_disabled(
    client,
    app_db,
    monkeypatch,
):
    _disable_multiuser(monkeypatch)

    code_response = client.post("/api/pair/code", headers=_bearer(initialize_token()))
    assert code_response.status_code == 200

    pair_response = client.post(
        "/api/pair",
        json={
            "code": code_response.json()["code"],
            "device_name": "Alice iPad",
        },
    )

    assert pair_response.status_code == 200
    device_token = pair_response.json()["device_token"]

    remote_client = TestClient(client.app, client=("192.0.2.10", 5000))
    remote_response = remote_client.get(
        "/api/providers",
        headers=_bearer(device_token),
    )
    list_response = client.get("/api/pair/devices", headers=_bearer(initialize_token()))

    assert remote_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1


def test_pairing_code_surfaces_optional_tailnet_url(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    monkeypatch.setenv("FICHERO_TAILNET_URL", "https://fichero-demo.ts.net")
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    session_token = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    ).json()["session_token"]

    response = client.post("/api/pair/code", headers=_bearer(session_token))

    assert response.status_code == 200
    assert response.json()["tailnet_url"] == "https://fichero-demo.ts.net"


@pytest.mark.parametrize(
    ("tailnet_url", "message"),
    [
        ("http://fichero-demo.ts.net", "public_base_url must use https"),
        ("https://127.0.0.1:8765", "tailnet_url must use a .ts.net host"),
    ],
)
def test_pairing_code_rejects_invalid_tailnet_url(
    client, app_db, monkeypatch, tailnet_url, message
):
    _enable_multiuser(monkeypatch)
    monkeypatch.setenv("FICHERO_TAILNET_URL", tailnet_url)
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    session_token = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    ).json()["session_token"]

    response = client.post("/api/pair/code", headers=_bearer(session_token))

    assert response.status_code == 422
    assert response.json()["detail"] == message


def test_revoked_device_token_is_rejected(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_token = accounts.new_session_token()
    device = app_db.create_device(
        name="Alice iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
    )
    app_db.revoke_device(device.id)

    response = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert response.status_code == 401


def test_device_token_expiry_and_revocation(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    fresh_token = accounts.new_session_token()
    expired_token = accounts.new_session_token()
    revoked_token = accounts.new_session_token()

    app_db.create_device(
        name="Fresh iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(fresh_token),
        ttl=timedelta(days=1),
    )
    app_db.create_device(
        name="Expired iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(expired_token),
        ttl=timedelta(seconds=-1),
    )
    revoked = app_db.create_device(
        name="Revoked iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(revoked_token),
        ttl=timedelta(days=1),
    )
    app_db.revoke_device(revoked.id)

    fresh = client.get("/api/auth/me", headers=_bearer(fresh_token))
    expired = client.get("/api/auth/me", headers=_bearer(expired_token))
    revoked_response = client.get("/api/auth/me", headers=_bearer(revoked_token))

    assert fresh.status_code == 200
    assert expired.status_code == 401
    assert revoked_response.status_code == 401


def test_device_last_seen_touch_is_throttled(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    user = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_token = accounts.new_session_token()
    token_hash = accounts.hash_token(raw_token)
    app_db.create_device(
        name="Alice iPad",
        user_id=user.id,
        token_hash=token_hash,
        ttl=timedelta(days=1),
    )
    app_db.touch_device(token_hash, when=datetime.now() - timedelta(minutes=5))
    original_touch = app_db.touch_device
    touches = []

    def touch_spy(*args, **kwargs):
        touches.append((args, kwargs))
        return original_touch(*args, **kwargs)

    monkeypatch.setattr(app_db, "touch_device", touch_spy)

    first = client.get("/api/auth/me", headers=_bearer(raw_token))
    after_first = app_db.get_device_by_token_hash(token_hash).last_seen
    second = client.get("/api/auth/me", headers=_bearer(raw_token))
    after_second = app_db.get_device_by_token_hash(token_hash).last_seen
    original_touch(token_hash, when=datetime.now() - timedelta(minutes=5))
    third = client.get("/api/auth/me", headers=_bearer(raw_token))

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200
    assert len(touches) == 2
    assert after_second == after_first


def test_pairing_rejects_reused_and_expired_codes(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)
    app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    login = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    session_token = login.json()["session_token"]

    code = client.post("/api/pair/code", headers=_bearer(session_token)).json()["code"]
    first = client.post(
        "/api/pair",
        json={"code": code, "device_name": "Alice iPad"},
    )
    reused = client.post(
        "/api/pair",
        json={"code": code, "device_name": "Alice iPad"},
    )

    expired_code = client.post(
        "/api/pair/code",
        headers=_bearer(session_token),
    ).json()["code"]
    pairing._PAIRING_CODES[expired_code].expires_at = datetime.now() - timedelta(
        seconds=1
    )
    expired = client.post(
        "/api/pair",
        json={"code": expired_code, "device_name": "Alice iPad"},
    )

    assert first.status_code == 200
    assert reused.status_code == 401
    assert expired.status_code == 401


def test_pairing_is_rate_limited(client, app_db, monkeypatch):
    _enable_multiuser(monkeypatch)

    statuses = [
        client.post(
            "/api/pair",
            json={"code": "NOPE", "device_name": "Alice iPad"},
        ).status_code
        for _ in range(pairing.PAIRING_RATE_LIMIT + 1)
    ]

    assert statuses[:-1] == [401] * pairing.PAIRING_RATE_LIMIT
    assert statuses[-1] == 429


def test_pairing_attempt_pruning_removes_stale_hosts():
    now = datetime.now()
    stale = now - pairing.PAIRING_RATE_WINDOW - timedelta(seconds=1)
    current = now - timedelta(seconds=1)
    pairing._PAIRING_ATTEMPTS.update(
        {
            "stale.example": [stale],
            "mixed.example": [stale, current],
            "current.example": [current],
        }
    )

    pairing._prune_pairing_attempts(now)

    assert "stale.example" not in pairing._PAIRING_ATTEMPTS
    assert pairing._PAIRING_ATTEMPTS["mixed.example"] == [current]
    assert pairing._PAIRING_ATTEMPTS["current.example"] == [current]


def test_device_actions_are_registered():
    assert "device.list" in registry.names()
    assert "device.revoke" in registry.names()
