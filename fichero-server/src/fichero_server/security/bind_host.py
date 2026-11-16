"""Bind-host resolution for the Fichero engine.

The supported remote-access model is loopback binding plus an explicit HTTPS
transport or SSH forwarding. The shared bootstrap token is not an internet-
facing auth boundary, so non-loopback binding must stay an explicit,
risk-acknowledged escape hatch rather than the default path.
"""

from __future__ import annotations

import ipaddress
import socket
import warnings
from collections.abc import Mapping
from os import environ

DEFAULT_BIND_HOST = "127.0.0.1"
PUBLIC_URL_ENV = "FICHERO_PUBLIC_BASE_URL"
LAN_BIND_HOST_ENV = "FICHERO_LAN_HOST"
NON_LOOPBACK_BIND_ACK_ENV = "FICHERO_ALLOW_NON_LOOPBACK_BIND"
NON_LOOPBACK_BIND_ACK_VALUE = "I_UNDERSTAND_SHARED_SECRET_RISK"


SHIPPED_PORT = 8765
TCP_PORT_ENV = "FICHERO_TCP_PORT"


DEV_TEST_ENVS = frozenset({"development", "test"})


def is_dev_or_test(env: Mapping[str, str] | None = None) -> bool:
    """Whether the environment says dev or test EXPLICITLY (`FICHERO_ENV`); unset is not (#5895)."""
    source = env if env is not None else environ
    return (source.get("FICHERO_ENV") or "").strip().lower() in DEV_TEST_ENVS


def listen_port(env: Mapping[str, str] | None = None) -> int:
    """The engine's TCP port (#5895): 8765, the shipped port, unless `FICHERO_TCP_PORT` names another AND the
    environment says dev or test EXPLICITLY (`FICHERO_ENV` is `development` or `test`). A Release app that sets
    nothing keeps 8765. A value that is not a port number refuses to start, in words. One place, so the listener,
    its start-up check, the Bonjour advert, the Tailscale forward and the remote-backend status cannot disagree."""
    source = env if env is not None else environ
    raw = (source.get(TCP_PORT_ENV) or "").strip()
    if not raw or not is_dev_or_test(source):
        return SHIPPED_PORT
    if not raw.isdigit() or not 1 <= int(raw) <= 65535:
        raise SystemExit(f"{TCP_PORT_ENV}={raw!r} is not a port number (1 to 65535); refusing to start.")
    return int(raw)


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def resolve_bind_host(
    env: Mapping[str, str] | None = None,
    host: str | None = None,
) -> str:
    """Return the configured bind host, enforcing the private-bind guard.

    ``host`` overrides the environment when passed explicitly. When neither is
    set, the engine stays on loopback.
    """

    source = env if env is not None else environ
    raw_host = host if host is not None else source.get("FICHERO_BIND_HOST")
    public_base_url = (source.get(PUBLIC_URL_ENV) or "").strip()
    if host is None and public_base_url:
        return DEFAULT_BIND_HOST
    resolved = (raw_host or DEFAULT_BIND_HOST).strip()

    if resolved == "0.0.0.0":
        if source.get(NON_LOOPBACK_BIND_ACK_ENV) != NON_LOOPBACK_BIND_ACK_VALUE:
            raise ValueError(
                "FICHERO_BIND_HOST=0.0.0.0 is not allowed without the shared-"
                "secret risk acknowledgement. Set "
                f"{NON_LOOPBACK_BIND_ACK_ENV}={NON_LOOPBACK_BIND_ACK_VALUE} to "
                "bind all interfaces."
            )

    if resolved == "::":
        raise ValueError(
            "FICHERO_BIND_HOST=:: is not allowed. Keep the engine on ::1 or "
            "127.0.0.1 and use the explicit HTTPS remote-access launch path "
            "or SSH loopback forwarding."
        )

    if not _is_loopback_host(resolved):
        if source.get(NON_LOOPBACK_BIND_ACK_ENV) != NON_LOOPBACK_BIND_ACK_VALUE:
            raise ValueError(
                f"FICHERO_BIND_HOST={resolved!r} is non-loopback. "
                "The supported remote model is 127.0.0.1 plus an explicit HTTPS "
                "remote-access transport or SSH loopback forwarding. To override "
                "deliberately, set "
                f"{NON_LOOPBACK_BIND_ACK_ENV}={NON_LOOPBACK_BIND_ACK_VALUE}."
            )
        warnings.warn(
            "WARNING: binding Fichero to a non-loopback host. The shared "
            "bootstrap token is not an internet-facing auth boundary; prefer "
            "127.0.0.1 plus an explicit HTTPS remote-access transport or SSH "
            "loopback forwarding.",
            RuntimeWarning,
            stacklevel=2,
        )

    return resolved


