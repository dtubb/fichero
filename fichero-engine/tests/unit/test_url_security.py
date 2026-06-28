"""Direct unit coverage for the shared SSRF guard `fichero.url_security`.

`is_safe_url` / `is_internal_ip` are the single primitive every research/web tool
delegates to (`research._is_safe_url` → `is_safe_url`). The existing SSRF tests
exercise it only indirectly through the tool functions; this locks the guard's
block-matrix directly, so coverage survives any router/tool refactor (#2600/#2593).

All cases use IP literals or known metadata hostnames so the matrix never depends
on live DNS (`is_internal_ip` parses literals without `getaddrinfo`). Async helpers
are driven with `asyncio.run` to match the sibling SSRF tests' convention.
"""

from __future__ import annotations

import asyncio

import pytest

from fichero.url_security import is_internal_ip, is_safe_url


@pytest.mark.parametrize(
    "url",
    [
        "",  # empty
        "example.com",  # no scheme
        "ftp://example.com/x",  # blocked scheme
        "file:///etc/passwd",  # blocked scheme (local file)
        "gopher://example.com/",  # blocked scheme
        "ws://example.com/",  # non-http(s) scheme
        "http://user:pass@example.com/",  # embedded credentials
        "http:///nohost",  # no hostname
        "http://127.0.0.1/admin",  # loopback
        "http://10.0.0.5/",  # private 10/8
        "http://172.16.0.1/",  # private 172.16/12
        "http://192.168.1.1/",  # private 192.168/16
        "http://169.254.169.254/latest/meta-data/",  # cloud metadata
        "http://metadata.google.internal/",  # cloud metadata host
        "http://[::1]/",  # IPv6 loopback
    ],
)
def test_is_safe_url_blocks_ssrf_vectors(url):
    safe, error = asyncio.run(is_safe_url(url))
    assert safe is False, f"{url!r} should be blocked"
    assert error, f"{url!r} should report a reason"


@pytest.mark.parametrize("url", ["https://8.8.8.8/path", "http://93.184.216.34/"])
def test_is_safe_url_allows_public_ip_literals(url):
    safe, error = asyncio.run(is_safe_url(url))
    assert safe is True, f"{url!r} should be allowed (got: {error})"
    assert error == ""


def test_is_safe_url_userinfo_gate():
    # Embedded creds blocked by default, permitted only when explicitly allowed.
    blocked, _ = asyncio.run(is_safe_url("https://user:pass@8.8.8.8/"))
    assert blocked is False
    allowed, error = asyncio.run(
        is_safe_url("https://user:pass@8.8.8.8/", allow_userinfo=True)
    )
    assert allowed is True, error


@pytest.mark.parametrize(
    "host,expected",
    [
        (None, False),
        ("8.8.8.8", False),  # public
        ("127.0.0.1", True),  # loopback
        ("10.1.2.3", True),  # private
        ("169.254.169.254", True),  # cloud metadata literal
        ("metadata.google.internal", True),  # cloud metadata hostname
        ("::1", True),  # IPv6 loopback
    ],
)
def test_is_internal_ip_literals(host, expected):
    assert asyncio.run(is_internal_ip(host)) is expected
