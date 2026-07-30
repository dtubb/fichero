from __future__ import annotations

import importlib
import json
from urllib.parse import quote

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from fichero_cli import __main__ as cli
from fichero_server.security import accounts
from fichero_server.db.app import AppDatabase
from fichero_cli import FicheroError
from fichero_cli import client as client_module

runner = CliRunner()


class _AppBackedClient:
    test_client: TestClient | None = None

    def __init__(self, *, token=None, library_path=None, as_user=None, **_kwargs):
        self.token = token
        self.library_path = library_path
        self.as_user = as_user

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def close(self):
        pass

    def request(self, method, path, *, params=None, json=None, files=None):
        headers = {}
        token = self.token if self.token is not None else client_module._read_token(as_user=self.as_user)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if self.library_path:
            headers["X-Fichero-Library-Path"] = quote(self.library_path, safe="/")
        response = self.test_client.request(
            method,
            path,
            params=params,
            json=json,
            files=files,
            headers=headers,
        )
        if response.status_code >= 400:
            raise FicheroError(
                f"{method} {path} -> {response.status_code}: {response.text}",
                status_code=response.status_code,
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()


def _install_cli_app_client(monkeypatch, app_db: AppDatabase, tmp_path):
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "0")
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "cli-session.json")
    monkeypatch.setattr(client_module, "_TOKEN_PATH", tmp_path / ".api-key")

    import fichero_server.api.main as api_main
    from fichero_server.api.routes.auth.accounts import get_app_database

    api_main = importlib.reload(api_main)
    api_main.app.dependency_overrides[get_app_database] = lambda: app_db
    test_client = TestClient(api_main.app)
    _AppBackedClient.test_client = test_client
    monkeypatch.setattr(cli, "FicheroClient", _AppBackedClient)
    return api_main, test_client


def test_auth_login_stores_session_file_and_whoami_uses_it(monkeypatch, app_db, tmp_path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("secret"),
        is_owner=True,
    )
    api_main, test_client = _install_cli_app_client(monkeypatch, app_db, tmp_path)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "secret")

    try:
        login = runner.invoke(cli.app, ["auth", "login", "alice"])
        assert login.exit_code == 0
        assert "username: alice" in login.output

        session_path = client_module._CLI_SESSION_PATH
        session_payload = json.loads(session_path.read_text(encoding="utf-8"))
        assert session_payload["current_user"] == "alice"
        assert session_payload["sessions"]["alice"]["session_token"]
        assert (session_path.stat().st_mode & 0o777) == 0o600

        whoami = runner.invoke(cli.app, ["auth", "whoami"])
        assert whoami.exit_code == 0
        assert "username: alice" in whoami.output
    finally:
        test_client.close()
        api_main.app.dependency_overrides.clear()


def test_auth_logout_revokes_session_and_deletes_file(monkeypatch, app_db, tmp_path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("secret"),
        is_owner=True,
    )
    api_main, test_client = _install_cli_app_client(monkeypatch, app_db, tmp_path)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "secret")

    try:
        assert runner.invoke(cli.app, ["auth", "login", "alice"]).exit_code == 0
        session_token = json.loads(
            client_module._CLI_SESSION_PATH.read_text(encoding="utf-8")
        )["sessions"]["alice"]["session_token"]

        logout = runner.invoke(cli.app, ["auth", "logout"])
        assert logout.exit_code == 0
        assert not client_module._CLI_SESSION_PATH.exists()
        assert app_db.get_session_by_token_hash(accounts.hash_token(session_token)).revoked is True
    finally:
        test_client.close()
        api_main.app.dependency_overrides.clear()


def test_auth_login_preserves_multiple_user_sessions(monkeypatch, app_db, tmp_path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    app_db.create_user(
        username="alice",
        display_name="Alice",
        password_hash=accounts.hash_password("alice-secret"),
        is_owner=True,
    )
    app_db.create_user(
        username="bob",
        display_name="Bob",
        password_hash=accounts.hash_password("bob-secret"),
        is_owner=False,
    )
    api_main, test_client = _install_cli_app_client(monkeypatch, app_db, tmp_path)
    passwords = iter(["alice-secret", "bob-secret"])
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: next(passwords))

    try:
        assert runner.invoke(cli.app, ["auth", "login", "alice"]).exit_code == 0
        assert runner.invoke(cli.app, ["auth", "login", "bob"]).exit_code == 0

        session_payload = json.loads(client_module._CLI_SESSION_PATH.read_text(encoding="utf-8"))
        assert session_payload["current_user"] == "bob"
        assert set(session_payload["sessions"]) == {"alice", "bob"}

        whoami = runner.invoke(cli.app, ["--as-user", "alice", "auth", "whoami"])
        assert whoami.exit_code == 0
        assert "username: alice" in whoami.output
    finally:
        test_client.close()
        api_main.app.dependency_overrides.clear()


def test_auth_login_reports_multiuser_disabled(monkeypatch, app_db, tmp_path):
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    api_main, test_client = _install_cli_app_client(monkeypatch, app_db, tmp_path)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: "secret")

    try:
        result = runner.invoke(cli.app, ["auth", "login", "alice"])
        assert result.exit_code == 1
        assert "Multi-user auth is disabled on this engine." in result.output
    finally:
        test_client.close()
        api_main.app.dependency_overrides.clear()