def resolve_lan_bind_host(
    env: Mapping[str, str] | None = None,
    host: str | None = None,
) -> str | None:
    """Return one explicit LAN listener host, or ``None`` when disabled."""

    source = env if env is not None else environ
    raw_host = host if host is not None else source.get(LAN_BIND_HOST_ENV)
    if raw_host is None or not raw_host.strip():
        return None
    if raw_host.strip() == "0.0.0.0":
        raise ValueError(
            f"{LAN_BIND_HOST_ENV}=0.0.0.0 is not allowed. Use one explicit LAN address."
        )

    resolved = resolve_bind_host(source, host=raw_host)
    if _is_loopback_host(resolved):
        raise ValueError(
            f"{LAN_BIND_HOST_ENV} must be a non-loopback address when set."
        )
    return resolved


def primary_lan_ip() -> str:
    """The machine's outbound-interface IPv4, found without any DNS.

    The sandboxed engine cannot getaddrinfo a Bonjour name (errno 8, live
    2026-08-27), so binding to "macbook-pro-m1.local" failed. A connected
    UDP socket names the primary interface without sending a packet.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 1))  # TEST-NET-1: never routed, never sent
        return probe.getsockname()[0]
    finally:
        probe.close()


# RFC 1918 and IPv4 link-local: the networks a Mac's own interfaces (Wi-Fi, Ethernet, the Thunderbolt bridge) use at home
# or in an office. Not 100.64/10 (Tailscale reaches the loopback port through `tailscale serve`), never a public address.
PRIVATE_LAN_NETWORKS = tuple(
    ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16")
)


def is_private_lan_address(host: str) -> bool:
    """Whether ``host`` is an IPv4 address of a private network (#6383): what a LAN listener may bind beside the named one."""
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False
    return addr.version == 4 and any(addr in net for net in PRIVATE_LAN_NETWORKS)


def _interface_ipv4s() -> list[str]:
    """The IPv4 address of every interface that is up, read with getifaddrs (no DNS, no subprocess: the sandboxed engine
    has neither, see `primary_lan_ip`). macOS layout of `struct sockaddr`; elsewhere nothing."""
    import ctypes
    import ctypes.util
    import sys

    if sys.platform != "darwin":
        return []

    class Sockaddr(ctypes.Structure):
        _fields_ = [("sa_len", ctypes.c_uint8), ("sa_family", ctypes.c_uint8), ("sa_data", ctypes.c_uint8 * 14)]

    class Ifaddrs(ctypes.Structure):
        pass

    Ifaddrs._fields_ = [
        ("ifa_next", ctypes.POINTER(Ifaddrs)), ("ifa_name", ctypes.c_char_p), ("ifa_flags", ctypes.c_uint),
        ("ifa_addr", ctypes.POINTER(Sockaddr)), ("ifa_netmask", ctypes.POINTER(Sockaddr)),
        ("ifa_dstaddr", ctypes.POINTER(Sockaddr)), ("ifa_data", ctypes.c_void_p),
    ]
    libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    head = ctypes.POINTER(Ifaddrs)()
    if libc.getifaddrs(ctypes.byref(head)) != 0:
        return []
    found: list[str] = []
    try:
        node = head
        while node:
            entry = node.contents
            if entry.ifa_addr and entry.ifa_flags & 0x1 and entry.ifa_addr.contents.sa_family == socket.AF_INET:
                found.append(socket.inet_ntoa(bytes(entry.ifa_addr.contents.sa_data[2:6])))
            node = entry.ifa_next
    finally:
        libc.freeifaddrs(head)
    return found


def private_interface_ips(addresses: list[str] | None = None) -> list[str]:
    """This Mac's private interface addresses (#6383, owner ruling 2026-11-07, extends #5897): the Thunderbolt bridge's
    10.10.10.x, a second Ethernet port. Bound beside the named LAN address while Sharing is on; never 0.0.0.0, never a
    public or loopback address. ``addresses`` stands in for the interfaces in tests."""
    source = _interface_ipv4s() if addresses is None else addresses
    return list(dict.fromkeys(a for a in source if is_private_lan_address(a)))


def port_in_use_message(port: int) -> str:
    """The sentence for a port an older engine still holds (`sharing.stale-server-holding-the-port`): what the app and the
    Sharing pane show instead of "engine failed to start"."""
    return f"Another copy of Fichero's server is using port {port}. Quit it (Activity Monitor › Fichero Server) or restart this Mac."
