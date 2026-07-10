"""Lazy bootstrap-token resolution in the auth middleware (#2388).

`attach_auth_middleware(app, token_provider=...)` must NOT resolve the token
until the first authenticated request. Importing the app only for its route
response models (the CLI does this for `fichero --help`) therefore never calls
`initialize_token()` and never grabs the `app.duckdb` lock from a second
process.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fichero.api.auth import attach_auth_middleware


def _app_with_provider(provider) -> FastAPI:
    app = FastAPI()

    @app.get("/api/health")
    async def health():
        return {"ok": True}

    @app.get("/api/private")
    async def private():
        return {"private": True}

    attach_auth_middleware(app, token_provider=provider)
    return app


def test_attach_requires_token_or_provider():
    with pytest.raises(ValueError):
        attach_auth_middleware(FastAPI())


def test_provider_not_called_until_first_authenticated_request():
    calls = {"n": 0}

    def provider() -> str:
        calls["n"] += 1
        return "lazy-secret"

    client = TestClient(_app_with_provider(provider))
    # Attaching the middleware (and constructing the client) must not resolve.
    assert calls["n"] == 0

    # An unauthenticated path is allowed through WITHOUT resolving the token.
    assert client.get("/api/health").status_code == 200
    assert calls["n"] == 0

    # First authenticated request resolves exactly once.
    ok = client.get("/api/private", headers={"Authorization": "Bearer lazy-secret"})
    assert ok.status_code == 200
    assert calls["n"] == 1

    # Subsequent requests reuse the cached header — no re-resolution.
    client.get("/api/private", headers={"Authorization": "Bearer lazy-secret"})
    assert calls["n"] == 1


def test_lazy_provider_secret_is_enforced():
    client = TestClient(_app_with_provider(lambda: "lazy-secret"))

    assert client.get("/api/private").status_code == 401
    assert (
        client.get(
            "/api/private", headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/private", headers={"Authorization": "Bearer lazy-secret"}
        ).status_code
        == 200
    )


def test_app_main_attaches_middleware_without_resolving_token(monkeypatch):
    """Importing fichero.api.main must not eagerly resolve the bootstrap token.

    The module attaches the middleware with token_provider=initialize_token; if
    it ever reverts to calling initialize_token() at import, a second process
    (the CLI) would fight the engine for the app.duckdb lock again (#2388).
    """
    import fichero.api.auth as auth_module

    calls = {"n": 0}
    real = auth_module.initialize_token

    def counting_initialize_token(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(auth_module, "initialize_token", counting_initialize_token)

    # Re-attach the way main.py does; provider must stay unevaluated.
    app = FastAPI()
    attach_auth_middleware(app, token_provider=auth_module.initialize_token)
    assert calls["n"] == 0


def test_startup_writes_token_file_so_client_is_not_deadlocked(monkeypatch, tmp_path):
    """Server startup must persist .api-key (#2388 deadlock guard).

    The middleware resolves lazily, but if the file were only written on the
    first authenticated request the Swift app could never read the token to
    MAKE that request. The lifespan helper writes it proactively at serve time.
    """
    import fichero.api.auth as auth_module
    from fichero.api.main import _ensure_bootstrap_token_written

    token_path = tmp_path / ".api-key"
    monkeypatch.setattr(auth_module, "_token_file_path", lambda: token_path)
    monkeypatch.delenv("FICHERO_DISABLE_AUTH", raising=False)

    assert not token_path.exists()
    _ensure_bootstrap_token_written()
    assert token_path.exists()
    assert token_path.read_text().strip()


def test_startup_syncs_sandbox_token_copy_for_follow_up_windows(monkeypatch, tmp_path):
    """Startup must refresh the sandbox copy so new windows keep the same token."""
    import fichero.api.auth as auth_module
    from fichero.api.main import _ensure_bootstrap_token_written

    host_token_path = tmp_path / "host" / ".api-key"
    sandbox_token_path = tmp_path / "sandbox" / ".api-key"
    monkeypatch.setattr(auth_module, "_token_file_path", lambda: host_token_path)
    monkeypatch.setattr(
        auth_module,
        "_sandbox_token_file_path",
        lambda _app_id: sandbox_token_path,
    )
    monkeypatch.delenv("FICHERO_DISABLE_AUTH", raising=False)

    _ensure_bootstrap_token_written()

    assert host_token_path.exists()
    assert sandbox_token_path.exists()
    assert sandbox_token_path.read_text() == host_token_path.read_text()
    assert stat.S_IMODE(sandbox_token_path.stat().st_mode) == 0o600


def test_sync_debug_bootstrap_token_writes_sandbox_copy_that_authenticates(
    monkeypatch, tmp_path
):
    import stat

    import fichero.api.auth as auth_module

    host_token_path = tmp_path / "host" / ".api-key"
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(auth_module, "_token_file_path", lambda: host_token_path)

    token = auth_module.initialize_token(force_rotate=True)
    sandbox_path = auth_module.sync_debug_bootstrap_token(
        token,
        app_id="app.fichero.debug-tests",
    )

    assert host_token_path.read_text() == token
    assert sandbox_path.read_text() == token
    assert stat.S_IMODE(sandbox_path.stat().st_mode) == 0o600

    app = FastAPI()

    @app.get("/api/registry")
    async def registry():
        return {"ok": True}

    attach_auth_middleware(app, token)
    client = TestClient(app)
    response = client.get(
        "/api/registry",
        headers={"Authorization": f"Bearer {sandbox_path.read_text()}"},
    )
    assert response.status_code == 200


def test_sync_app_bootstrap_token_overwrites_stale_container_copy(monkeypatch, tmp_path):
    import fichero.api.auth as auth_module

    host_token_path = tmp_path / "host" / ".api-key"
    sandbox_token_path = tmp_path / "sandbox" / ".api-key"
    monkeypatch.setattr(auth_module, "_token_file_path", lambda: host_token_path)
    monkeypatch.setattr(
        auth_module,
        "_sandbox_token_file_path",
        lambda _app_id: sandbox_token_path,
    )

    host_token_path.parent.mkdir(parents=True, exist_ok=True)
    host_token_path.write_text("fresh-bootstrap-token")
    sandbox_token_path.parent.mkdir(parents=True, exist_ok=True)
    sandbox_token_path.write_text("stale-bootstrap-token")

    sandbox_path = auth_module.sync_app_bootstrap_token(
        "fresh-bootstrap-token",
        app_id="app.fichero.debug-tests",
    )

    assert sandbox_path == sandbox_token_path
    assert host_token_path.read_text() == "fresh-bootstrap-token"
    assert sandbox_token_path.read_text() == "fresh-bootstrap-token"

    app = FastAPI()

    @app.get("/api/registry")
    async def registry():
        return {"ok": True}

    attach_auth_middleware(app, "fresh-bootstrap-token")
    client = TestClient(app)
    response = client.get(
        "/api/registry",
        headers={"Authorization": f"Bearer {sandbox_token_path.read_text()}"},
    )
    assert response.status_code == 200


def test_sync_app_bootstrap_token_stays_scoped_to_requested_app_id(monkeypatch, tmp_path):
    import fichero.api.auth as auth_module

    monkeypatch.setenv("HOME", str(tmp_path))

    token = "fresh-bootstrap-token"
    synced = auth_module.sync_app_bootstrap_token(
        token,
        app_id="app.fichero.debug-tests",
    )
    wrong = (
        tmp_path
        / "Library"
        / "Containers"
        / "app.fichero.other"
        / "Data"
        / "Library"
        / "Application Support"
        / "Fichero"
        / ".api-key"
    )

    assert synced.read_text() == token
    assert "app.fichero.debug-tests" in synced.parts
    assert not wrong.exists()
    assert stat.S_IMODE(synced.stat().st_mode) == 0o600


def test_sync_app_bootstrap_token_discovers_uuid_sandbox_container(monkeypatch, tmp_path):
    import fichero.api.auth as auth_module

    monkeypatch.setenv("HOME", str(tmp_path))
    containers_root = tmp_path / "Library" / "Containers"
    uuid_container = (
        containers_root
        / "123e4567-e89b-12d3-a456-426614174000"
        / "Data"
        / "Library"
        / "Application Support"
        / "Fichero"
    )
    skipped_missing_support = containers_root / "123e4567-e89b-12d3-a456-426614174001" / "Data"
    skipped_non_uuid = (
        containers_root
        / "app.fichero.not-uuid"
        / "Data"
        / "Library"
        / "Application Support"
        / "Fichero"
    )
    uuid_container.mkdir(parents=True, exist_ok=True)
    skipped_missing_support.mkdir(parents=True, exist_ok=True)
    skipped_non_uuid.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(auth_module, "_sandbox_containers_root", lambda: containers_root)

    token = "fresh-bootstrap-token"
    bundle_path = auth_module.sync_app_bootstrap_token(
        token,
        app_id="app.fichero.debug-tests",
    )
    uuid_token_path = uuid_container / ".api-key"

    assert bundle_path.read_text() == token
    assert uuid_token_path.read_text() == token
    assert stat.S_IMODE(uuid_token_path.stat().st_mode) == 0o600
    assert not (skipped_missing_support / "Library" / "Application Support" / "Fichero" / ".api-key").exists()
    assert not (skipped_non_uuid / ".api-key").exists()


def test_sync_app_bootstrap_token_is_idempotent_for_existing_uuid_container(
    monkeypatch, tmp_path
):
    import fichero.api.auth as auth_module

    monkeypatch.setenv("HOME", str(tmp_path))
    containers_root = tmp_path / "Library" / "Containers"
    uuid_support_dir = (
        containers_root
        / "123e4567-e89b-12d3-a456-426614174000"
        / "Data"
        / "Library"
        / "Application Support"
        / "Fichero"
    )
    uuid_support_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(auth_module, "_sandbox_containers_root", lambda: containers_root)

    token = "fresh-bootstrap-token"
    auth_module.sync_app_bootstrap_token(token, app_id="app.fichero.debug-tests")
    bundle_path = auth_module._sandbox_token_file_path("app.fichero.debug-tests")
    uuid_token_path = uuid_support_dir / ".api-key"
    before_mtimes = {
        bundle_path: bundle_path.stat().st_mtime_ns,
        uuid_token_path: uuid_token_path.stat().st_mtime_ns,
    }

    calls: list[Path] = []
    real_write = auth_module._write_token_file

    def counting_write(path: Path, value: str) -> None:
        calls.append(path)
        real_write(path, value)

    monkeypatch.setattr(auth_module, "_write_token_file", counting_write)
    auth_module.sync_app_bootstrap_token(token, app_id="app.fichero.debug-tests")

    assert calls == []
    assert bundle_path.stat().st_mtime_ns == before_mtimes[bundle_path]
    assert uuid_token_path.stat().st_mtime_ns == before_mtimes[uuid_token_path]


def test_prepare_app_bootstrap_token_for_launch_preserves_running_engine_token(
    monkeypatch, tmp_path
):
    import fichero.api.auth as auth_module

    host_token_path = tmp_path / "host" / ".api-key"
    sandbox_token_path = tmp_path / "sandbox" / ".api-key"
    monkeypatch.setattr(auth_module, "_token_file_path", lambda: host_token_path)
    monkeypatch.setattr(
        auth_module,
        "_sandbox_token_file_path",
        lambda _app_id: sandbox_token_path,
    )
    monkeypatch.setenv("FICHERO_BOOTSTRAP_TOKEN", "fresh-app-token")

    host_token_path.parent.mkdir(parents=True, exist_ok=True)
    host_token_path.write_text("running-engine-token")

    resolved = auth_module.prepare_app_bootstrap_token_for_launch(
        app_id="app.fichero.debug-tests",
    )

    assert resolved == "running-engine-token"
    assert host_token_path.read_text() == "running-engine-token"
    assert sandbox_token_path.read_text() == "running-engine-token"


def test_prepare_app_bootstrap_token_for_launch_defers_app_supplied_token_until_startup(
    monkeypatch, tmp_path
):
    import fichero.api.auth as auth_module

    host_token_path = tmp_path / "host" / ".api-key"
    sandbox_token_path = tmp_path / "sandbox" / ".api-key"
    monkeypatch.setattr(auth_module, "_token_file_path", lambda: host_token_path)
    monkeypatch.setattr(
        auth_module,
        "_sandbox_token_file_path",
        lambda _app_id: sandbox_token_path,
    )
    monkeypatch.setenv("FICHERO_BOOTSTRAP_TOKEN", "fresh-app-token")

    resolved = auth_module.prepare_app_bootstrap_token_for_launch(
        app_id="app.fichero.debug-tests",
    )

    assert resolved is None
    assert not host_token_path.exists()
    assert not sandbox_token_path.exists()


def test_uuid_sandbox_token_paths_ignores_unreadable_root(monkeypatch):
    import fichero.api.auth as auth_module

    class UnreadableRoot:
        def iterdir(self):
            raise OSError("nope")

    monkeypatch.setattr(auth_module, "_sandbox_containers_root", lambda: UnreadableRoot())

    assert auth_module._uuid_sandbox_token_paths() == []


def test_startup_skips_token_when_auth_disabled(monkeypatch, tmp_path):
    import fichero.api.auth as auth_module
    from fichero.api.main import _ensure_bootstrap_token_written

    token_path = tmp_path / ".api-key"
    monkeypatch.setattr(auth_module, "_token_file_path", lambda: token_path)
    monkeypatch.setenv("FICHERO_DISABLE_AUTH", "1")

    _ensure_bootstrap_token_written()
    assert not token_path.exists()


def test_cli_help_does_not_open_app_duckdb(tmp_path):
    """`fichero --help` must not create/open app.duckdb (#2388 acceptance).

    Runs the CLI in a subprocess with app storage redirected to an empty dir,
    asserts a clean exit, and asserts no app.duckdb appeared — proving help
    never reached the backend DB even though it imports route response models.
    """
    src = Path(__file__).resolve().parents[2] / "src"
    base = tmp_path / "fichero-base"
    base.mkdir()

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(src), env.get("PYTHONPATH", "")])
    env["FICHERO_BASE_PATH"] = str(base)
    env.pop("FICHERO_DISABLE_AUTH", None)

    result = subprocess.run(
        [sys.executable, "-m", "fichero", "--help"],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert "Usage:" in result.stdout
    db_files = list(base.rglob("app.duckdb"))
    assert not db_files, f"CLI --help opened the app DB: {db_files}"
