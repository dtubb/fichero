"""Two real engines side by side for the sharing release bar (#5911, `testenv.two-engines`).

A HOST engine on a free TEST port with a LAN listener and its own TLS identity, and a GUEST engine on its own socket. Both are
`python -m fichero_server` in their own processes, each on throwaway `FICHERO_BASE_PATH`, `HOME`, token directory and Unix
socket under a temp directory: never the owner's ports (8765), data, Keychain or `.api-key`. Opt-in and for the M4 only.
"""
from __future__ import annotations

import base64
import os
import secrets
import shutil
import signal
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
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
    launch_secret: str
    sock: Path
    proc: subprocess.Popen
    port: int | None = None
    lan: str | None = None
    spki_pin: str | None = None
    _clean: list[Path] = field(default_factory=list)
    env_for: Callable[[bool, bool], dict[str, str]] | None = None  # (sharing, multiuser) -> the env the app would give the engine
    _key: object | None = None  # the owner's P-256 key, made once; the engine keeps only its public half
    _client_id: str | None = None

    def _socket_client(self, headers: dict[str, str] | None = None) -> httpx.Client:
        return httpx.Client(transport=httpx.HTTPTransport(uds=str(self.sock)), base_url="http://localhost", timeout=30,
                            headers=headers or {})

    @property
    def uds(self) -> httpx.Client:
        """The host's owner as a person: a session from signing in with their key, never the bootstrap token (#5911, ## 582).
        Sessions are honoured while Multi-user is on (the app's state: multiuser-always-on); with it off the engine takes only
        the bootstrap token, so a host that must mint a code runs with Multi-user on."""
        return self._socket_client({"Authorization": f"Bearer {self.sign_in_owner()}"})

    def sign_in_owner(self) -> str:
        """First run (the owner and their key, with the launch secret the app would have piped in), then the real
        challenge/sign-in routes; returns the session token."""
        from tests.signed_in import new_key, signature_for

        with self._socket_client() as http:
            if self._key is None:
                self._key, pem = new_key()
                made = http.post("/api/auth/first-run", headers={"X-Fichero-Launch-Secret": self.launch_secret},
                                 json={"display_name": "Owner", "public_key_pem": pem, "client": {"kind": "app", "name": self.name}})
                made.raise_for_status()
                self._client_id = made.json()["client"]["id"]
            issued = http.post("/api/auth/challenge", json={"client_id": self._client_id}).json()
            signed = http.post("/api/auth/sign-in", json={
                "client_id": self._client_id, "nonce": issued["nonce"], "signature": signature_for(self._key, self._client_id, issued)})
            signed.raise_for_status()
            return signed.json()["session_token"]

    def wait_ready(self) -> None:
        from tests.integration._engine_wait import wait_for_engine

        def answers() -> bool:
            with httpx.Client(transport=httpx.HTTPTransport(uds=str(self.sock)), base_url="http://localhost", timeout=5) as c:
                return c.get("/api/health").status_code == 200

        why = wait_for_engine(answers, self.proc)
        if why:
            raise RuntimeError(f"{self.name} engine never became ready: {why}")

    def alive(self) -> bool:
        return self.proc.poll() is None

    def _end_process(self) -> None:
        """End the engine and anything it spawned (the engine runs in its own process group)."""
        self._signal_group(signal.SIGTERM)
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self._signal_group(signal.SIGKILL)
            self.proc.wait(timeout=5)

    def _signal_group(self, sig: int) -> None:
        try:
            os.killpg(self.proc.pid, sig)
        except ProcessLookupError:
            pass  # already gone

    def restart(self, *, sharing: bool, multiuser: bool) -> None:
        """What the app does for a Sharing or Multi-user switch: stop its engine and start it again, same libraries and
        socket, with the new settings in its environment. Raises if the new engine does not come up."""
        assert self.env_for is not None, "only a host restarts"
        self._end_process()
        self.persist_multiuser(multiuser)
        self.proc = _popen(self.env_for(sharing, multiuser), self.launch_secret)
        self.wait_ready()
        if self.lan_expected(sharing):  # the LAN listener binds a moment after the socket answers: wait for it, never race it
            self.wait_lan()

    def persist_multiuser(self, on: bool) -> None:
        """What the app's Multi-user switch leaves in the library (#5914: the engine owns the switch, the app no longer passes
        FICHERO_MULTIUSER): the persisted setting, plus the owner's chosen password when it goes on. Written to the throwaway
        app database while the engine is stopped, since the route that does this needs the app's own credential (the bootstrap
        token the ## 582 ratchet keeps out of tests)."""
        assert self._key is not None or not on, "sign the owner in (first run) before turning Multi-user on"
        code = ("from fichero_server.db.app import get_app_db\n"
                "from fichero_server.security.multiuser import MULTIUSER_SETTING_KEY, note_owner_password_set\n"
                "db = get_app_db()\n"
                f"db.set_setting(MULTIUSER_SETTING_KEY, {'true' if on else 'false'!r})\n"
                + ("note_owner_password_set(db)\n" if on else ""))
        env = _env(self.base, self.sock, "unused")
        env.pop("FICHERO_MULTIUSER", None)
        subprocess.run([sys.executable, "-c", code], env=env, check=True, timeout=120)

    def lan_expected(self, sharing: bool) -> bool:
        return sharing and self.port is not None

    def lan_answers(self) -> bool:
        try:
            with httpx.Client(verify=False, base_url=f"https://{self.lan}:{self.port}", timeout=5) as client:
                return client.get("/api/health").status_code == 200
        except httpx.TransportError:
            return False

    def wait_lan(self, seconds: float = 30.0) -> None:
        deadline = time.monotonic() + seconds
        while not self.lan_answers():
            if time.monotonic() > deadline:
                raise RuntimeError(f"{self.name} engine's LAN listener never answered in {seconds:g} s")
            time.sleep(0.25)

    def stop(self) -> None:
        self._end_process()
        for path in self._clean:
            shutil.rmtree(path, ignore_errors=True)


