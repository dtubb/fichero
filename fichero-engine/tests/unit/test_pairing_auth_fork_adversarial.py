from __future__ import annotations

from datetime import datetime, timedelta
import importlib
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from fichero import accounts
from fichero.api.auth import attach_auth_middleware
from fichero.api.routes import pairing


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def clear_pairing_state():
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    pairing._PAIRING_RENEW_ATTEMPTS.clear()
    yield
    pairing._PAIRING_CODES.clear()
    pairing._PAIRING_ATTEMPTS.clear()
    pairing._PAIRING_RENEW_ATTEMPTS.clear()


@pytest.fixture
def pairing_client(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    import fichero.api.main as api_main
    from fichero.api.routes import auth_accounts
    from fichero.api.routes.providers import get_app_database as providers_app_db

    api_main = importlib.reload(api_main)
    api_main.app.dependency_overrides[auth_accounts.get_app_database] = lambda: app_db
    api_main.app.dependency_overrides[pairing.get_app_database] = lambda: app_db
    api_main.app.dependency_overrides[providers_app_db] = lambda: app_db
    with TestClient(api_main.app) as client:
        yield client
    api_main.app.dependency_overrides.clear()
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")
    importlib.reload(api_main)


def _create_owner(app_db, *, active: bool = True):
    return app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
        active=active,
    )


def _owner_request(
    user,
    *,
    bootstrap_auth: bool = False,
    host: str = "127.0.0.1",
    scheme: str = "https",
):
    return SimpleNamespace(
        state=SimpleNamespace(user=user, bootstrap_auth=bootstrap_auth),
        client=SimpleNamespace(host=host),
        url=SimpleNamespace(scheme=scheme),
    )


def _owner_session_token(client: TestClient, app_db) -> str:
    _create_owner(app_db)
    response = client.post(
        "/api/auth/login",
        json={"username": "owner", "password": "password"},
    )
    assert response.status_code == 200
    return response.json()["session_token"]


def test_pairing_rejects_replay_after_code_is_used(pairing_client, app_db):
    session_token = _owner_session_token(pairing_client, app_db)
    code_response = pairing_client.post("/api/pair/code", headers=_bearer(session_token))
    assert code_response.status_code == 200
    code = code_response.json()["code"]

    first = pairing_client.post(
        "/api/pair",
        json={"code": code, "device_name": "Owner iPad"},
    )
    replay = pairing_client.post(
        "/api/pair",
        json={"code": code, "device_name": "Replay iPad"},
    )

    assert first.status_code == 200
    assert replay.status_code == 401
    assert code not in pairing._PAIRING_CODES


