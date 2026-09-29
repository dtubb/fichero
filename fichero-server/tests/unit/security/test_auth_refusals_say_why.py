"""Every request the auth middleware refuses logs ONE line naming the check that refused it.

WHY: on 2026-09-28 the Dev Local app got 401 on some requests over a socket where others got 200.
The cause (a second app launch had rewritten the bootstrap token) took twenty minutes to find,
because every refusal looked alike: "missing or invalid Authorization header". One line naming the
branch -- bootstrap_mismatch -- would have said it at once. If this regresses, a refusal is silent
again, or worse, a log line carries a token.

Each branch is driven for real through the middleware, single-user and multiuser. The response each
returns is asserted unchanged; the log line must name the branch, the path, the transport, whether
the request was loopback, the X-Fichero-Client value, and never the token -- only a 6-character
SHA-256 prefix.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from fichero_server.api.routes.auth import pairing
from fichero_server.security import accounts
from tests.unit.security.test_api_auth import _app_with_auth

REMOTE = ("192.0.2.10", 5000)
GENERIC = {"detail": "missing or invalid Authorization header"}


def assert_refused(caplog, *, client=None, headers=None, status=401, body=GENERIC, branch, token=None):
    app_client = TestClient(_app_with_auth(), client=client) if client else TestClient(_app_with_auth())
    app_client.headers["Authorization"] = ""          # the conftest seeds the bootstrap header
    with caplog.at_level(logging.WARNING, logger="fichero_server.api.auth"):
        caplog.clear()
        response = app_client.get("/api/private", headers={"X-Fichero-Client": "app-dev-local", **(headers or {})})
    assert (response.status_code, response.json()) == (status, body)
    lines = [r.getMessage() for r in caplog.records if r.getMessage().startswith("auth refused")]
    assert len(lines) == 1, lines                      # ONE line per refusal
    [line] = lines
    assert f"auth refused {status} branch={branch} " in line
    assert "path=/api/private" in line and "client='app-dev-local'" in line and "transport=tcp" in line
    if token:
        assert token not in line                       # never the token itself
        assert f"token_sha256={hashlib.sha256(token.encode()).hexdigest()[:6]}" in line
    return line


# -- single-user --------------------------------------------------------------------------

@pytest.fixture
def single_user(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")


@pytest.fixture
def multiuser(monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")


def test_single_user_no_header(single_user, caplog):
    line = assert_refused(caplog, branch="missing_header")
    assert "header=missing" in line and "loopback=True" in line and "token_sha256=-" in line


def test_single_user_a_bootstrap_token_that_does_not_match(single_user, caplog):
    line = assert_refused(caplog, headers={"Authorization": "Bearer an-old-bootstrap-token"},
                   branch="bootstrap_mismatch", token="an-old-bootstrap-token")
    assert "header=bearer" in line


def test_single_user_non_loopback_is_403(single_user, caplog):
    line = assert_refused(caplog, client=REMOTE, headers={"Authorization": "Bearer test-token"},
                   status=403, body={"detail": "loopback only"}, branch="non_loopback", token="test-token")
    assert "loopback=False" in line and "192.0.2.10" in line


def _device(app_db, *, ttl=timedelta(days=90), revoked=False) -> str:
    raw = accounts.new_session_token()
    owner = pairing._single_user_pairing_owner(app_db)
    device = app_db.create_device(name="iPad", user_id=owner.id, token_hash=accounts.hash_token(raw), ttl=ttl)
    if revoked:
        app_db.revoke_device(device.id)
    return raw


def test_single_user_an_expired_device_token(single_user, caplog, app_db):
    raw = _device(app_db, ttl=timedelta(seconds=-1))
    assert_refused(caplog, client=REMOTE, headers={"Authorization": f"Bearer {raw}"},
            body={"detail": "device token expired"}, branch="device_token_expired", token=raw)


def test_single_user_a_revoked_device_token(single_user, caplog, app_db):
    raw = _device(app_db, revoked=True)
    assert_refused(caplog, client=REMOTE, headers={"Authorization": f"Bearer {raw}"},
            branch="device_token_rejected", token=raw)


def _stale_sandbox(monkeypatch, tmp_path) -> str:
    monkeypatch.setenv("FICHERO_APP_BUNDLE_ID", "app.fichero.tests")
    host, sandbox = tmp_path / "host" / ".api-key", tmp_path / "sandbox" / ".api-key"
    monkeypatch.setattr("fichero_server.api.auth._token_file_path", lambda: host)
    monkeypatch.setattr("fichero_server.api.auth._sandbox_token_file_path", lambda _app_id: sandbox)
    for path, text in ((host, "fresh-bootstrap-token"), (sandbox, "stale-bootstrap-token")):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return "stale-bootstrap-token"


STALE = {"detail": "local bootstrap token is stale", "code": "stale_bootstrap_token"}


def test_single_user_a_stale_sandbox_bootstrap_token(single_user, caplog, monkeypatch, tmp_path):
    stale = _stale_sandbox(monkeypatch, tmp_path)
    assert_refused(caplog, headers={"Authorization": f"Bearer {stale}"}, body=STALE,
            branch="stale_bootstrap_token", token=stale)


# -- multiuser ----------------------------------------------------------------------------

def test_multiuser_bootstrap_from_off_the_machine(multiuser, caplog):
    assert_refused(caplog, client=REMOTE, headers={"Authorization": "Bearer test-token"},
            body={"detail": "bootstrap auth is loopback only"}, branch="bootstrap_not_loopback", token="test-token")


def test_multiuser_no_header(multiuser, caplog):
    assert_refused(caplog, branch="missing_header")


def test_multiuser_a_header_that_is_not_bearer(multiuser, caplog):
    line = assert_refused(caplog, headers={"Authorization": "Basic dXNlcjpwYXNz"}, branch="not_bearer")
    assert "header=other-scheme" in line and "dXNlcjpwYXNz" not in line


def test_multiuser_an_empty_bearer(multiuser, caplog):
    assert_refused(caplog, headers={"Authorization": "Bearer "}, branch="empty_bearer")


def test_multiuser_an_expired_session(multiuser, caplog, app_db):
    user = app_db.create_user(username="alice", display_name="Alice",
                              password_hash=accounts.hash_password("pw"), is_owner=True)
    raw = accounts.new_session_token()
    app_db.create_session(user.id, accounts.hash_token(raw), None, ttl=timedelta(seconds=-1))
    assert_refused(caplog, headers={"Authorization": f"Bearer {raw}"},
            body={**GENERIC, "code": "session_expired"}, branch="session_expired", token=raw)


def test_multiuser_an_unknown_token(multiuser, caplog):
    assert_refused(caplog, client=REMOTE, headers={"Authorization": "Bearer nobody-issued-this"},
            branch="token_unknown", token="nobody-issued-this")


def test_multiuser_an_expired_device_token(multiuser, caplog, app_db):
    user = app_db.create_user(username="bob", display_name="Bob",
                              password_hash=accounts.hash_password("pw"), is_owner=True)
    raw = accounts.new_session_token()
    app_db.create_device(name="iPad", user_id=user.id, token_hash=accounts.hash_token(raw), ttl=timedelta(seconds=-1))
    assert_refused(caplog, client=REMOTE, headers={"Authorization": f"Bearer {raw}"},
            body={"detail": "device token expired"}, branch="device_token_expired", token=raw)


def test_multiuser_a_stale_sandbox_bootstrap_token(multiuser, caplog, monkeypatch, tmp_path):
    stale = _stale_sandbox(monkeypatch, tmp_path)
    assert_refused(caplog, headers={"Authorization": f"Bearer {stale}"}, body=STALE,
            branch="stale_bootstrap_token", token=stale)


def test_an_accepted_request_logs_no_refusal(single_user, caplog):
    client = TestClient(_app_with_auth())
    with caplog.at_level(logging.WARNING, logger="fichero_server.api.auth"):
        assert client.get("/api/private", headers={"Authorization": "Bearer test-token"}).status_code == 200
    assert not [r for r in caplog.records if r.getMessage().startswith("auth refused")]
