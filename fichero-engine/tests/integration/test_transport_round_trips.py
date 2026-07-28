"""Live round trips over every transport the engine serves (#4176).

*"We need to make sure that things work via socket, via HTTPS, and via
memory. We've been testing via UDS socket, not sure if HTTPS still works or
memory python kit ever worked."* All three worked when probed by hand on
2026-07-28 — but NOTHING guarded them. `test_bind_host.py`, the closest thing,
only asserts argument construction and never binds a socket, so any of the
three could rot silently.

These bind real listeners and drive real requests. Each transport asserts the
same three things, because "the transport works" and "auth works over the
transport" are different claims and only the second one caught the CRITICAL-1
regression:

    /api/health          no token -> 200   (unauthenticated path is reachable)
    /api/actions/registry no token -> 401  (auth IS enforced)
    /api/actions/registry + token -> 200   (loopback-owner bootstrap grant works)

`/api/actions/registry` is deliberate: it needs a valid token but neither a
selected library nor request params, so a pass is an unambiguous 200 rather
than a 400 that has to be argued about.

Recovered from the stranded `transport-tests/` harness (3a638470f), which was
written as standalone assets for a manager to integrate later and never was.
"""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

AUTH_ENDPOINT = "/api/actions/registry"
HEALTH = "/api/health"
REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_SRC = REPO_ROOT / "fichero-engine" / "src"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _child_env(base_path: Path, token: str) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        # Each engine gets its OWN base path: app.duckdb takes an EXCLUSIVE
        # lock, so a shared one silently prevents the second engine booting.
        FICHERO_BASE_PATH=str(base_path),
        # Pin the secret instead of scraping the user's 0600 .api-key, which
        # lives in ~/Library/Application Support and not under BASE_PATH.
        FICHERO_BOOTSTRAP_TOKEN=token,
        FICHERO_MULTIUSER="0",
        FICHERO_FEATURE_TIER="dev",
        FICHERO_SKIP_DEFAULT_WORKFLOWS="1",
        PYTHONPATH=str(ENGINE_SRC),
    )
    # These tests are ABOUT auth behaviour per transport, so the suite-wide
    # auth bypass must not leak in from conftest.
    env.pop("FICHERO_DISABLE_AUTH", None)
    return env


class _Engine:
    def __init__(self, proc: subprocess.Popen, token: str, client_kwargs: dict):
        self.proc = proc
        self.token = token
        self.client_kwargs = client_kwargs

    @property
    def auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def wait_ready(self, timeout: float = 90.0) -> None:
        deadline = time.time() + timeout
        last: Exception | None = None
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"engine exited early: rc={self.proc.returncode}")
            try:
                with httpx.Client(timeout=5, **self.client_kwargs) as c:
                    if c.get(HEALTH).status_code == 200:
                        return
            except Exception as exc:  # not up yet
                last = exc
            time.sleep(0.5)
        raise RuntimeError(f"engine never became ready: {last}")

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)


def _spawn(args: list[str], env: dict[str, str], token: str, client_kwargs: dict) -> _Engine:
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", *args],
        env=env,
        # DEVNULL, not PIPE: an undrained pipe fills and deadlocks the child on
        # shutdown, which reads as a hung teardown rather than a server problem.
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    engine = _Engine(proc, token, client_kwargs)
    try:
        engine.wait_ready()
    except Exception:
        engine.stop()
        raise
    return engine


@pytest.fixture(scope="module")
def uds_engine():
    token = secrets.token_urlsafe(24)
    base = Path(tempfile.mkdtemp(prefix="fichero-uds-"))
    # AF_UNIX sun_path caps near 104 bytes, so the socket goes in a SHORT tmp
    # dir rather than beside the (long) pytest tmp path.
    sock = Path(tempfile.mkdtemp(dir="/tmp", prefix="fsk-")) / "e.sock"
    engine = _spawn(
        # The PRODUCTION target: uds_transport wraps the app and stamps the
        # transport marker. Serving fichero.api.main directly over a socket
        # makes every request read as non-loopback and 403 — a false failure.
        ["fichero.api.uds_transport:app", "--uds", str(sock)],
        _child_env(base, token),
        token,
        {"transport": httpx.HTTPTransport(uds=str(sock)), "base_url": "http://localhost"},
    )
    yield engine
    engine.stop()
    shutil.rmtree(base, ignore_errors=True)
    shutil.rmtree(sock.parent, ignore_errors=True)


