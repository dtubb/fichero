"""sharing.link-names-a-listener: a pairing link never names an address nothing listens on (owner ruling 2026-10-20).

Spec: docs/contributor_manual/specs/transport/library-sharing.md. Seen live: Sharing on at `macbook-air-m4.local`, the
engine bound 127.0.0.1 only, so the link could never be used. The engine records what it bound; minting refuses in words.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fichero_server.api import transport_diagnostics as td


@pytest.fixture(autouse=True)
def _bound():
    before = td._BOUND_TCP
    yield
    td._BOUND_TCP = before


def test_a_local_link_with_only_loopback_bound_is_refused_in_words():
    gap = td.network_listener_gap("https://macbook-air-m4.local:8765", ["127.0.0.1"])
    assert gap and "macbook-air-m4.local" in gap and "not listening there" in gap


def test_a_local_link_with_a_lan_listener_is_fine():
    assert td.network_listener_gap("https://macbook-air-m4.local:8765", ["127.0.0.1", "192.168.50.225"]) is None


def test_a_tailnet_link_needs_only_loopback_because_tailscale_serves_it():
    assert td.network_listener_gap("https://studio.tail1234.ts.net", ["127.0.0.1"]) is None


def test_an_engine_that_recorded_nothing_is_not_judged():
    assert td.network_listener_gap("https://macbook-air-m4.local:8765", None) is None
    assert td.network_listener_gap("", ["127.0.0.1"]) is None


def test_minting_a_code_refuses_with_409_when_nothing_listens_where_the_link_points(monkeypatch):
    from fichero_server.api.routes.auth import pairing

    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://macbook-air-m4.local:8765")
    monkeypatch.setattr(pairing, "_require_secure_pairing_transport", lambda request: None)
    monkeypatch.setattr(pairing, "_pairing_user", lambda *_: SimpleNamespace(is_owner=True, id="u"))
    td.note_tcp_listeners(["127.0.0.1"])
    with pytest.raises(HTTPException) as refused:
        pairing.create_pairing_code(SimpleNamespace(), app_db=SimpleNamespace())
    assert refused.value.status_code == 409 and "not listening there" in refused.value.detail
