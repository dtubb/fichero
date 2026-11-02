"""`fichero devices pair <link>`: pair the CLI as a revocable device of a host (`sharing.cli-pairs-a-device`).

A pairing link is the text a phone scans (`fichero://pair?payload=<base64 JSON>`). This module checks it by the app's
rules (#5891), redeems it at `POST /api/pair` and keeps the device token per engine in an owner-only file. The token is
never printed and never returned to a caller that prints.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import getpass
import hashlib
import json
import os
import socket
import ssl
import stat
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import httpx

from fichero_cli.client import _TOKEN_PATH, FicheroError, engine_key

DEVICES_PATH = _TOKEN_PATH.with_name("paired-devices.json")
PAIR_NEXT_HEADER = "x-fichero-pair-next"  # what the host asks the person for next (api/routes/auth/pairing.py)
NEXT_PERSON = "person-required"
NEXT_NEW_PASSWORD = "choose-password"
_PAIR_HOSTS = {"fichero.app"}  # the https universal link the app also accepts


@dataclass(frozen=True)
class PairLink:
    api_url: str
    code: str
    spki: str | None
    alt_urls: tuple[str, ...] = ()  # the host's other addresses, in order (`sharing.link-carries-every-address`); old links have none


def parse_link(text: str) -> PairLink:
    """The link's host, code and pin. Anything that is not a pairing link is refused in words."""
    raw = "".join((text or "").split())
    url = urlparse(raw)
    is_link = (url.scheme == "fichero" and url.netloc == "pair") or (
        url.scheme == "https" and url.hostname in _PAIR_HOSTS and url.path.rstrip("/") == "/pair"
    )
    payload = (parse_qs(url.query).get("payload") or [""])[0]
    if not is_link or not payload:
        raise FicheroError("That is not a Fichero pairing link (expected fichero://pair?payload=…).")
    try:
        data = json.loads(base64.b64decode(payload + "=" * (-len(payload) % 4), altchars=b"-_"))
        api_url, code = str(data["api_url"]).strip(), str(data["pair_code"]).strip()
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise FicheroError("The pairing link is damaged: ask the host for a new one.") from exc
    spki = data.get("spki") or None
    alts = data.get("alt_urls")
    alt_urls = tuple(str(u).rstrip("/") for u in alts if isinstance(u, str) and u.strip()) if isinstance(alts, list) else ()
    return PairLink(api_url=api_url.rstrip("/"), code=code, spki=str(spki) if spki else None, alt_urls=alt_urls)


def _payload_of(text: str) -> bytes:
    """The link's decoded JSON payload bytes (the parser's own reading)."""
    url = urlparse("".join((text or "").split()))
    payload = (parse_qs(url.query).get("payload") or [""])[0]
    return base64.b64decode(payload + "=" * (-len(payload) % 4), altchars=b"-_")


MAX_LINK_ADDRESSES = 3  # ponytail: three is what the 5-second-each try budget allows (a dead link fails in <= 15 s)
QR_PAYLOAD_LIMIT = 400  # characters of encoded payload a phone camera reads reliably at QR level M (`sharing.ios-qr-payload-size`)


def alt_urls_from(rows: list[dict], *, chosen: str, sharing_address: str | None) -> list[str]:
    """The addresses to carry beside the chosen one, from the engine's own list (`GET /api/pair/addresses`), in its order:
    only rows with nothing against them, never loopback, none twice, at most `MAX_LINK_ADDRESSES` in all. A tailnet row is the
    origin the engine reports, so it takes the sharing port (`tailnet_link_url`)."""
    chosen = chosen.rstrip("/")
    out: list[str] = []
    for row in rows or []:
        url = str(row.get("url") or "").strip().rstrip("/")
        host = (urlparse(url).hostname or "").lower()
        if not url or row.get("reason") or not row.get("listening", True) or host in ("localhost", "::1") or host.startswith("127."):
            continue
        if row.get("kind") == "tailnet":
            url = tailnet_link_url(url, sharing_address)
        if url != chosen and url not in out:
            out.append(url)
    return out[: MAX_LINK_ADDRESSES - 1]


