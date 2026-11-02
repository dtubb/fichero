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


def _facts():
    """What the rows and the health block both read: sharing on, the listeners, the forward, the tailnet name."""
    from fichero_server.security import bind_host, tailscale_serve

    port = bind_host.listen_port()
    lan_host = (os.environ.get("FICHERO_LAN_HOST") or "").strip()
    on = tailscale_serve.sharing_on()
    forward = _kept("forward", lambda: tailscale_serve.forward_state(port))
    tailnet = _kept("tailnet", lambda: tailscale_serve.detected_tailnet_url() or "") if on else ""
    listeners = [f"127.0.0.1:{port}"] + ([f"{lan_host}:{port}"] if lan_host else [])
    return port, lan_host, on, forward, tailnet, listeners


def _tailnet_reason(forward: str, port: int) -> str | None:
    from fichero_server.security import tailscale_serve

    if forward == "ours":
        return None
    if forward == "foreign":
        conflict = tailscale_serve.forward_conflict(port)
        if conflict:
            return (f"Port {port} on your tailnet already goes to {conflict['holds']}, not to Fichero. "
                    f"Run `{conflict['free_with']}`, then turn Sharing off and on.")
        return f"Port {port} on your tailnet goes to another service, not to Fichero."
    if forward == "unknown":
        return "This engine could not ask Tailscale whether it forwards to Fichero (a sandboxed build cannot run its command)."
    return "The Tailscale forward is not made yet: turn Sharing off and on."


def address_rows(facts=None) -> list:
    """Every address this Mac can be reached at, in the order to try (`sharing.address-choice`): the tailnet name when its
    forward is Fichero's own, then the `.local` name, then the LAN IP; a tailnet row that cannot work goes last with why.
    Never loopback. The host cannot see client isolation, so a `.local` or IP row says "listening", never "works"."""
    from fichero_server.models import SharingAddress
    from fichero_server.security import bind_host

    port, lan_host, on, forward, tailnet, _ = facts or _facts()
    if not on:
        return []
    try:
        lan_ip = bind_host.primary_lan_ip() or ""
    except OSError:
        lan_ip = ""
    public = (os.environ.get("FICHERO_PUBLIC_BASE_URL") or "").strip()
    public_host = urlparse(public).hostname or ""

    first: list[SharingAddress] = []
    last: list[SharingAddress] = []
    if tailnet:
        host = urlparse(tailnet).hostname or tailnet
        reason = _tailnet_reason(forward, port)
        row = SharingAddress(kind="tailnet", url=tailnet, listening=forward == "ours", reason=reason,
                             label=f"Tailscale, {host}: works from anywhere your Tailscale is on")
        (first if reason is None else last).append(row)
    if public and not public_host.endswith(".ts.net"):
        local = public_host.endswith(".local")
        first.append(SharingAddress(
            kind="local-name" if local else "lan", url=public, listening=bool(lan_host),
            label=f"This network, {public_host}: works only on the same network, when it lets Macs find each other"))
    if lan_ip:
        first.append(SharingAddress(kind="lan", url=f"https://{lan_ip}:{port}", listening=lan_host == lan_ip,
                                    label=f"This network, {lan_ip}: works only on the same network"))
    rows, seen = [], set()
    for row in first + last:
        if row.url not in seen:
            seen.add(row.url)
            rows.append(row)
    return rows


def sharing_report(app_db):
    from fichero_server.models import SharingHealth
    from fichero_server.security.multiuser import multiuser_enabled

    facts = _facts()
    _, _, on, forward, _, listeners = facts
    return SharingHealth(
        on=on,
        listeners=listeners,
        addresses=address_rows(facts),
        certificate_names=_certificate_names(),
        tailnet_forward=forward,
        multiuser=multiuser_enabled(),
        paired_devices=sum(1 for d in app_db.list_devices() if not d.revoked),
    )
