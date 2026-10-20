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
    env_for: Callable[[bool], dict[str, str]] | None = None  # sharing -> the env the app would give the engine
    token: str = ""  # the engine's bootstrap token: the app's own credential, used only by turn_multiuser_on
    cert: Path | None = None  # the host's TLS certificate, which LAN calls are pinned to
    owner_id: str | None = None
    _multiuser: bool = False
    _key: object | None = None  # the owner's P-256 key, made once; the engine keeps only its public half
    _client_id: str | None = None
    library: dict[str, str] | None = None  # the header naming this engine's library, once make_library has run

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
                self.owner_id = made.json()["user"]["id"]
            issued = http.post("/api/auth/challenge", json={"client_id": self._client_id}).json()
            signed = http.post("/api/auth/sign-in", json={
                "client_id": self._client_id, "nonce": issued["nonce"], "signature": signature_for(self._key, self._client_id, issued)})
            signed.raise_for_status()
            return signed.json()["session_token"]

    def log_tail(self, lines: int = 40) -> str:
        try:
            return "\n".join((self.base / "engine.log").read_text(errors="replace").splitlines()[-lines:])
        except OSError:
            return "(no engine.log)"

    def wait_ready(self) -> None:
        from tests.integration._engine_wait import wait_for_engine

        def answers() -> bool:
            with httpx.Client(transport=httpx.HTTPTransport(uds=str(self.sock)), base_url="http://localhost", timeout=5) as c:
                return c.get("/api/health").status_code == 200

        why = wait_for_engine(answers, self.proc)
        if why:
            raise RuntimeError(f"{self.name} engine never became ready: {why}\n--- last 40 lines of its output ---\n{self.log_tail()}")

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

    def restart(self, *, sharing: bool) -> None:
        """What the app does for a Sharing switch: stop its engine and start it again, same libraries and socket, with
        the new settings in its environment (Multi-user is the engine's own persisted setting, #5914: it survives this). Raises if the new engine does not come up."""
        assert self.env_for is not None, "only a host restarts"
        self._end_process()
        self.proc = _popen(self.env_for(sharing), self.launch_secret)
        self.wait_ready()
        if self.lan_expected(sharing):  # the LAN listener binds a moment after the socket answers: wait for it, never race it
            self.wait_lan()

    def lan_ssl(self):
        """TLS for the host's LAN address, pinned to the certificate this harness made for it (never verify=False)."""
        context = ssl.create_default_context(cafile=str(self.cert))
        context.check_hostname = False  # the certificate is pinned; its names are not what is under test
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT  # Python 3.13 rejects a self-signed leaf without the extensions strict mode wants (## 585)
        return context

    def make_library(self, name: str = "Release bar", client: httpx.Client | None = None) -> dict[str, str]:
        """A library on this engine, under its throwaway HOME (an allowed location), as the header every library route wants."""
        path = self.base / "home" / "Documents" / f"{name}.fichero"
        if client is None:
            with self.uds as local:
                made = local.post("/api/library", json={"path": str(path)})
        else:
            made = client.post("/api/library", json={"path": str(path)})
        made.raise_for_status()
        self.library = {"X-Fichero-Library-Path": quote(str(path), safe="/")}
        return self.library

    def lan_expected(self, sharing: bool) -> bool:
        return sharing and self.port is not None

    def lan_answers(self) -> bool:
        try:
            with httpx.Client(verify=self.lan_ssl(), base_url=f"https://{self.lan}:{self.port}", timeout=5) as client:
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
    home = base / "home"
    home.mkdir(parents=True, exist_ok=True)
    env = {key: value for key, value in os.environ.items() if not key.startswith("FICHERO_")}  # nothing of the owner's shell reaches a test engine
    env.update(
        HOME=str(home), FICHERO_MODEL_STORE_ROOT=str(base / "models"), FICHERO_BASE_PATH=str(base),
        FICHERO_BOOTSTRAP_TOKEN=token, FICHERO_TOKEN_DIR=str(base / "token"), FICHERO_UDS_PATH=str(sock),
        FICHERO_LAUNCH_SECRET_STDIN="1",
        FICHERO_FEATURE_TIER="dev", FICHERO_SKIP_DEFAULT_WORKFLOWS="1", FICHERO_ENV="test",
        PYTHONPATH=str(ENGINE_SRC))
    return env