def invite_link(*, api_url: str, code: str, spki: str | None, expires_at: str | None, library_path: str | None,
                alt_urls: list[str] | tuple[str, ...] = (), for_qr: bool = False) -> str:
    """The pairing link the app, the phone and `devices pair` all redeem (`sharing.cli-mints-a-link`): the app's own shape
    (`RemoteClientPairing.inviteLinkString`: `fichero://pair?payload=<base64 JSON>`), keys sorted so the same link reads
    the same from every machine. The pin rides only with an address that serves its own certificate; a `.ts.net` name
    is system trust and carries none (`_is_public_ca`). Absent values leave their key out, as the app's encoder does."""
    payload: dict[str, object] = {"v": 1, "api_url": api_url.rstrip("/"), "pair_code": code}
    if expires_at:
        payload["expires_at"] = expires_at
    alts = [u.rstrip("/") for u in alt_urls if u and u.rstrip("/") != api_url.rstrip("/")]
    # The one pin is the engine's key, whatever the name; a `.ts.net` address is system trust and needs none, so the pin rides
    # only when some carried address serves the engine's own certificate.
    if spki and not all(_is_public_ca(urlparse(u).hostname or "") for u in [api_url, *alts]):
        payload["spki"] = spki
    if library_path and not for_qr:  # the QR leaves it out: the guest asks the host for it (`sharing.ios-qr-payload-size`)
        payload["library_path"] = library_path

    def encode() -> str:
        return base64.b64encode(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).decode()

    if alts:
        payload["alt_urls"] = alts
    while for_qr and alts and len(encode()) > QR_PAYLOAD_LIMIT:
        alts.pop()  # the chosen address is never the one dropped; `payload` holds this same list
        if not alts:
            del payload["alt_urls"]
    encoded = encode()
    # Percent-encode as the app does: an unquoted `+` in the query reads back as a space and the link is "damaged".
    return f"fichero://pair?payload={quote(encoded, safe='')}"


def tailnet_link_url(tailnet_url: str, sharing_address: str | None, default_port: int = 8765) -> str:
    """The tailnet address a LINK carries: the engine reports the origin (`https://<name>.ts.net`, no port) while the
    forward is `--https=<sharing port>`; a link without the port names 443 and never connects (review 2026-10-31, H3)."""
    tail = urlparse(tailnet_url.strip())
    if tail.port:
        return tailnet_url.strip().rstrip("/")
    port = urlparse(sharing_address or "").port or default_port
    return f"https://{tail.hostname}:{port}"


def _is_public_ca(host: str) -> bool:
    return host.lower().endswith(".ts.net")  # tailscale serve: system trust, nothing of ours to pin (#5891)


def _pin_matches(pin: str, der: bytes) -> bool:
    """`pin` is the raw SPKI (base64), `sha256/<base64 digest>` or a bare 32-byte digest, as the app accepts them."""
    pin = "".join(pin.split())
    digest = hashlib.sha256(der).digest()
    try:
        if pin.startswith("sha256/"):
            return base64.b64decode(pin[7:], validate=True) == digest
        raw = base64.b64decode(pin, validate=True)
    except (ValueError, binascii.Error):
        return False
    return raw == digest or raw == der


