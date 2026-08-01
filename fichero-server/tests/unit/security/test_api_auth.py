from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fichero_server.security import accounts
from fichero_server.api.auth import (
    attach_auth_middleware,
    auth_kind_from_request,
    initialize_token,
    library_access_denial_payload,
)
from fichero_server.api.routes.auth import pairing


def _app_with_auth() -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/docs/")
    async def docs_index():
        return {"docs": True}

    @app.get("/api/private")
    async def private():
        return {"private": True}

    attach_auth_middleware(app, "test-token")
    return app


def _drive_asgi(app, path, *, host, server, transport=None, headers=None):
    """Drive ``app`` as a raw ASGI callable with a hand-built scope and return
    ``(status, body)``.

    This lets a test reproduce the exact scope uvicorn builds for a Unix-domain
    socket request: ``server = (<socket path>, None)`` and a Host header that is
    the percent-encoded socket path (which is NOT a valid hostname). That is the
    real UDS request the AsyncHTTPClient ``http+unix`` transport sends.
    """
    import asyncio

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("utf-8"),
        "query_string": b"",
        "root_path": "",
        "server": server,
        "client": None,
        "headers": [(b"host", host.encode("latin-1"))]
        + [(k.lower().encode("latin-1"), v.encode("latin-1")) for k, v in (headers or [])],
    }
    if transport is not None:
        scope["fichero.transport"] = transport

    events = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(event):
        events.append(event)

    asyncio.run(app(scope, receive, send))

    status = next(e["status"] for e in events if e["type"] == "http.response.start")
    body = b"".join(e.get("body", b"") for e in events if e["type"] == "http.response.body")
    return status, body


# The percent-encoded socket path AsyncHTTPClient uses as the Host on the wire.
_UDS_SOCKET_PATH = "/Users/tester/Library/Containers/app.fichero.fichero/Data/tmp/fichero.sock"
_UDS_ENCODED_HOST = (
    "%2FUsers%2Ftester%2FLibrary%2FContainers%2Fapp.fichero.fichero"
    "%2FData%2Ftmp%2Ffichero.sock"
)


def test_uds_health_is_unauthenticated_despite_encoded_host():
    """Regression: /api/health over UDS must skip auth even though the Host
    header is the percent-encoded socket path (which corrupts request.url.path).

    Before the fix, the allowlist keyed off ``request.url.path``, which Starlette
    derives from ``scope["server"] = (<socket path>, None)`` when the Host is not
    a valid hostname -> ``<socket path>:None/api/health`` -> 401. The fix keys off
    ``scope["path"]`` (always ``/api/health``), so it passes through.
    """
    app = _app_with_auth()
    status, _ = _drive_asgi(
        app,
        "/api/health",
        host=_UDS_ENCODED_HOST,
        server=(_UDS_SOCKET_PATH, None),
        transport="uds",
    )
    assert status == 200


def test_uds_encoded_host_does_not_break_openapi_allowlist():
    """The same Host-independence applies to the other unauthenticated paths."""
    app = _app_with_auth()

    @app.get("/docs/")
    async def _docs():  # pragma: no cover - route body trivial
        return {"docs": True}

    status, _ = _drive_asgi(
        app,
        "/docs/",
        host=_UDS_ENCODED_HOST,
        server=(_UDS_SOCKET_PATH, None),
        transport="uds",
    )
    assert status == 200


def test_uds_owner_trust_is_host_independent(monkeypatch):
    """Owner-trust over UDS must not depend on the Host header: a private path
    with the bootstrap token succeeds, and WITHOUT the token still 401s (proving
    we did not loosen auth for the UDS transport)."""
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    app = _app_with_auth()

    # With the bootstrap token -> owner-trusted, 200 (Host is the encoded socket).
    status_ok, _ = _drive_asgi(
        app,
        "/api/private",
        host=_UDS_ENCODED_HOST,
        server=(_UDS_SOCKET_PATH, None),
        transport="uds",
        headers=[("authorization", "Bearer test-token")],
    )
    assert status_ok == 200

    # Without any token -> still rejected, even over the trusted UDS transport.
    status_denied, _ = _drive_asgi(
        app,
        "/api/private",
        host=_UDS_ENCODED_HOST,
        server=(_UDS_SOCKET_PATH, None),
        transport="uds",
    )
    assert status_denied == 401