def _env(base: Path, sock: Path, token: str) -> dict[str, str]:
    from tests.integration._engine_wait import _share_real_model_cache

    home = base / "home"
    env = {key: value for key, value in os.environ.items() if not key.startswith("FICHERO_")}  # nothing of the owner's shell reaches a test engine
    env.update(
        HOME=str(home), FICHERO_MODEL_STORE_ROOT=str(_share_real_model_cache(home)), FICHERO_BASE_PATH=str(base),
        FICHERO_BOOTSTRAP_TOKEN=token, FICHERO_TOKEN_DIR=str(base / "token"), FICHERO_UDS_PATH=str(sock),
        FICHERO_LAUNCH_SECRET_STDIN="1",
        FICHERO_FEATURE_TIER="dev", FICHERO_SKIP_DEFAULT_WORKFLOWS="1", FICHERO_ENV="test",
        PYTHONPATH=str(ENGINE_SRC))
    return env


def _popen(env: dict[str, str], launch_secret: str) -> subprocess.Popen:
    """The engine in its own process group, its launch secret piped in on stdin as the app does (one line, then closed)."""
    proc = subprocess.Popen([sys.executable, "-m", "fichero_server"], env=env, stdin=subprocess.PIPE, text=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    proc.stdin.write(launch_secret + "\n")
    proc.stdin.close()
    return proc


def _spawn(name: str, env: dict[str, str], base: Path, sock: Path, **extra) -> Engine:
    launch_secret = secrets.token_hex(32)
    engine = Engine(name=name, base=base, launch_secret=launch_secret, sock=sock, proc=_popen(env, launch_secret),
                    _clean=[base, sock.parent], **extra)
    try:
        engine.wait_ready()
    except Exception:
        engine.stop()
        raise
    return engine


def start_host(lan: str, *, sharing: bool = True, multiuser: bool = False) -> Engine:
    """A host sharing on `lan` at a free test port: the LAN listener beside its socket, its own TLS identity.
    `sharing=False` starts it as the app does with Sharing off (its socket only)."""
    from fichero_server.security.remote_access_tls import prepare_remote_access_tls

    token = secrets.token_urlsafe(24)
    base = Path(tempfile.mkdtemp(prefix="fichero-host-"))
    sock = Path(tempfile.mkdtemp(dir="/tmp", prefix="fsk-")) / "h.sock"
    port = free_port()
    public = f"https://{lan}:{port}"
    material = prepare_remote_access_tls(public, storage_root=base)

    def env_for(sharing_on: bool, multiuser_on: bool) -> dict[str, str]:
        env = _env(base, sock, token)
        if sharing_on:
            env.update(FICHERO_TCP_TLS_ALSO="1", FICHERO_TCP_PORT=str(port), FICHERO_LAN_HOST=lan, FICHERO_PUBLIC_BASE_URL=public,
                       FICHERO_TLS_CERTFILE=str(material.certificate_path), FICHERO_TLS_KEYFILE=str(material.key_path),
                       FICHERO_TLS_SPKI_HASH=material.spki_pin, FICHERO_BIND_HOST=material.bind_host)
        return env

    engine = _spawn("host", env_for(sharing, False), base, sock, port=port, lan=lan, spki_pin=material.spki_pin)
    engine.env_for = env_for
    if multiuser:  # as a person does: the owner exists and chose a password first, then the switch goes on and the engine restarts
        engine.sign_in_owner()
        engine.restart(sharing=sharing, multiuser=True)
    return engine


def start_guest() -> Engine:
    """A guest: its own engine on its own socket and libraries, no network listener."""
    token = secrets.token_urlsafe(24)
    base = Path(tempfile.mkdtemp(prefix="fichero-guest-"))
    sock = Path(tempfile.mkdtemp(dir="/tmp", prefix="fsk-")) / "g.sock"
    return _spawn("guest", _env(base, sock, token), base, sock)


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