def _popen(env: dict[str, str], launch_secret: str) -> subprocess.Popen:
    """The engine in its own process group, its launch secret piped in on stdin as the app does (one line, then closed).
    Its stdout and stderr go to `engine.log` under its base path, whose tail a failed start prints."""
    with open(Path(env["FICHERO_BASE_PATH"]) / "engine.log", "ab") as log:
        proc = subprocess.Popen([sys.executable, "-m", "fichero_server"], env=env, stdin=subprocess.PIPE, text=True,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
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

    def env_for(sharing_on: bool) -> dict[str, str]:
        env = _env(base, sock, token)
        if sharing_on:
            # As the app's spawn (EmbeddedBackendService+Spawn.swift, RemoteAccessConfig.launchEnvironment): the bind host is the access
            # material's (loopback), the LAN address rides FICHERO_LAN_HOST, and resolve_lan_bind_host asks for the acknowledgement
            # of a non-loopback address, which the app passes with the public URL (RemoteAccessConfig.swift:122).
            env.update(FICHERO_ALLOW_NON_LOOPBACK_BIND="I_UNDERSTAND_SHARED_SECRET_RISK", FICHERO_TCP_TLS_ALSO="1", FICHERO_TCP_PORT=str(port), FICHERO_LAN_HOST=lan, FICHERO_PUBLIC_BASE_URL=public,
                       FICHERO_TLS_CERTFILE=str(material.certificate_path), FICHERO_TLS_KEYFILE=str(material.key_path),
                       FICHERO_TLS_SPKI_HASH=material.spki_pin, FICHERO_BIND_HOST=material.bind_host)
        return env

    engine = _spawn("host", env_for(sharing), base, sock, port=port, lan=lan, spki_pin=material.spki_pin,
                    token=token, cert=Path(material.certificate_path))
    engine.env_for = env_for
    if multiuser:
        turn_multiuser_on(engine)
    return engine


def set_owner_password(host: Engine, password: str) -> None:
    """The product's own #5908 step: the owner chooses a password. While Multi-user is off the route takes only the app's start-up
    credential (a session is not honoured until Multi-user is on), so this is the ONE named use of it in the tests
    (`check_no_ambient_owner_in_tests.NAMED`, #5911)."""
    bootstrap_token = host.token
    with host._socket_client({"Authorization": f"Bearer {bootstrap_token}"}) as app:
        chosen = app.patch(f"/api/auth/users/{host.owner_id}", json={"password": password})
    assert chosen.status_code == 200, f"choosing the owner's password: {chosen.status_code} {chosen.text}"


def turn_multiuser_on(host: Engine, password: str = "owner-password-for-the-test") -> None:
    """The real path (#5908, #5914): the owner chooses a password through its route, then ONE PUT /api/pair/multiuser as the
    SIGNED-IN owner (never the start-up key). If the engine refuses the owner's own session here, that is a product finding
    (the app signs in the same way), reported as the failure below, not worked around."""
    host.sign_in_owner()  # the owner exists (first run) and holds a key
    set_owner_password(host, password)
    try:
        library = host.make_library()
        with host.uds as owner:
            on = owner.put("/api/pair/multiuser", json={"enabled": True}, headers=library)
    except httpx.HTTPStatusError as exc:
        pytest.fail(f"PRODUCT FINDING (#5908/#5914): the signed-in owner cannot create the library to turn Multi-user on: {exc}")
    if on.status_code in (401, 403):
        pytest.fail(f"PRODUCT FINDING (#5908/#5914): the signed-in owner's session is refused ({on.status_code}) while Multi-user is off, "
                    f"so the app cannot turn it on either: {on.text}")
    assert on.status_code == 200, f"turning Multi-user on: {on.status_code} {on.text}"
    host._multiuser = True


def turn_multiuser_off(host: Engine) -> None:
    with host.uds as owner:  # on: the owner's session is honoured
        off = owner.put("/api/pair/multiuser", json={"enabled": False}, headers=host.library)
        assert off.status_code == 200, f"turning Multi-user off: {off.status_code} {off.text}"
    host._multiuser = False


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


class Stream:
    """A server-sent-events stream read on a thread: `frames` fills as data arrives, `ended` is set when the server closes it."""

    def __init__(self, url: str, headers: dict[str, str], verify):
        import threading

        self.frames: list[str] = []
        self.lines: list[str] = []  # every non-empty line, keepalive comments too
        self.status: int | None = None
        self.ended = threading.Event()
        self.opened = threading.Event()
        self._thread = threading.Thread(target=self._read, args=(url, headers, verify), daemon=True)
        self._thread.start()

    def _read(self, url: str, headers: dict[str, str], verify) -> None:
        try:
            with httpx.Client(verify=verify, timeout=httpx.Timeout(60, read=60)) as client, \
                    client.stream("GET", url, headers=headers) as response:
                self.status = response.status_code
                self.opened.set()
                for line in response.iter_lines():
                    if line:
                        self.lines.append(line)
                    if line.startswith("data:"):
                        self.frames.append(line)
        except httpx.HTTPError:
            pass  # a closed or reset connection is an end
        finally:
            self.opened.set()
            self.ended.set()

    def wait_open(self, seconds: float = 15.0) -> None:
        assert self.opened.wait(seconds), "the stream never opened"
        assert self.status == 200, f"the stream answered {self.status}"

    def wait_line(self, seconds: float = 25.0) -> bool:
        """Any line at all: the engine sends a keepalive comment every 10 s on a quiet activity stream, so a live stream says
        something within that, whatever else is or is not emitted."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if self.lines:
                return True
            time.sleep(0.1)
        return False
