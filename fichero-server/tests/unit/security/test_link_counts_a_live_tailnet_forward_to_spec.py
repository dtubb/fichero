"""sharing.link-counts-a-live-tailnet-forward (t58, live 2026-11-06): the Air had Fichero's own Tailscale forward
(`https://macbook-air-m1.<tailnet>.ts.net:8765 -> https+insecure://127.0.0.1:8765`) yet minting a code was refused with
409 because the `.local` sharing address had no network listener. A live forward to the loopback listener is somewhere
to listen: the code is minted and the link names the tailnet first. With nothing bound at all, it is still refused.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.api import transport_diagnostics as td

LOCAL = "https://macbook-air-m1.local:8765"


@pytest.fixture(autouse=True)
def _bound():
    before = td._BOUND_TCP
    yield
    td._BOUND_TCP = before


def test_a_live_forward_with_the_loopback_listener_is_reachable():
    assert td.network_listener_gap(LOCAL, ["127.0.0.1"], tailnet_forward=True) is None


def test_a_forward_to_nothing_is_still_refused():
    gap = td.network_listener_gap(LOCAL, [], tailnet_forward=True)
    assert gap and "not listening there" in gap


def test_minting_a_code_with_a_live_forward_is_not_refused(monkeypatch):
    from fichero_server.api.routes.auth import pairing
    from fichero_server.security import tailscale_serve

    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", LOCAL)
    monkeypatch.setattr(pairing, "_require_secure_pairing_transport", lambda request: None)
    monkeypatch.setattr(pairing, "_pairing_user", lambda *_: SimpleNamespace(is_owner=True, id="u"))
    monkeypatch.setattr(tailscale_serve, "forward_state", lambda _port: "ours")
    td.note_tcp_listeners(["127.0.0.1"])
    try:
        pairing.create_pairing_code(SimpleNamespace(), app_db=SimpleNamespace())
    except Exception as exc:  # anything after the gap check needs a real database; the 409 must not be it
        assert getattr(exc, "status_code", None) != 409 or "not listening there" not in str(getattr(exc, "detail", ""))
