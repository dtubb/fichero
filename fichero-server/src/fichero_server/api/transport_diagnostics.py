"""Say which transport the engine bound, and who dials it (#4222).

`start_fichero_server.sh --uds` and the `Fichero (Dev Local)` scheme can disagree
about transport, and nothing said so. Only `.releaseEmbedded` resolves to UDS
(`EngineConfig+Launch.swift`); `Fichero (Dev Local)` is `.debugExternal`, which
is HTTPS on 127.0.0.1:8765. So the reasonable sequence — start the engine the
way the script's own help suggests, then run Dev Local — produced "Failed to
connect to the engine", a message identical to a genuinely down engine, a
wrong host, or a firewall.

Neither half is wrong. The defect is that nothing NAMED the disagreement. This
module is that naming: one pure function that turns the bound transport into
the three facts a person needs — what it bound, where, and what a client must
be set to in order to reach it.

Pure on purpose: the banner is testable without binding a socket, which is why
the launch paths format it here rather than inlining strings.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

# The Swift app pins this loopback endpoint fail-closed (#2376/#2370/#2538).
APP_LOOPBACK_PORT = 8765
APP_LOOPBACK_URL = f"https://127.0.0.1:{APP_LOOPBACK_PORT}"

TransportKind = Literal["uds", "https", "http"]


@dataclass(frozen=True)
class TransportBinding:
    """What the engine is actually listening on."""

    kind: TransportKind
    address: str

    @property
    def is_uds(self) -> bool:
        return self.kind == "uds"


def describe_transport(
    *,
    uds_path: str | None = None,
    host: str | None = None,
    port: int | None = None,
    tls: bool = False,
) -> TransportBinding:
    """Classify the bound transport. UDS wins when a socket path is set."""
    path = (uds_path or "").strip()
    if path:
        return TransportBinding(kind="uds", address=f"unix:{path}")
    if host is None or port is None:
        raise ValueError("A non-UDS binding needs both host and port")
    scheme = "https" if tls else "http"
    return TransportBinding(kind=scheme, address=f"{scheme}://{host}:{port}")


def transport_banner(binding: TransportBinding, *, uds_path: str | None = None) -> str:
    """Three facts: what it bound, where, and what a client must set.

    Written to be read by someone who has just seen "Failed to connect" and
    does not want to read Swift source to find out why.
    """
    lines = [f"Engine transport: {binding.kind.upper()} — listening on {binding.address}"]

    if binding.is_uds:
        socket_path = (uds_path or binding.address.removeprefix("unix:")).strip()
        lines += [
            "  Dialled by: every Mac Local scheme — they set "
            f"FICHERO_FORCE_UDS_PATH={socket_path} — and the Embedded/App Store "
            "builds, which spawn their own engine on a socket in their container",
            "  NOT dialled by: the iOS and iPad schemes. A simulator or device "
            f"cannot reach a socket in the Mac's container, so they use "
            f"{APP_LOOPBACK_URL}; restart without --uds to serve them.",
        ]
        return "\n".join(lines)

    lines.append(
        "  Dialled by: any scheme that leaves FICHERO_FORCE_UDS_PATH unset — the "
        "Local and iOS schemes, and any configuredRemote client"
    )
    lines.append(
        "  NOT dialled by: Fichero (Dev Local) — it SETS FICHERO_FORCE_UDS_PATH and "
        "dials that Unix socket, never this port. Nor the Release-embedded app. "
        "Restart with --uds=<path> for either."
    )
    if binding.kind == "http" and f":{APP_LOOPBACK_PORT}" in binding.address:
        # Plain HTTP on the pinned port is reachable by nothing the app runs.
        lines.append(
            f"  WARNING: the app pins {APP_LOOPBACK_URL} fail-closed (#2538), so this "
            "PLAIN HTTP listener is unreachable from every Fichero client."
        )
    return "\n".join(lines)


def log_transport_banner(
    *,
    uds_path: str | None = None,
    host: str | None = None,
    port: int | None = None,
    tls: bool = False,
) -> TransportBinding:
    """Describe + log in one call, and hand the binding back to the caller."""
    binding = describe_transport(uds_path=uds_path, host=host, port=port, tls=tls)
    for line in transport_banner(binding, uds_path=uds_path).splitlines():
        logger.info("%s", line)
    return binding


_FIRST_SEEN: set[str] = set()


def note_first_request(scope: dict) -> str | None:
    """Log `first request on <uds|https|http> after start` once per transport per engine life (#5868), so a repro can tell
    requests that never arrived from ones that arrived and failed. Says only the transport: no path, address, header or
    token. Returns the transport named the first time, else None."""
    server = scope.get("server")
    if server and server[1] is None:  # uvicorn gives a Unix socket (path, None); a TCP listener has a port
        transport = "uds"
    else:
        transport = "https" if scope.get("scheme") == "https" else "http"
    if transport in _FIRST_SEEN:
        return None
    _FIRST_SEEN.add(transport)
    logger.info("first request on %s after start", transport)
    return transport


_BOUND_TCP: list[str] | None = None


def note_tcp_listeners(addresses: list[str]) -> None:
    """The TCP addresses this engine really bound (empty: UDS only). Called once at start by `__main__`."""
    global _BOUND_TCP
    _BOUND_TCP = list(addresses)


def tcp_listeners() -> list[str] | None:
    """What `note_tcp_listeners` recorded, or None when this engine did not say (a dev or test engine started another way)."""
    return None if _BOUND_TCP is None else list(_BOUND_TCP)


def network_listener_gap(public_base_url: str, bound: list[str] | None) -> str | None:
    """Why a pairing link for `public_base_url` would name an address nothing listens on, in words, else None
    (`sharing.link-names-a-listener`). A `.ts.net` address is served by Tailscale to the loopback port, so loopback is
    enough there; anything else needs a non-loopback listener. An engine that recorded nothing is not judged."""
    from urllib.parse import urlparse

    host = (urlparse(public_base_url).hostname or "").lower() if public_base_url else ""
    if not host or bound is None or host.endswith(".ts.net"):
        return None
    if any(not (a.startswith("127.") or a in ("::1", "localhost")) for a in bound):
        return None
    return (f"Sharing is on at {host}, but this Mac is not listening there yet: 'This network' is off, so no device "
            "could connect. Turn it on, or share over Tailscale.")
