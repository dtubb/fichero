"""Shared SSRF URL validation helpers."""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlparse

_SANDBOX_BLOCKED_SCHEMES = frozenset(
    [
        "file",
        "ftp",
        "ftps",
        "s3",
        "smb",
        "ssh",
        "telnet",
        "gopher",
        "ldap",
        "ldaps",
    ]
)

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("::ffff:0:0/96"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

_CLOUD_METADATA_HOSTS = frozenset(
    [
        "169.254.169.254",
        "metadata.google.internal",
        "metadata.googleapis.com",
        "169.254.170.2",
        "169.254.170.1",
    ]
)


async def is_internal_ip(hostname: str | None) -> bool:
    if not hostname:
        return False

    if hostname.lower() in _CLOUD_METADATA_HOSTS:
        return True

    try:
        addr = ipaddress.ip_address(hostname)
        return any(addr in network for network in _BLOCKED_NETWORKS)
    except ValueError:
        pass

    try:
        addrs = await asyncio.to_thread(socket.getaddrinfo, hostname, None)
        for addr_info in addrs:
            ip_str = addr_info[4][0]
            try:
                ip = ipaddress.ip_address(ip_str)
            except ValueError:
                continue
            if any(ip in network for network in _BLOCKED_NETWORKS):
                return True
    except (socket.gaierror, socket.herror):
        pass

    return False


async def is_safe_url(url: str, allow_userinfo: bool = False) -> tuple[bool, str]:
    if not url:
        return False, "URL is empty"

    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    scheme = parsed.scheme.lower()
    if not scheme:
        return False, "URL must have a scheme (http:// or https://)"
    if scheme in _SANDBOX_BLOCKED_SCHEMES:
        return False, f"URL scheme '{parsed.scheme}' is not allowed"
    if scheme not in ("http", "https"):
        return False, f"URL scheme '{parsed.scheme}' is not allowed (only http/https)"
    if not allow_userinfo and (parsed.username or parsed.password):
        return False, "URLs with embedded credentials are not allowed"

    hostname = parsed.hostname
    if not hostname:
        return False, "URL must have a hostname"
    if await is_internal_ip(hostname):
        return False, f"Internal addresses are not allowed: {hostname}"

    if re.match(r"^0[xX][0-9a-fA-F]+", hostname) or re.match(r"^\d+$", hostname):
        if await is_internal_ip(hostname):
            return False, "Numeric IP addresses are not allowed"

    return True, ""