# The scope the in-process bridge actually builds — see
# fichero-api-client/Sources/FicheroAPIClient/InMemory/AsgiBridge.swift, which
# sets server=("127.0.0.1", 8765) and client=None (ASGI's "no network peer").
# _drive_asgi already hardcodes client=None, so this reproduces it exactly.
_INMEMORY_HOST = "127.0.0.1"
_INMEMORY_SERVER = ("127.0.0.1", 8765)


def test_inmemory_marker_does_not_waive_the_bootstrap_token(monkeypatch):
    """#4432: the ``inmemory`` transport marker makes a request loopback-ELIGIBLE.
    It does not authenticate it.

    ``_is_loopback_request`` treats ``"uds"`` and ``"inmemory"`` identically, and
    the client-side doc comment claimed both "grant loopback-owner auth". They do
    not: ``is_loopback`` decides 403-or-not and the bootstrap token decides
    401-or-not, and the marker only satisfies the first. ``_expected_header()``
    always resolves to ``f"Bearer {token_provider()}"``, so there is no
    configuration in which a token-less in-memory request passes.

    The UDS half of this contract is pinned by
    ``test_uds_owner_trust_is_host_independent``; the in-memory half was not
    pinned at all, which is how a comment could claim the opposite without
    anything failing.
    """
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    app = _app_with_auth()

    # With the bootstrap token -> owner-trusted, 200.
    status_ok, _ = _drive_asgi(
        app,
        "/api/private",
        host=_INMEMORY_HOST,
        server=_INMEMORY_SERVER,
        transport="inmemory",
        headers=[("authorization", "Bearer test-token")],
    )
    assert status_ok == 200

    # Without any token -> 401, NOT 200. The marker is not a credential.
    status_denied, _ = _drive_asgi(
        app,
        "/api/private",
        host=_INMEMORY_HOST,
        server=_INMEMORY_SERVER,
        transport="inmemory",
    )
    assert status_denied == 401

    # And a wrong token is rejected too — the marker cannot rescue it.
    status_wrong, _ = _drive_asgi(
        app,
        "/api/private",
        host=_INMEMORY_HOST,
        server=_INMEMORY_SERVER,
        transport="inmemory",
        headers=[("authorization", "Bearer not-the-token")],
    )
    assert status_wrong == 401


def test_encoded_host_over_tcp_does_not_grant_unauth_private_path():
    """Security: the scope["path"] allowlist must not become a bypass on the TCP
    path. A non-UDS request (no transport marker, real network peer) to a private
    path is still rejected regardless of Host header shenanigans."""
    app = _app_with_auth()
    status, _ = _drive_asgi(
        app,
        "/api/private",
        host=_UDS_ENCODED_HOST,
        server=("192.0.2.10", 5000),
        transport=None,
    )
    # Non-loopback, non-UDS -> rejected (403 "loopback only" here); never granted.
    assert status in (401, 403)


def test_docs_subpath_is_unauthenticated():
    client = TestClient(_app_with_auth())
    response = client.get("/docs/")
    assert response.status_code == 200
    assert response.json() == {"docs": True}


def test_private_endpoint_still_requires_bearer_token():
    client = TestClient(_app_with_auth())
    # conftest autouse (_unit_test_auth_all_testclients) seeds a bootstrap
    # Authorization header on every TestClient; clear it so this negative case
    # is genuinely UNauthenticated.
    client.headers["Authorization"] = ""
    no_auth = client.get("/api/private")
    assert no_auth.status_code == 401

    authed = client.get(
        "/api/private",
        headers={"Authorization": "Bearer test-token"},
    )
    assert authed.status_code == 200


