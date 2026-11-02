"""`sharing.listener-follows-the-network` (docs/contributor_manual/specs/source/sharing-two-macs.md §4, Step 1.5).

The engine binds one LAN address. When the Mac's address changes under it (DHCP renewal, Wi-Fi to Ethernet) health says so in
the sentence the Sharing pane shows. The engine does not rebind the live socket (a ponytail ceiling): the person turns
Sharing off and on, which makes a new listener and, under one key per Mac, keeps every pin.
"""
from __future__ import annotations

from tests.unit.api.test_health_reports_sharing_to_spec import _health, _quiet_network
from tests.unit.transport.test_two_macs_end_to_end_to_spec import two_macs  # noqa: F401

# ruff: noqa: F811  -- pytest fixtures are passed by name; the parameter shadows the imported fixture on purpose


def test_health_says_the_address_changed(two_macs, monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    monkeypatch.setenv("FICHERO_LAN_HOST", "192.0.2.10")
    _quiet_network(monkeypatch, lan="192.0.2.77")  # the Mac now has another address than the one bound
    assert _health(two_macs).json()["sharing"]["address_changed"] == "This Mac's network address changed. Turn Sharing off and on."


def test_the_same_address_is_no_change(two_macs, monkeypatch):
    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    monkeypatch.setenv("FICHERO_LAN_HOST", "192.0.2.10")
    _quiet_network(monkeypatch, lan="192.0.2.10")
    assert _health(two_macs).json()["sharing"]["address_changed"] is None


def test_no_network_now_is_offline_not_a_change(two_macs, monkeypatch):
    from fichero_server.security import bind_host

    monkeypatch.setenv("FICHERO_TCP_TLS_ALSO", "1")
    monkeypatch.setenv("FICHERO_LAN_HOST", "192.0.2.10")
    _quiet_network(monkeypatch)
    monkeypatch.setattr(bind_host, "primary_lan_ip", lambda: (_ for _ in ()).throw(OSError("no network")))
    assert _health(two_macs).json()["sharing"]["address_changed"] is None


def test_a_loopback_only_engine_has_nothing_to_follow(two_macs, monkeypatch):
    for name in ("FICHERO_TCP_TLS_ALSO", "FICHERO_LAN_HOST", "FICHERO_PUBLIC_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    _quiet_network(monkeypatch, lan="192.0.2.77")
    assert _health(two_macs).json()["sharing"]["address_changed"] is None
