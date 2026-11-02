"""The `sharing` block of `GET /api/health` (`sharing.health-reports-sharing`, sharing-two-macs.md Step 1.4).

Health is polled constantly, so the two answers that start a Tailscale process (the tailnet name and who holds the
forward) are kept for `_TTL` seconds. Everything else is an environment or settings read.
"""
from __future__ import annotations

import os
import time
from urllib.parse import urlparse

_TTL = 30.0  # ponytail: a fixed 30 s; a changed tailnet shows within it. Event-driven if a pane needs it sooner.
_cache: dict[str, tuple[float, object]] = {}


def _kept(key: str, ask):
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    value = ask()
    _cache[key] = (now, value)
    return value


def _certificate_names() -> list[str]:
    """The names the serving certificate carries, or [] when there is none or it cannot be read."""
    path = (os.environ.get("FICHERO_TLS_CERTFILE") or "").strip()
    if not path:
        return []
    try:
        from cryptography import x509

        with open(path, "rb") as handle:
            cert = x509.load_pem_x509_certificate(handle.read())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        return [str(name.value) for name in san]
    except Exception:  # noqa: BLE001 -- health must answer; an unreadable certificate is "no names"
        return []


def sharing_report(app_db):
    from fichero_server.models import SharingAddress, SharingHealth
    from fichero_server.security import bind_host, tailscale_serve
    from fichero_server.security.multiuser import multiuser_enabled

    port = bind_host.listen_port()
    lan_host = (os.environ.get("FICHERO_LAN_HOST") or "").strip()
    listeners = [f"127.0.0.1:{port}"] + ([f"{lan_host}:{port}"] if lan_host else [])
    on = tailscale_serve.sharing_on()
    forward = _kept("forward", lambda: tailscale_serve.forward_state(port))
    tailnet = _kept("tailnet", lambda: tailscale_serve.detected_tailnet_url() or "") if on else ""
    try:
        lan_ip = bind_host.primary_lan_ip() or ""
    except OSError:
        lan_ip = ""
    public = (os.environ.get("FICHERO_PUBLIC_BASE_URL") or "").strip()

    addresses: list[SharingAddress] = []
    seen: set[str] = set()

    def add(kind, url, listening):
        if url and url not in seen:
            seen.add(url)
            addresses.append(SharingAddress(kind=kind, url=url, listening=listening))

    if tailnet:
        add("tailnet", tailnet, forward == "ours")  # Tailscale reaches the loopback listener only through our forward
    if public and not (urlparse(public).hostname or "").endswith(".ts.net"):
        host = urlparse(public).hostname or ""
        add("local-name" if host.endswith(".local") else "lan", public, bool(on and lan_host))
    if lan_ip and on:
        add("lan", f"https://{lan_ip}:{port}", bool(lan_host == lan_ip))

    return SharingHealth(
        on=on,
        listeners=listeners,
        addresses=addresses,
        certificate_names=_certificate_names(),
        tailnet_forward=forward,
        multiuser=multiuser_enabled(),
        paired_devices=sum(1 for d in app_db.list_devices() if not d.revoked),
    )