def test_bootstrap_secret_rejects_non_loopback_multiuser(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    client = TestClient(_app_with_auth(), client=("192.0.2.10", 5000))

    response = client.get(
        "/api/private",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 401


def test_unpaired_remote_request_is_denied_with_empty_device_set(monkeypatch, app_db):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    assert app_db.list_devices() == []
    client = TestClient(_app_with_auth(), client=("192.0.2.10", 5000))
    # Clear the conftest-seeded bootstrap Authorization header so this remote
    # request is genuinely unauthenticated (empty header, not the bootstrap token).
    client.headers["Authorization"] = ""

    response = client.get("/api/private")

    assert response.status_code == 401
    assert response.json() == {"detail": "missing or invalid Authorization header"}


def test_bootstrap_secret_accepts_loopback_without_forwarding(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    client = TestClient(_app_with_auth())

    response = client.get(
        "/api/private",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200


def test_bootstrap_secret_rejects_forwarded_loopback_multiuser(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    client = TestClient(_app_with_auth())

    response = client.get(
        "/api/private",
        headers={
            "Authorization": "Bearer test-token",
            "X-Forwarded-For": "192.0.2.10",
        },
    )

    assert response.status_code == 401


def test_non_loopback_device_token_authenticates_multiuser(monkeypatch, app_db):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    user = app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_token = accounts.new_session_token()
    app_db.create_device(
        name="Alice iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
    )
    client = TestClient(_app_with_auth(), client=("192.0.2.10", 5000))

    response = client.get(
        "/api/private",
        headers={"Authorization": f"Bearer {raw_token}"},
    )

    assert response.status_code == 200


def test_non_loopback_device_token_authenticates_single_user(monkeypatch, app_db):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    raw_token = accounts.new_session_token()
    owner = pairing._single_user_pairing_owner(app_db)
    app_db.create_device(
        name="Alice iPad",
        user_id=owner.id,
        token_hash=accounts.hash_token(raw_token),
    )
    client = TestClient(_app_with_auth(), client=("192.0.2.10", 5000))

    response = client.get(
        "/api/private",
        headers={"Authorization": f"Bearer {raw_token}"},
    )

    assert response.status_code == 200


def test_initialize_token_rotates_when_file_contains_device_token(monkeypatch, tmp_path, app_db):
    token_path = tmp_path / ".api-key"
    monkeypatch.setattr("fichero_server.api.auth._token_file_path", lambda: token_path)

    user = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_device_token = accounts.new_session_token()
    app_db.create_device(
        name="Test iPad",
        user_id=user.id,
        token_hash=accounts.hash_token(raw_device_token),
    )
    token_path.write_text(raw_device_token)

    rotated = initialize_token()

    assert rotated != raw_device_token
    assert token_path.read_text() == rotated


def test_initialize_token_rotates_when_file_contains_session_token(
    monkeypatch, tmp_path, app_db
):
    token_path = tmp_path / ".api-key"
    monkeypatch.setattr("fichero_server.api.auth._token_file_path", lambda: token_path)

    user = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    raw_session_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(raw_session_token),
        device_label="Mac",
        ttl=timedelta(days=1),
    )
    token_path.write_text(raw_session_token)

    rotated = initialize_token()

    assert rotated != raw_session_token
    assert token_path.read_text() == rotated


def test_loopback_stale_sandbox_bootstrap_token_gets_explicit_code(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_APP_BUNDLE_ID", "app.fichero.tests")
    host_token_path = tmp_path / "host" / ".api-key"
    sandbox_token_path = tmp_path / "sandbox" / ".api-key"
    monkeypatch.setattr("fichero_server.api.auth._token_file_path", lambda: host_token_path)
    monkeypatch.setattr(
        "fichero_server.api.auth._sandbox_token_file_path",
        lambda _app_id: sandbox_token_path,
    )

    host_token_path.parent.mkdir(parents=True, exist_ok=True)
    host_token_path.write_text("fresh-bootstrap-token")
    sandbox_token_path.parent.mkdir(parents=True, exist_ok=True)
    sandbox_token_path.write_text("stale-bootstrap-token")

    client = TestClient(_app_with_auth())
    response = client.get(
        "/api/private",
        headers={"Authorization": "Bearer stale-bootstrap-token"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "local bootstrap token is stale",
        "code": "stale_bootstrap_token",
    }


def test_loopback_stale_sandbox_bootstrap_token_rejects_follow_up_requests_with_explicit_code(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_APP_BUNDLE_ID", "app.fichero.tests")
    host_token_path = tmp_path / "host" / ".api-key"
    sandbox_token_path = tmp_path / "sandbox" / ".api-key"
    monkeypatch.setattr("fichero_server.api.auth._token_file_path", lambda: host_token_path)
    monkeypatch.setattr(
        "fichero_server.api.auth._sandbox_token_file_path",
        lambda _app_id: sandbox_token_path,
    )

    host_token_path.parent.mkdir(parents=True, exist_ok=True)
    host_token_path.write_text("fresh-bootstrap-token")
    sandbox_token_path.parent.mkdir(parents=True, exist_ok=True)
    sandbox_token_path.write_text("stale-bootstrap-token")

    client = TestClient(_app_with_auth())
    response = client.get(
        "/api/private",
        headers={"Authorization": "Bearer stale-bootstrap-token"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "stale_bootstrap_token"


def test_stale_bootstrap_token_cannot_replay_privileged_side_effect(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_APP_BUNDLE_ID", "app.fichero.tests")
    host_token_path = tmp_path / "host" / ".api-key"
    sandbox_token_path = tmp_path / "sandbox" / ".api-key"
    monkeypatch.setattr("fichero_server.api.auth._token_file_path", lambda: host_token_path)
    monkeypatch.setattr(
        "fichero_server.api.auth._sandbox_token_file_path",
        lambda _app_id: sandbox_token_path,
    )

    host_token_path.parent.mkdir(parents=True, exist_ok=True)
    host_token_path.write_text("fresh-bootstrap-token")
    sandbox_token_path.parent.mkdir(parents=True, exist_ok=True)
    sandbox_token_path.write_text("stale-bootstrap-token")

    touched = {"value": False}
    app = FastAPI()

    @app.post("/api/private")
    async def private():
        touched["value"] = True
        return {"private": True}

    attach_auth_middleware(app, "fresh-bootstrap-token")
    client = TestClient(app)
    response = client.post(
        "/api/private",
        headers={"Authorization": "Bearer stale-bootstrap-token"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "detail": "local bootstrap token is stale",
        "code": "stale_bootstrap_token",
    }
    assert touched["value"] is False


def test_loopback_unknown_token_stays_generic_when_not_sandbox_copy(monkeypatch, tmp_path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    monkeypatch.setenv("FICHERO_APP_BUNDLE_ID", "app.fichero.tests")
    host_token_path = tmp_path / "host" / ".api-key"
    sandbox_token_path = tmp_path / "sandbox" / ".api-key"
    monkeypatch.setattr("fichero_server.api.auth._token_file_path", lambda: host_token_path)
    monkeypatch.setattr(
        "fichero_server.api.auth._sandbox_token_file_path",
        lambda _app_id: sandbox_token_path,
    )

    host_token_path.parent.mkdir(parents=True, exist_ok=True)
    host_token_path.write_text("fresh-bootstrap-token")
    sandbox_token_path.parent.mkdir(parents=True, exist_ok=True)
    sandbox_token_path.write_text("different-sandbox-token")

    client = TestClient(_app_with_auth())
    response = client.get(
        "/api/private",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "missing or invalid Authorization header"}


def _fake_request(**state) -> SimpleNamespace:
    """A stand-in Request exposing only ``.state`` (what these helpers read)."""
    return SimpleNamespace(state=SimpleNamespace(**state))


def test_auth_kind_from_request_precedence_bootstrap_wins():
    # bootstrap outranks both session and device even when all are set.
    req = _fake_request(bootstrap_auth=True, session=object(), device=object())
    assert auth_kind_from_request(req) == "bootstrap"


def test_auth_kind_from_request_session_over_device():
    req = _fake_request(bootstrap_auth=False, session=object(), device=object())
    assert auth_kind_from_request(req) == "session"


def test_auth_kind_from_request_device():
    req = _fake_request(bootstrap_auth=False, session=None, device=object())
    assert auth_kind_from_request(req) == "device"


def test_auth_kind_from_request_none_when_unauthenticated():
    req = _fake_request(bootstrap_auth=False, session=None, device=None)
    assert auth_kind_from_request(req) is None


def test_auth_kind_from_request_none_when_state_missing():
    # A bare object with no ``state`` attribute must not raise.
    assert auth_kind_from_request(SimpleNamespace(state=None)) is None


def test_library_access_denial_payload_shape_and_auth_kind():
    req = _fake_request(
        bootstrap_auth=False,
        session=object(),
        device=None,
        user=SimpleNamespace(username="ada"),
    )
    payload = library_access_denial_payload(
        req, "/tmp/Lib.fichero", required="write", detail="no write grant"
    )
    assert payload["code"] == "library_access_denied"
    assert payload["detail"] == "no write grant"
    assert payload["required"] == "write"
    assert payload["auth_kind"] == "session"
    assert payload["username"] == "ada"
    # Path is normalized (realpath) but must remain a non-empty string keyed off
    # the input, never dropped.
    assert isinstance(payload["library_path"], str) and payload["library_path"]


def test_library_access_denial_payload_username_none_without_user():
    req = _fake_request(bootstrap_auth=True, session=None, device=None, user=None)
    payload = library_access_denial_payload(
        req, "/tmp/Lib.fichero", required="read", detail="denied"
    )
    assert payload["username"] is None
    assert payload["auth_kind"] == "bootstrap"
    assert payload["required"] == "read"
