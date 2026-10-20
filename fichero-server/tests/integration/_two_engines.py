"""Two real engines side by side for the sharing release bar (#5911, `testenv.two-engines`).

A HOST engine on a free TEST port with a LAN listener and its own TLS identity, and a GUEST engine on its own socket. Both are
`python -m fichero_server` in their own processes, each on throwaway `FICHERO_BASE_PATH`, `HOME`, token directory and Unix
socket under a temp directory: never the owner's ports (8765), data, Keychain or `.api-key`. Opt-in and for the M4 only.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_SRC = REPO_ROOT / "fichero-server" / "src"
SHIPPED_PORT = 8765

#: the harness spawns two engines and binds a LAN address: only where the owner opted in (the M4)
requires_two_engines = pytest.mark.skipif(
    os.environ.get("FICHERO_TWO_ENGINES") != "1", reason="two-engine harness: set FICHERO_TWO_ENGINES=1 (the M4 only)")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    assert port != SHIPPED_PORT
    return port


def lan_address() -> str | None:
    """This Mac's LAN address, or None when it has none (then the test skips)."""
    from fichero_server.security.bind_host import primary_lan_ip

    try:
        ip = primary_lan_ip()
    except OSError:
        return None
    return None if ip.startswith("127.") else ip


@dataclass
class Engine:
    name: str
    base: Path
    token: str
    sock: Path
    proc: subprocess.Popen
    port: int | None = None
    lan: str | None = None
    spki_pin: str | None = None
    _clean: list[Path] = field(default_factory=list)

    @property
    def uds(self) -> httpx.Client:
        return httpx.Client(transport=httpx.HTTPTransport(uds=str(self.sock)), base_url="http://localhost", timeout=30,
                            headers={"Authorization": f"Bearer {self.token}"})

    def wait_ready(self) -> None:
        from tests.integration._engine_wait import wait_for_engine

        def answers() -> bool:
            with httpx.Client(transport=httpx.HTTPTransport(uds=str(self.sock)), base_url="http://localhost", timeout=5) as c:
                return c.get("/api/health").status_code == 200

        why = wait_for_engine(answers, self.proc)
        if why:
            raise RuntimeError(f"{self.name} engine never became ready: {why}")

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        for path in self._clean:
            shutil.rmtree(path, ignore_errors=True)


def _env(base: Path, sock: Path, token: str) -> dict[str, str]:
    from tests.integration._engine_wait import _share_real_model_cache

    home = base / "home"
    env = dict(os.environ)
    env.update(
        HOME=str(home), FICHERO_MODEL_STORE_ROOT=str(_share_real_model_cache(home)), FICHERO_BASE_PATH=str(base),
        FICHERO_BOOTSTRAP_TOKEN=token, FICHERO_TOKEN_DIR=str(base / "token"), FICHERO_UDS_PATH=str(sock),
        FICHERO_MULTIUSER="0", FICHERO_FEATURE_TIER="dev", FICHERO_SKIP_DEFAULT_WORKFLOWS="1", FICHERO_ENV="test",
        PYTHONPATH=str(ENGINE_SRC))
    env.pop("FICHERO_DISABLE_AUTH", None)
    for leaked in ("FICHERO_TCP_PORT", "FICHERO_LAN_HOST", "FICHERO_PUBLIC_BASE_URL", "FICHERO_TLS_CERTFILE",
                   "FICHERO_TLS_KEYFILE", "FICHERO_TLS_SPKI_HASH", "FICHERO_TCP_TLS_ALSO", "FICHERO_BIND_HOST"):
        env.pop(leaked, None)  # nothing of the owner's shell reaches a test engine
    return env


def _spawn(name: str, env: dict[str, str], base: Path, sock: Path, token: str, **extra) -> Engine:
    proc = subprocess.Popen([sys.executable, "-m", "fichero_server"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    engine = Engine(name=name, base=base, token=token, sock=sock, proc=proc, _clean=[base, sock.parent], **extra)
    try:
        engine.wait_ready()
    except Exception:
        engine.stop()
        raise
    return engine


def start_host(lan: str) -> Engine:
    """A host sharing on `lan` at a free test port: the LAN listener beside its socket, its own TLS identity."""
    from fichero_server.security.remote_access_tls import prepare_remote_access_tls

    token = secrets.token_urlsafe(24)
    base = Path(tempfile.mkdtemp(prefix="fichero-host-"))
    sock = Path(tempfile.mkdtemp(dir="/tmp", prefix="fsk-")) / "h.sock"
    port = free_port()
    public = f"https://{lan}:{port}"
    material = prepare_remote_access_tls(public, storage_root=base)
    env = _env(base, sock, token)
    env.update(FICHERO_TCP_TLS_ALSO="1", FICHERO_TCP_PORT=str(port), FICHERO_LAN_HOST=lan, FICHERO_PUBLIC_BASE_URL=public,
               FICHERO_TLS_CERTFILE=str(material.certificate_path), FICHERO_TLS_KEYFILE=str(material.key_path),
               FICHERO_TLS_SPKI_HASH=material.spki_pin, FICHERO_BIND_HOST=material.bind_host)
    return _spawn("host", env, base, sock, token, port=port, lan=lan, spki_pin=material.spki_pin)


def start_guest() -> Engine:
    """A guest: its own engine on its own socket and libraries, no network listener."""
    token = secrets.token_urlsafe(24)
    base = Path(tempfile.mkdtemp(prefix="fichero-guest-"))
    sock = Path(tempfile.mkdtemp(dir="/tmp", prefix="fsk-")) / "g.sock"
    return _spawn("guest", _env(base, sock, token), base, sock, token)


def pairing_link(host: Engine, code: str, pin: str | None = None) -> str:
    """The `fichero://pair` link a person would copy: the host's address, the code and the pin to check."""
    return f"fichero://pair?host={quote(f'https://{host.lan}:{host.port}', safe='')}&code={quote(code)}&pin={quote(pin if pin is not None else (host.spki_pin or ''), safe='')}"


def presented_pin(host: str, port: int) -> str:
    """The SPKI pin (base64 of the SubjectPublicKeyInfo DER, as the engine states it) of the certificate `host:port` really presents."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    pem = ssl.get_server_certificate((host, port))
    cert = x509.load_pem_x509_certificate(pem.encode())
    spki = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return base64.b64encode(spki).decode("ascii")


def pair_with_link(guest: Engine, link: str, device_name: str = "Guest test") -> dict:
    """STAND-IN for `fichero devices pair <link>` (r1's CLI, not landed): check the link's pin against the certificate the host
    presents, redeem the code over the link's address, return the device token. Replace the body with the real command when it lands."""
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(link).query)
    base_url, code, pin = query["host"][0], query["code"][0], query.get("pin", [""])[0]
    parsed = urlparse(base_url)
    if presented_pin(parsed.hostname, parsed.port) != pin:
        raise RuntimeError("the host's certificate does not match the link's pin: refused")
    with httpx.Client(verify=False, base_url=base_url, timeout=30) as client:  # trust comes from the pin check above
        response = client.post("/api/pair", json={"code": code, "device_name": device_name})
    response.raise_for_status()
    return response.json()
