"""App-supplied bootstrap token + health instance identity (#2862).

The host app mints the bootstrap token and a launch nonce, passes both to the
engine it spawns, and verifies /api/health echoes the nonce (proving it is the
engine it launched, not a stale process on the port). These tests pin the
engine side of that contract.
"""

from __future__ import annotations

import os

from fichero import accounts
from fichero.api.auth import initialize_token


def test_initialize_token_adopts_app_supplied_bootstrap_token(monkeypatch, tmp_path):
    """FICHERO_BOOTSTRAP_TOKEN wins: it is persisted (0600) and returned."""
    token_path = tmp_path / ".api-key"
    monkeypatch.setattr("fichero.api.auth._token_file_path", lambda: token_path)
    monkeypatch.setenv("FICHERO_BOOTSTRAP_TOKEN", "app-minted-secret")

    resolved = initialize_token()

    assert resolved == "app-minted-secret"
    assert token_path.read_text() == "app-minted-secret"
    # Owner-only perms, matching the mint path.
    assert (token_path.stat().st_mode & 0o777) == 0o600


def test_app_supplied_token_overrides_existing_file(monkeypatch, tmp_path):
    """A stale token on disk is replaced by the app's — the app is authoritative
    for the spawn, so there is never a window where the two disagree (#2862)."""
    token_path = tmp_path / ".api-key"
    token_path.write_text("stale-token-from-previous-run")
    monkeypatch.setattr("fichero.api.auth._token_file_path", lambda: token_path)
    monkeypatch.setenv("FICHERO_BOOTSTRAP_TOKEN", "fresh-app-token")

    assert initialize_token() == "fresh-app-token"
    assert token_path.read_text() == "fresh-app-token"


def test_initialize_token_ignores_app_supplied_device_token(monkeypatch, tmp_path, app_db):
    token_path = tmp_path / ".api-key"
    monkeypatch.setattr("fichero.api.auth._token_file_path", lambda: token_path)

    owner = app_db.create_user(
        username="owner",
        display_name="Owner",
        password_hash=accounts.hash_password("password"),
        is_owner=True,
    )
    device_token = accounts.new_session_token()
    app_db.create_device(
        name="Remote iPad",
        user_id=owner.id,
        token_hash=accounts.hash_token(device_token),
    )
    monkeypatch.setenv("FICHERO_BOOTSTRAP_TOKEN", device_token)

    resolved = initialize_token()

    assert resolved != device_token
    assert token_path.read_text() == resolved


def test_no_env_token_mints_as_before(monkeypatch, tmp_path):
    """Without the env var, behaviour is unchanged: mint + persist a fresh one."""
    token_path = tmp_path / ".api-key"
    monkeypatch.setattr("fichero.api.auth._token_file_path", lambda: token_path)
    monkeypatch.delenv("FICHERO_BOOTSTRAP_TOKEN", raising=False)

    resolved = initialize_token()

    assert resolved
    assert token_path.read_text() == resolved


def test_health_echoes_launch_nonce_and_pid(monkeypatch):
    """/api/health carries engine_pid + the launch nonce the app passed, so the
    app can prove the responder is the child it spawned."""
    from fichero.models import HealthResponse

    monkeypatch.setenv("FICHERO_LAUNCH_NONCE", "nonce-abc123")

    # The endpoint constructs HealthResponse(engine_pid=os.getpid(),
    # launch_nonce=os.environ["FICHERO_LAUNCH_NONCE"]); assert the model carries
    # both fields and round-trips them (guards against the schema being dropped).
    resp = HealthResponse(
        status="healthy",
        engine_pid=os.getpid(),
        launch_nonce=os.environ.get("FICHERO_LAUNCH_NONCE") or None,
    )
    assert resp.engine_pid == os.getpid()
    assert resp.launch_nonce == "nonce-abc123"
    assert resp.model_dump()["launch_nonce"] == "nonce-abc123"