def served_spki_der(host: str, port: int) -> bytes:
    """The SubjectPublicKeyInfo of the certificate the host serves (read without trusting it; the pin decides)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    pem = ssl.get_server_certificate((host, port), timeout=5)
    cert = x509.load_pem_x509_certificate(pem.encode("ascii"))
    return cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def check_trust(api_url: str, spki: str | None, *, fetch_der: Callable[[str, int], bytes] = served_spki_der) -> None:
    """Refuse, in words, a host this device may not trust. Nothing is sent before this passes."""
    url = urlparse(api_url)
    if url.scheme != "https" or not url.hostname:
        raise FicheroError(
            "Refusing to pair over plain http: the link must name an https host. Ask the host for a new link."
        )
    if _is_public_ca(url.hostname):
        return
    if url.hostname.startswith("100."):  # Tailscale's certificate names the MagicDNS name only, never the number
        raise FicheroError("Tailscale addresses work by name, not by number. Ask for a new link.")
    if not spki:
        raise FicheroError(
            f"The link carries no certificate pin for {url.hostname}, and that host serves its own certificate. "
            "Refusing to pair; ask the host for a new link."
        )
    try:
        der = fetch_der(url.hostname, url.port or 443)
    except OSError as exc:
        raise FicheroError(f"Could not reach {url.hostname} to check its certificate: {exc}") from exc
    if not _pin_matches(spki, der):
        raise FicheroError(
            f"{url.hostname} presents a certificate that does not match the link's pin. "
            "Refusing to pair: it may not be the host the link came from."
        )


# -- the per-engine device store -------------------------------------------
def _read_store(*, strict: bool = True) -> dict:
    """The store. `strict` (reads that hand out a token) refuses a file that is not owner-only; a writer reads it
    anyway so one wrong mode never wipes the other engines' entries (it rewrites the file 0600)."""
    try:
        if strict and (DEVICES_PATH.stat().st_mode & 0o777) != 0o600:
            return {}
        data = json.loads(DEVICES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_store(store: dict) -> None:
    DEVICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DEVICES_PATH.with_name(DEVICES_PATH.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(store))
    os.chmod(tmp, 0o600)  # a stale tmp keeps its mode through O_CREAT
    os.replace(tmp, DEVICES_PATH)  # atomic: a crash leaves the old file, never half a token


def write_owner_only(path: Path, text: str) -> None:
    """Write `text` to `path` readable by this user only (a pairing link is a one-time secret while it lives).

    The bytes never touch a file anyone else can read: a fresh temp file beside the target is created
    O_CREAT|O_EXCL|O_NOFOLLOW at mode 0600 (never a mode fixed up after the write), then moved over the target. The
    target may only be replaced when it does not exist or is the caller's own regular file; a symlink, a directory or
    another user's file is refused in words (review 2026-10-31: a shared /tmp path could be pre-created by someone else)."""
    path = Path(path)
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if stat.S_ISLNK(existing.st_mode):
            raise FicheroError(f"{path} is a symlink; refusing to write the link through it. Name a new file.")
        if not stat.S_ISREG(existing.st_mode):
            raise FicheroError(f"{path} is not a regular file; name a new file for the link.")
        if existing.st_uid != os.getuid():
            raise FicheroError(f"{path} belongs to another user; name a file of your own for the link.")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def device_token(engine: str | None) -> str | None:
    """The token this CLI was paired with for `engine`, if any."""
    entry = _read_store().get(engine or "")
    token = entry.get("device_token") if isinstance(entry, dict) else None
    return token.strip() if isinstance(token, str) and token.strip() else None


def forget(host: str) -> int:
    """Drop the local token(s) for `host` (a name, `name:port` or the engine key). Returns how many were dropped."""
    store = _read_store(strict=False)
    gone = [key for key, entry in store.items()
            if host in (key, urlparse(key).hostname, (entry or {}).get("host"))]
    for key in gone:
        del store[key]
    if gone:
        _write_store(store)
    return len(gone)


def pinned_context(base_url: str) -> ssl.SSLContext | None:
    """A TLS context that trusts exactly the certificate whose pin was stored at pairing; None when none was."""
    entry = _read_store().get(engine_key(base_url, None))
    spki = entry.get("spki") if isinstance(entry, dict) else None
    return trust_served(base_url, spki) if spki else None


def trust_served(base_url: str, spki: str) -> ssl.SSLContext:
    """Trust exactly the certificate `base_url` serves now, if its key matches `spki`; else refuse."""
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization

    url = urlparse(base_url)
    pem = ssl.get_server_certificate((url.hostname, url.port or 443), timeout=5)
    key = x509.load_pem_x509_certificate(pem.encode("ascii")).public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if not _pin_matches(spki, key):
        raise FicheroError(f"{url.hostname} does not match the pin it was paired with. Refusing to connect.")
    context = ssl.create_default_context(cadata=pem)
    context.check_hostname = False  # the pin, not the name, is the identity of a self-signed host
    # Python 3.13 turns VERIFY_X509_STRICT on, which can refuse a self-signed leaf used as its own anchor; the pin
    # already decided identity above. VERIFY on the M4 run (Python version there).
    context.verify_flags &= ~ssl.VERIFY_X509_STRICT
    return context


# -- redeeming -------------------------------------------------------------
def _open_client(api_url: str, uds: str | None, spki: str | None) -> httpx.Client:
    """The socket, or the host (pinned when it serves its own certificate, system trust for a `.ts.net` name)."""
    if uds:
        return httpx.Client(base_url="http://fichero-app", transport=httpx.HTTPTransport(uds=uds), timeout=30)
    return httpx.Client(base_url=api_url, verify=trust_served(api_url, spki) if spki else True, timeout=30)


def _ask_person() -> tuple[str, str]:
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise FicheroError(
            "This host uses Multi-user, so the device must sign in as a person, and there is no terminal to ask on. "
            "Run `fichero devices pair` in a terminal. The username and password are never taken from arguments "
            "or the environment."
        )
    return input("Username: ").strip(), getpass.getpass("Password: ")


def _ask_new_password() -> str:
    """An invitation to a NEW person: they choose their own password here (the host never sees or sets it)."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        raise FicheroError(
            "This invitation makes your account, so you choose a password, and there is no terminal to ask on. "
            "Run `fichero devices pair` in a terminal. The password is never taken from arguments or the environment."
        )
    first = getpass.getpass("Choose a password for your account: ")
    if first != getpass.getpass("Again: "):
        raise FicheroError("The two passwords differ: nothing was paired. Run the command again.")
    return first


ATTEMPT_SECONDS = 5.0  # per address: lookup + connect + TLS + the first byte of an unauthenticated health call


def _label(api_url: str) -> str:
    host = urlparse(api_url).hostname or api_url
    return f"Tailscale ({host})" if _is_public_ca(host) else host


def _health_probe(api_url: str, spki: str | None) -> str | None:
    """None when the host answered `GET /api/health` within the budget (any HTTP answer counts: the Mac is there), else why not."""
    try:
        with _open_client(api_url, None, spki) as http:
            http.get("/api/health", timeout=ATTEMPT_SECONDS)
        return None
    except httpx.TimeoutException:
        if _is_public_ca(urlparse(api_url).hostname or ""):
            return "no answer in 5 s: is Tailscale on this Mac?"
        return "no answer in 5 s: the network may keep devices apart"
    except httpx.ConnectError as exc:
        text = f"{exc} {exc.__cause__ or ''}".lower()
        if "certificate" in text or "ssl" in text:
            return "its certificate was refused: ask the host for a new link"
        if "nodename" in text or "name or service" in text or "name resolution" in text or "getaddrinfo" in text:
            return "this Mac cannot find that name on this network"
        return "Fichero isn't listening there: turn Sharing off and on on the host"
    except httpx.HTTPError as exc:
        return f"it could not be reached ({type(exc).__name__})"


def reach(link: PairLink, *, probe: Callable[[str, str | None], str | None],
          fetch_der: Callable[[str, int], bytes]) -> tuple[str, list[str]]:
    """Try the link's addresses in its order, one after another (a race hides which failed and why), and stop at the first that
    passes the trust check and answers (`sharing.client-tries-every-address`). Returns that address and the sentences to show;
    raises with every attempt named when none answers. The code is sent only after this, to the address that answered."""
    failed: list[tuple[str, str]] = []
    for url in [link.api_url, *link.alt_urls][:MAX_LINK_ADDRESSES]:
        try:
            check_trust(url, link.spki, fetch_der=fetch_der)
            why = probe(url, None if _is_public_ca(urlparse(url).hostname or "") else link.spki)
        except FicheroError as exc:
            why = str(exc)
        if why is None:
            notes = [f"Connected through {_label(url)}."]
            notes += [f"The {_label(bad)} address did not answer: {reason}." for bad, reason in failed]
            return url, notes
        failed.append((url, why.rstrip(".")))
    first = urlparse(link.api_url).hostname or link.api_url
    tried = " · ".join(f"{_label(bad)}: {reason}" for bad, reason in failed)
    raise FicheroError(f"Could not reach {first}. Tried {tried}.")


def pair(
    link_text: str,
    *,
    device_name: str | None = None,
    uds: str | None = None,
    fetch_der: Callable[[str, int], bytes] | None = None,
    ask_person: Callable[[], tuple[str, str]] = _ask_person,
    ask_new_password: Callable[[], str] = _ask_new_password,
    probe: Callable[[str, str | None], str | None] | None = None,
) -> dict[str, Any]:
    """Redeem the link and store the device token. Returns the device id, name, host and (for a link with several addresses)
    the notes on which address answered; never the token."""
    link = parse_link(link_text)
    notes: list[str] = []
    if link.alt_urls and not uds:  # a link with several addresses: try them in turn, 5 s each, and pair at the first that answers
        chosen, notes = reach(link, probe=probe or _health_probe, fetch_der=fetch_der or served_spki_der)
        link = PairLink(api_url=chosen, code=link.code, spki=link.spki)
    else:
        check_trust(link.api_url, link.spki, fetch_der=fetch_der or served_spki_der)
    host = urlparse(link.api_url).hostname or link.api_url
    name = (device_name or f"{socket.gethostname()} (fichero CLI)").strip()
    pin = None if _is_public_ca(host) else link.spki
    body: dict[str, str] = {"code": link.code, "device_name": name}
    try:
        with _open_client(link.api_url, uds, pin) as http:
            reply = http.post("/api/pair", json=body)
            next_step = reply.headers.get(PAIR_NEXT_HEADER)  # the host's typed hint, never its prose
            if reply.status_code == 401 and next_step == NEXT_PERSON:
                username, password = ask_person()
                reply = http.post("/api/pair", json={**body, "username": username, "password": password})
            elif reply.status_code in (400, 422) and next_step == NEXT_NEW_PASSWORD:  # the host answers 400 (its own refusal of a missing or short password)
                reply = http.post("/api/pair", json={**body, "new_password": ask_new_password()})
    except httpx.ConnectError as exc:
        text = f"{exc} {exc.__cause__ or ''}".lower()
        if "certificate" in text or "ssl" in text:
            raise FicheroError(
                f"{host}'s certificate was refused (expired or replaced) though its key matched the link. "
                "Ask the host for a new pairing link."
            ) from exc
        raise FicheroError(f"Cannot connect to {host}: {exc}") from exc
    if reply.status_code != 200:
        try:
            detail = reply.json().get("detail", "")
        except ValueError:
            detail = ""
        raise FicheroError(f"{host} refused the pairing ({reply.status_code}): {detail}", status_code=reply.status_code)
    data = reply.json()
    key = engine_key(None, uds) if uds else engine_key(link.api_url, None)
    store = _read_store(strict=False)
    store[key] = {
        "device_token": data["device_token"],
        "device_id": data["device_id"],
        "name": name,
        "host": host,
        "spki": pin,
    }
    _write_store(store)
    done: dict[str, Any] = {"device_id": data["device_id"], "name": name, "host": host}
    if notes:  # only a link with several addresses has any: which answered and why the others did not
        done["notes"] = notes
    return done
