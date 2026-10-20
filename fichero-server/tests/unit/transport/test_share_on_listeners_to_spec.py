"""sharing.listener (#5897, owner ruling 2026-10-20): Sharing on listens on this network, by itself.

There is no separate "This network" switch. When the app names a LAN address (`FICHERO_LAN_HOST`, set only while Sharing is
on at a `.local` address) the engine binds it beside the loopback port, whatever devices are paired and whatever an old
`FICHERO_THIS_NETWORK` says; with no LAN address (Sharing off, or shared over Tailscale, which reaches the loopback
port through `tailscale serve`) only the loopback port is bound.
"""

import pytest

from fichero_server import __main__ as backend_main

LAN = "192.168.1.42"


@pytest.fixture(autouse=True)
def _lan(monkeypatch):
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: LAN)


def test_sharing_on_at_a_local_address_binds_the_lan_listener_with_no_device_paired(app_db):
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1", LAN]


def test_an_old_this_network_off_no_longer_closes_it(app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_THIS_NETWORK", "0")
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1", LAN]


def test_no_lan_address_means_loopback_only(app_db, monkeypatch):
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: None)  # Sharing off, or shared over Tailscale
    assert backend_main._listener_hosts("127.0.0.1", app_db=app_db) == ["127.0.0.1"]


def test_a_lan_address_equal_to_the_bind_host_is_not_bound_twice(app_db):
    assert backend_main._listener_hosts(LAN, app_db=app_db) == [LAN]
