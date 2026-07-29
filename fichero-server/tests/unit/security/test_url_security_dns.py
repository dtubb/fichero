"""Extra SSRF-guard coverage for ``url_security`` — the paths the existing
``test_url_security.py`` block-matrix doesn't exercise: DNS resolution
(hostname -> internal IP), the remaining blocked networks + schemes, and
scheme case-handling.

The DNS path is stubbed via ``socket.getaddrinfo`` so nothing hits live DNS;
async helpers are driven with ``asyncio.run`` to match the sibling tests.
"""

from __future__ import annotations

import asyncio
import socket

import pytest

import fichero_server.security.url_security as us
from fichero_server.security.url_security import is_internal_ip, is_safe_url


def _run(coro):
    return asyncio.run(coro)


# ===========================================================================
# Additional blocked networks (IP literals — no DNS)
# ===========================================================================


@pytest.mark.parametrize(
    "host",
    [
        "0.0.0.0",           # 0.0.0.0/8
        "169.254.1.1",       # link-local (non-metadata)
        "fc00::1",           # IPv6 unique-local (fc00::/7)
        "fe80::1",           # IPv6 link-local (fe80::/10)
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
    ],
)
def test_additional_internal_networks_blocked(host):
    assert _run(is_internal_ip(host)) is True


def test_ipv4_mapped_range_blocks_even_public_address():
    # Documented conservative choice: the whole ::ffff:0:0/96 range is blocked,
    # so an IPv4-mapped *public* address is rejected too. Safe-side over-block.
    assert _run(is_internal_ip("::ffff:8.8.8.8")) is True


# ===========================================================================
# Remaining blocked schemes + scheme case-insensitivity
# ===========================================================================


@pytest.mark.parametrize(
    "url",
    [
        "s3://bucket/key",
        "smb://host/share",
        "ssh://host/",
        "telnet://host/",
        "ldap://host/",
        "ldaps://host/",
        "ftps://host/file",
    ],
)
def test_more_blocked_schemes(url):
    safe, error = _run(is_safe_url(url))
    assert safe is False
    assert "not allowed" in error


@pytest.mark.parametrize("url", ["HTTP://8.8.8.8/", "HTTPS://8.8.8.8/path"])
def test_scheme_is_case_insensitive(url):
    safe, error = _run(is_safe_url(url))
    assert safe is True, error


# ===========================================================================
# DNS resolution path (getaddrinfo stubbed — the SSRF-via-hostname vector)
# ===========================================================================


def _stub_getaddrinfo(monkeypatch, ips=None, raise_exc=None):
    def fake(host, port, *a, **k):
        if raise_exc is not None:
            raise raise_exc
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0)) for ip in (ips or [])]

    monkeypatch.setattr(us.socket, "getaddrinfo", fake)


def test_hostname_resolving_to_internal_is_blocked(monkeypatch):
    _stub_getaddrinfo(monkeypatch, ips=["10.0.0.5"])
    assert _run(is_internal_ip("evil.example.com")) is True


def test_hostname_resolving_to_public_is_allowed(monkeypatch):
    _stub_getaddrinfo(monkeypatch, ips=["93.184.216.34"])
    assert _run(is_internal_ip("example.com")) is False


def test_hostname_with_any_internal_answer_is_blocked(monkeypatch):
    # DNS-rebinding style: mixed answers — a single internal record blocks.
    _stub_getaddrinfo(monkeypatch, ips=["93.184.216.34", "127.0.0.1"])
    assert _run(is_internal_ip("rebind.example.com")) is True


def test_unresolvable_hostname_is_not_flagged_internal(monkeypatch):
    # Documented fail-open: a name that won't resolve is treated as "not
    # internal" (the actual connection will simply fail downstream).
    _stub_getaddrinfo(monkeypatch, raise_exc=socket.gaierror("no such host"))
    assert _run(is_internal_ip("nope.invalid")) is False


def test_is_safe_url_blocks_hostname_resolving_internal(monkeypatch):
    _stub_getaddrinfo(monkeypatch, ips=["192.168.1.50"])
    safe, error = _run(is_safe_url("http://intranet.example.com/admin"))
    assert safe is False
    assert "Internal addresses are not allowed" in error


def test_is_safe_url_allows_hostname_resolving_public(monkeypatch):
    _stub_getaddrinfo(monkeypatch, ips=["93.184.216.34"])
    safe, error = _run(is_safe_url("https://example.com/page"))
    assert safe is True, error
    assert error == ""


def test_metadata_hostname_short_circuits_before_dns(monkeypatch):
    # Cloud-metadata hostnames are caught by name, never reaching getaddrinfo.
    def explode(*a, **k):
        raise AssertionError("getaddrinfo should not be called for metadata host")

    monkeypatch.setattr(us.socket, "getaddrinfo", explode)
    assert _run(is_internal_ip("metadata.googleapis.com")) is True