@pytest.fixture(scope="module")
def https_engine():
    from fichero.security.remote_access_tls import prepare_remote_access_tls

    token = secrets.token_urlsafe(24)
    base = Path(tempfile.mkdtemp(prefix="fichero-tls-"))
    port = _free_port()
    material = prepare_remote_access_tls(
        f"https://127.0.0.1:{port}", storage_root=base, allow_loopback=True
    )
    engine = _spawn(
        [
            "fichero.api.main:app",
            "--host", "127.0.0.1",
            "--port", str(port),
            "--ssl-certfile", material.certificate_path,
            "--ssl-keyfile", material.key_path,
        ],
        _child_env(base, token),
        token,
        # verify=False: the cert is a locally generated loopback identity, and
        # what is under test is that TLS TERMINATES and serves, not the PKI.
        {"verify": False, "base_url": f"https://127.0.0.1:{port}"},
    )
    yield engine
    engine.stop()
    shutil.rmtree(base, ignore_errors=True)


@pytest.mark.parametrize("fixture_name", ["uds_engine", "https_engine"])
def test_health_is_reachable_without_a_token(fixture_name, request):
    engine = request.getfixturevalue(fixture_name)
    with httpx.Client(timeout=15, **engine.client_kwargs) as client:
        response = client.get(HEALTH)

    assert response.status_code == 200, response.text
    assert response.json().get("status") in {"healthy", "ok"}, response.text


@pytest.mark.parametrize("fixture_name", ["uds_engine", "https_engine"])
def test_auth_is_enforced_without_a_token(fixture_name, request):
    engine = request.getfixturevalue(fixture_name)
    with httpx.Client(timeout=15, **engine.client_kwargs) as client:
        response = client.get(AUTH_ENDPOINT)

    assert response.status_code == 401, f"expected 401, got {response.status_code}: {response.text}"


@pytest.mark.parametrize("fixture_name", ["uds_engine", "https_engine"])
def test_bootstrap_token_grants_access(fixture_name, request):
    """The CRITICAL-1 shape: the loopback-owner grant must work per transport."""
    engine = request.getfixturevalue(fixture_name)
    with httpx.Client(timeout=15, **engine.client_kwargs) as client:
        response = client.get(AUTH_ENDPOINT, headers=engine.auth_header)

    assert response.status_code == 200, f"got {response.status_code}: {response.text}"


@pytest.mark.anyio
async def test_in_memory_asgi_round_trip():
    """In-process ASGI — the Python side of Daniel's "via memory".

    Only REACHABILITY is asserted here. `tests/conftest.py` sets
    FICHERO_DISABLE_AUTH=1 at import time for the whole session, so an app
    running in THIS process cannot demonstrate auth enforcement — it would
    assert the bypass, not the behaviour. Enforcement is covered by the UDS and
    HTTPS legs above, which run in subprocesses with the bypass removed.

    The Swift/PythonKit in-process transport is a separate claim this cannot
    reach; it needs an Xcode run with FICHERO_TEST_* set (#4176).
    """
    from fichero.api.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://asgi.local") as client:
        health = await client.get(HEALTH)
        registry = await client.get(AUTH_ENDPOINT)

    assert health.status_code == 200, health.text
    assert health.json().get("status") in {"healthy", "ok"}, health.text
    # A real routed response, not a 404/500 that happens to be non-empty.
    assert registry.status_code == 200, registry.text
    assert isinstance(registry.json().get("items"), list), registry.text[:200]