def test_pairing_rejects_code_at_exact_expiry_boundary(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", "c3BraS1waW4=")
    owner = _create_owner(app_db)
    now = datetime(2026, 7, 4, 12, 0, 0)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    pairing._PAIRING_CODES["ABCD-EFGH"] = pairing._PairingCode(
        code="ABCD-EFGH",
        user_id=owner.id,
        expires_at=now,
    )
    monkeypatch.setattr(pairing, "datetime", FrozenDateTime)

    with pytest.raises(HTTPException, match="invalid or expired pairing code") as exc:
        pairing.pair_device(
            _owner_request(None, host="198.51.100.24"),
            pairing.PairRequest(code="ABCD-EFGH", device_name="Boundary iPad"),
            app_db,
        )

    assert exc.value.status_code == 401


def test_pairing_code_ttl_is_exactly_sixty_seconds(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    owner = _create_owner(app_db)
    now = datetime(2026, 7, 4, 12, 0, 0)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(pairing, "datetime", FrozenDateTime)
    monkeypatch.setattr(pairing, "_new_pairing_code", lambda: "TTL-0001")

    response = pairing.create_pairing_code(_owner_request(owner), app_db)

    assert response.expires_at == now + timedelta(seconds=60)
    assert pairing._PAIRING_CODES["TTL-0001"].expires_at == response.expires_at


def test_pairing_rejects_code_after_ttl_prune(pairing_client, app_db):
    session_token = _owner_session_token(pairing_client, app_db)
    code = pairing_client.post(
        "/api/pair/code",
        headers=_bearer(session_token),
    ).json()["code"]
    pairing._PAIRING_CODES[code].expires_at = datetime.now() - timedelta(seconds=1)
    pairing._prune_pairing_codes(datetime.now())

    response = pairing_client.post(
        "/api/pair",
        json={"code": code, "device_name": "Expired iPad"},
    )

    assert response.status_code == 401


def test_pairing_rate_limiter_returns_429_on_sixth_attempt(pairing_client):
    statuses = [
        pairing_client.post(
            "/api/pair",
            json={"code": "WRONG-CODE", "device_name": "Attacker"},
        ).status_code
        for _ in range(pairing.PAIRING_RATE_LIMIT + 1)
    ]

    assert statuses[: pairing.PAIRING_RATE_LIMIT] == [401] * pairing.PAIRING_RATE_LIMIT
    assert statuses[pairing.PAIRING_RATE_LIMIT] == 429


def test_successful_pairings_do_not_consume_pairing_rate_limit(pairing_client, app_db):
    session_token = _owner_session_token(pairing_client, app_db)

    statuses = []
    for index in range(pairing.PAIRING_RATE_LIMIT + 1):
        code_response = pairing_client.post("/api/pair/code", headers=_bearer(session_token))
        assert code_response.status_code == 200
        code = code_response.json()["code"]
        response = pairing_client.post(
            "/api/pair",
            json={"code": code, "device_name": f"Owner iPad {index}"},
        )
        statuses.append(response.status_code)

    assert statuses == [200] * (pairing.PAIRING_RATE_LIMIT + 1)
    assert pairing._PAIRING_ATTEMPTS.get("testclient") in (None, [])


def test_pairing_rate_limit_isolated_per_host_and_prunes_window(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", "c3BraS1waW4=")
    now = datetime(2026, 7, 4, 12, 0, 0)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(pairing, "datetime", FrozenDateTime)
    host_a = _owner_request(None, host="198.51.100.10")
    host_b = _owner_request(None, host="198.51.100.11")

    for _ in range(pairing.PAIRING_RATE_LIMIT):
        with pytest.raises(HTTPException) as exc:
            pairing.pair_device(
                host_a,
                pairing.PairRequest(code="WRONG-CODE", device_name="Attacker"),
                app_db,
            )
        assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as blocked:
        pairing.pair_device(
            host_a,
            pairing.PairRequest(code="WRONG-CODE", device_name="Attacker"),
            app_db,
        )
    assert blocked.value.status_code == 429

    with pytest.raises(HTTPException) as other_host:
        pairing.pair_device(
            host_b,
            pairing.PairRequest(code="WRONG-CODE", device_name="Attacker"),
            app_db,
        )
    assert other_host.value.status_code == 401

    pairing._PAIRING_ATTEMPTS["stale.example"] = [now - pairing.PAIRING_RATE_WINDOW - timedelta(seconds=1)]
    pairing._prune_pairing_attempts(now)
    assert "stale.example" not in pairing._PAIRING_ATTEMPTS


def test_pairing_rejects_code_for_deactivated_user(pairing_client, app_db):
    owner = _create_owner(app_db)
    code = "ABCD-EFGH"
    pairing._PAIRING_CODES[code] = pairing._PairingCode(
        code=code,
        user_id=owner.id,
        expires_at=datetime.now() + timedelta(seconds=60),
    )
    app_db.set_active(owner.id, False)

    response = pairing_client.post(
        "/api/pair",
        json={"code": code, "device_name": "Inactive Owner iPad"},
    )

    assert response.status_code == 401
    assert code not in pairing._PAIRING_CODES


def test_owner_for_pairing_bootstrap_requires_exactly_one_active_owner(app_db):
    owner = _create_owner(app_db)

    resolved = pairing._owner_for_pairing(
        _owner_request(None, bootstrap_auth=True),
        app_db,
    )
    assert resolved.id == owner.id

    second_owner = app_db.create_user(
        username="owner-2",
        display_name="Owner Two",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    with pytest.raises(HTTPException, match="owner access required"):
        pairing._owner_for_pairing(_owner_request(None, bootstrap_auth=True), app_db)

    app_db.set_active(owner.id, False)
    app_db.set_active(second_owner.id, False)
    with pytest.raises(HTTPException, match="owner access required"):
        pairing._owner_for_pairing(_owner_request(None, bootstrap_auth=True), app_db)


def test_create_pairing_code_prunes_stale_entries_before_minting(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    owner = _create_owner(app_db)
    stale_expired = pairing._PairingCode(
        code="EXPR-1111",
        user_id=owner.id,
        expires_at=datetime.now() - timedelta(seconds=1),
    )
    stale_used = pairing._PairingCode(
        code="USED-1111",
        user_id=owner.id,
        expires_at=datetime.now() + timedelta(seconds=30),
        used=True,
    )
    pairing._PAIRING_CODES[stale_expired.code] = stale_expired
    pairing._PAIRING_CODES[stale_used.code] = stale_used
    monkeypatch.setattr(pairing, "_new_pairing_code", lambda: "FRESH-2222")

    response = pairing.create_pairing_code(_owner_request(owner), app_db)

    assert response.code == "FRESH-2222"
    assert set(pairing._PAIRING_CODES) == {"FRESH-2222"}
    assert pairing._PAIRING_CODES["FRESH-2222"].user_id == owner.id
    assert pairing._PAIRING_CODES["FRESH-2222"].expires_at == response.expires_at


def test_pair_device_normalizes_code_and_device_name_and_consumes_code(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", "c3BraS1waW4=")
    owner = _create_owner(app_db)
    pairing._PAIRING_CODES["ABCD-EFGH"] = pairing._PairingCode(
        code="ABCD-EFGH",
        user_id=owner.id,
        expires_at=datetime.now() + timedelta(seconds=30),
    )
    monkeypatch.setattr(accounts, "new_session_token", lambda: "device-token")

    response = pairing.pair_device(
        _owner_request(None, host="198.51.100.25"),
        pairing.PairRequest(code=" abcd-efgh ", device_name="  Alice iPad  "),
        app_db,
    )

    stored = app_db.get_device(response.device_id)
    assert response.device_token == "device-token"
    assert response.expires_at == stored.expires_at
    assert stored is not None
    assert stored.name == "Alice iPad"
    assert stored.user_id == owner.id
    assert pairing._PAIRING_CODES == {}


def test_pair_device_rejects_blank_device_name_after_strip_without_consuming_code(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", "c3BraS1waW4=")
    owner = _create_owner(app_db)
    pairing._PAIRING_CODES["ABCD-EFGH"] = pairing._PairingCode(
        code="ABCD-EFGH",
        user_id=owner.id,
        expires_at=datetime.now() + timedelta(seconds=30),
    )

    with pytest.raises(HTTPException, match="device_name is required") as exc:
        pairing.pair_device(
            _owner_request(None, host="198.51.100.26"),
            pairing.PairRequest(code="ABCD-EFGH", device_name="   "),
            app_db,
        )

    assert exc.value.status_code == 422
    assert "ABCD-EFGH" in pairing._PAIRING_CODES
    assert pairing._PAIRING_CODES["ABCD-EFGH"].used is False


def test_pair_device_rejects_remote_plaintext_transport_without_consuming_code(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    owner = _create_owner(app_db)
    pairing._PAIRING_CODES["ABCD-EFGH"] = pairing._PairingCode(
        code="ABCD-EFGH",
        user_id=owner.id,
        expires_at=datetime.now() + timedelta(seconds=30),
    )
    request = _owner_request(None, host="198.51.100.26", scheme="http")

    with pytest.raises(HTTPException, match="remote pairing requires https") as exc:
        pairing.pair_device(
            request,
            pairing.PairRequest(code="ABCD-EFGH", device_name="Remote iPad"),
            app_db,
        )

    assert exc.value.status_code == 400
    assert "ABCD-EFGH" in pairing._PAIRING_CODES
    assert pairing._PAIRING_CODES["ABCD-EFGH"].used is False


def test_create_pairing_code_rejects_remote_plaintext_transport(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    owner = _create_owner(app_db)

    with pytest.raises(HTTPException, match="remote pairing requires https") as exc:
        pairing.create_pairing_code(
            _owner_request(owner, host="198.51.100.26", scheme="http"),
            app_db,
        )

    assert exc.value.status_code == 400


def test_pair_device_rejects_remote_https_without_configured_spki_pin(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.delenv("FICHERO_TLS_SPKI_HASH", raising=False)
    owner = _create_owner(app_db)
    pairing._PAIRING_CODES["ABCD-EFGH"] = pairing._PairingCode(
        code="ABCD-EFGH",
        user_id=owner.id,
        expires_at=datetime.now() + timedelta(seconds=30),
    )
    request = _owner_request(None, host="198.51.100.27", scheme="https")

    with pytest.raises(
        HTTPException,
        match="remote pairing unavailable without configured SPKI pin",
    ) as exc:
        pairing.pair_device(
            request,
            pairing.PairRequest(code="ABCD-EFGH", device_name="Remote iPad"),
            app_db,
        )

    assert exc.value.status_code == 503
    assert "ABCD-EFGH" in pairing._PAIRING_CODES
    assert pairing._PAIRING_CODES["ABCD-EFGH"].used is False


def test_create_pairing_code_rejects_remote_https_without_configured_spki_pin(
    app_db, monkeypatch
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.delenv("FICHERO_TLS_SPKI_HASH", raising=False)
    owner = _create_owner(app_db)

    with pytest.raises(
        HTTPException,
        match="remote pairing unavailable without configured SPKI pin",
    ) as exc:
        pairing.create_pairing_code(
            _owner_request(owner, host="198.51.100.27", scheme="https"),
            app_db,
        )

    assert exc.value.status_code == 503


def test_pair_device_allows_remote_https_with_configured_spki_pin(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_TLS_SPKI_HASH", "c3BraS1waW4=")
    owner = _create_owner(app_db)
    pairing._PAIRING_CODES["ABCD-EFGH"] = pairing._PairingCode(
        code="ABCD-EFGH",
        user_id=owner.id,
        expires_at=datetime.now() + timedelta(seconds=30),
    )
    monkeypatch.setattr(accounts, "new_session_token", lambda: "device-token")
    request = _owner_request(None, host="198.51.100.28", scheme="https")

    response = pairing.pair_device(
        request,
        pairing.PairRequest(code="ABCD-EFGH", device_name="Remote iPad"),
        app_db,
    )

    assert response.device_token == "device-token"
    assert app_db.get_device(response.device_id) is not None
    assert pairing._PAIRING_CODES == {}


def test_pairing_validation_errors_scrub_submitted_code(pairing_client, app_db):
    session_token = _owner_session_token(pairing_client, app_db)
    secret_code = pairing_client.post("/api/pair/code", headers=_bearer(session_token)).json()["code"]

    missing_field = pairing_client.post("/api/pair", json={"code": secret_code})
    malformed_json = pairing_client.post(
        "/api/pair",
        content=f'{{"code": "{secret_code}",',
        headers={"Content-Type": "application/json"},
    )

    for response in (missing_field, malformed_json):
        assert response.status_code == 422
        assert response.json() == {"detail": "invalid pairing request"}
        assert secret_code not in response.text


def test_list_devices_returns_revoked_state_and_revoke_missing_device_404(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    owner = _create_owner(app_db)
    active = app_db.create_device(
        name="Laptop",
        user_id=owner.id,
        token_hash=accounts.hash_token("active-token"),
    )
    revoked = app_db.create_device(
        name="Tablet",
        user_id=owner.id,
        token_hash=accounts.hash_token("revoked-token"),
    )
    app_db.revoke_device(revoked.id)

    response = pairing.list_devices(_owner_request(owner), app_db)

    assert response.count == 2
    assert [device.id for device in response.items] == [active.id, revoked.id]
    assert [device.revoked for device in response.items] == [False, True]

    with pytest.raises(HTTPException, match="device not found") as exc:
        pairing.revoke_device(_owner_request(owner), "missing-device", app_db)
    assert exc.value.status_code == 404


def test_warn_pairing_single_process_invariant_logs_once(monkeypatch, caplog):
    monkeypatch.setattr(pairing, "_PAIRING_WORKER_WARNING_EMITTED", False)
    monkeypatch.setattr(pairing, "_detect_configured_worker_count", lambda: 3)

    with caplog.at_level("WARNING"):
        pairing.warn_pairing_single_process_invariant()
        pairing.warn_pairing_single_process_invariant()

    warnings = [record.message for record in caplog.records if "process-local" in record.message]
    assert len(warnings) == 1
    assert "worker count appears to be 3" in warnings[0]


@pytest.mark.parametrize(
    ("env", "argv", "expected"),
    [
        ({"FICHERO_UVICORN_WORKERS": "2"}, ["prog"], 2),
        ({}, ["prog", "--workers", "4"], 4),
        ({}, ["prog", "--workers=5"], 5),
    ],
)
def test_detect_configured_worker_count_reads_env_and_argv(monkeypatch, env, argv, expected):
    for name in ("FICHERO_UVICORN_WORKERS", "UVICORN_WORKERS", "WEB_CONCURRENCY"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(pairing.sys, "argv", argv)

    assert pairing._detect_configured_worker_count() == expected


def _auth_fork_app() -> FastAPI:
    app = FastAPI()

    @app.get("/api/private")
    async def private(request: Request):
        user = getattr(request.state, "user", None)
        return {
            "username": getattr(user, "username", None),
            "session": hasattr(request.state, "session"),
            "device": hasattr(request.state, "device"),
            "bootstrap": getattr(request.state, "bootstrap_auth", None),
        }

    attach_auth_middleware(app, "bootstrap-secret")
    return app


def test_auth_fork_accepts_valid_session_and_valid_device(monkeypatch, app_db):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    session_token = accounts.new_session_token()
    device_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(session_token),
        device_label="Mac",
        ttl=timedelta(days=1),
    )
    app_db.create_device(
        name="iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(device_token),
        ttl=timedelta(days=1),
    )
    client = TestClient(_auth_fork_app(), client=("192.0.2.10", 5000))

    session_response = client.get("/api/private", headers=_bearer(session_token))
    device_response = client.get("/api/private", headers=_bearer(device_token))

    assert session_response.status_code == 200
    assert session_response.json() == {
        "username": "alice",
        "session": True,
        "device": False,
        "bootstrap": False,
    }
    assert device_response.status_code == 200
    assert device_response.json() == {
        "username": "alice",
        "session": False,
        "device": True,
        "bootstrap": False,
    }


@pytest.mark.parametrize(
    "token_kind",
    ["revoked_device", "expired_session", "expired_device", "garbage"],
)
def test_auth_fork_rejects_invalid_token_matrix(monkeypatch, app_db, token_kind):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    user = app_db.create_user(
        username=f"user-{token_kind}",
        display_name="User",
        password_hash=accounts.hash_password("password"),
    )
    token = accounts.new_session_token()
    if token_kind == "revoked_device":
        device = app_db.create_device(
            name="Revoked iPad",
            user_id=user.id,
            token_hash=accounts.hash_token(token),
            ttl=timedelta(days=1),
        )
        app_db.revoke_device(device.id)
    elif token_kind == "expired_session":
        app_db.create_session(
            user_id=user.id,
            token_hash=accounts.hash_token(token),
            device_label="Expired Mac",
            ttl=timedelta(seconds=-1),
        )
    elif token_kind == "expired_device":
        app_db.create_device(
            name="Expired iPad",
            user_id=user.id,
            token_hash=accounts.hash_token(token),
            ttl=timedelta(seconds=-1),
        )
    else:
        token = "not-a-real-token"
    client = TestClient(_auth_fork_app(), client=("192.0.2.10", 5000))

    response = client.get("/api/private", headers=_bearer(token))

    assert response.status_code == 401
    if token_kind == "expired_device":
        assert response.json()["detail"] == "device token expired"
    else:
        assert response.json()["detail"] == "missing or invalid Authorization header"


def test_pairing_device_renew_rotates_token_extends_expiry_and_audits(pairing_client, app_db):
    session_token = _owner_session_token(pairing_client, app_db)
    pair_response = pairing_client.post(
        "/api/pair",
        json={
            "code": pairing_client.post("/api/pair/code", headers=_bearer(session_token)).json()["code"],
            "device_name": "Owner iPad",
        },
    )
    old_token = pair_response.json()["device_token"]
    old_device = app_db.get_device_by_token_hash(accounts.hash_token(old_token))
    old_expires_at = old_device.expires_at

    renew = pairing_client.post("/api/pair/devices/renew", headers=_bearer(old_token))

    assert renew.status_code == 200
    new_token = renew.json()["device_token"]
    assert new_token != old_token
    assert pairing_client.get("/api/auth/me", headers=_bearer(old_token)).status_code == 401
    assert pairing_client.get("/api/auth/me", headers=_bearer(new_token)).status_code == 200
    renewed = app_db.get_device(pair_response.json()["device_id"])
    assert renewed is not None
    assert renewed.expires_at > old_expires_at
    audits = [row for row in app_db.list_action_audits() if row.action_name == "device.renew"]
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].target_ids == [renewed.id]


def test_pairing_device_renew_rejects_expired_at_boundary(pairing_client, app_db):
    owner = _create_owner(app_db)
    token = accounts.new_session_token()
    device = app_db.create_device(
        name="Boundary iPad",
        user_id=owner.id,
        token_hash=accounts.hash_token(token),
        ttl=timedelta(days=1),
    )
    device.expires_at = datetime.now()
    app_db.renew_device(
        device.id,
        token_hash=device.token_hash,
        when=device.last_seen,
        ttl=timedelta(seconds=0),
    )

    response = pairing_client.post("/api/pair/devices/renew", headers=_bearer(token))

    assert response.status_code == 401
    assert response.json()["detail"] == "device token expired"


def test_pairing_device_renew_unknown_and_revoked_tokens_match(pairing_client, app_db):
    owner = _create_owner(app_db)
    revoked_token = accounts.new_session_token()
    device = app_db.create_device(
        name="Revoked iPad",
        user_id=owner.id,
        token_hash=accounts.hash_token(revoked_token),
    )
    app_db.revoke_device(device.id)

    revoked = pairing_client.post("/api/pair/devices/renew", headers=_bearer(revoked_token))
    unknown = pairing_client.post("/api/pair/devices/renew", headers=_bearer("not-a-real-token"))

    assert revoked.status_code == 401
    assert unknown.status_code == 401
    assert revoked.json() == unknown.json() == {"detail": "missing or invalid Authorization header"}


def test_pairing_device_renew_is_rate_limited_per_host(pairing_client, app_db):
    session_token = _owner_session_token(pairing_client, app_db)
    token = pairing_client.post(
        "/api/pair",
        json={
            "code": pairing_client.post("/api/pair/code", headers=_bearer(session_token)).json()["code"],
            "device_name": "Owner iPad",
        },
    ).json()["device_token"]

    statuses: list[int] = []
    for _ in range(pairing.PAIRING_RATE_LIMIT):
        response = pairing_client.post("/api/pair/devices/renew", headers=_bearer(token))
        statuses.append(response.status_code)
        token = response.json()["device_token"]
    blocked = pairing_client.post("/api/pair/devices/renew", headers=_bearer(token))

    assert statuses == [200] * pairing.PAIRING_RATE_LIMIT
    assert blocked.status_code == 429
    assert blocked.json()["detail"] == "pairing renew rate limit exceeded"


def test_auth_fork_rejects_bootstrap_secret_from_non_loopback(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    client = TestClient(_auth_fork_app(), client=("192.0.2.10", 5000))

    response = client.get("/api/private", headers=_bearer("bootstrap-secret"))

    assert response.status_code == 401
