from __future__ import annotations

import pytest

from server import __main__ as backend_main
from fichero_server.security.bind_host import (
    LAN_BIND_HOST_ENV,
    NON_LOOPBACK_BIND_ACK_ENV,
    NON_LOOPBACK_BIND_ACK_VALUE,
    resolve_lan_bind_host,
)


def test_listener_hosts_stays_loopback_only_without_explicit_lan_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: None)

    assert backend_main._listener_hosts("127.0.0.1") == ["127.0.0.1"]


def test_listener_hosts_adds_only_explicit_lan_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: "192.168.1.42")

    assert backend_main._listener_hosts("127.0.0.1") == ["127.0.0.1", "192.168.1.42"]


def test_listener_hosts_never_duplicates_loopback_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: "127.0.0.1")

    assert backend_main._listener_hosts("127.0.0.1") == ["127.0.0.1"]


@pytest.mark.parametrize("bind_host", ["127.0.0.1", "::1", "localhost"])
def test_listener_hosts_never_returns_wildcards_for_supported_inputs(
    monkeypatch: pytest.MonkeyPatch, bind_host: str
) -> None:
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: "192.168.1.42")

    listener_hosts = backend_main._listener_hosts(bind_host)

    assert "0.0.0.0" not in listener_hosts
    assert "::" not in listener_hosts


def test_explicit_lan_host_rejects_wildcard_bind_even_with_ack() -> None:
    with pytest.raises(ValueError, match=r"0\.0\.0\.0 is not allowed"):
        resolve_lan_bind_host(
            {
                LAN_BIND_HOST_ENV: "0.0.0.0",
                NON_LOOPBACK_BIND_ACK_ENV: NON_LOOPBACK_BIND_ACK_VALUE,
            }
        )
