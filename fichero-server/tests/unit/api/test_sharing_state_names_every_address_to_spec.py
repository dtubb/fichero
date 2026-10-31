"""`sharing.state-names-every-address` (docs/contributor_manual/specs/source/sharing-two-macs.md §10.1).

`GET /api/pair/sharing` names the host's addresses in one place: the sharing address the engine was started with
(`public_base_url`), the LAN IP, the tailnet name and whether the tailnet forward is Fichero's own, another
service's, or absent. The app's address rows, the CLI's `devices invite` and a tester read this instead of guessing.
"""
from __future__ import annotations

from tests.unit.transport.test_sharing_state_and_multiuser_switch_to_spec import _owner
from tests.unit.transport.test_two_macs_end_to_end_to_spec import two_macs  # noqa: F401

# ruff: noqa: F811  -- pytest fixtures are passed by name; the parameter shadows the imported fixture on purpose


def test_sharing_state_names_the_sharing_address_the_lan_ip_and_the_forward(two_macs, monkeypatch):
    from fichero_server.security import bind_host, tailscale_serve

    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://macbook-air-m1.local:8765")
    monkeypatch.setattr(tailscale_serve, "detected_tailnet_url", lambda *a, **k: "https://m.tail.ts.net")
    monkeypatch.setattr(tailscale_serve, "forward_state", lambda port: "ours")
    monkeypatch.setattr(bind_host, "primary_lan_ip", lambda: "192.0.2.10")

    body = two_macs["a"].get("/api/pair/sharing", headers=_owner(two_macs["a"])).json()
    assert body["public_base_url"] == "https://macbook-air-m1.local:8765"
    assert body["lan_ip"] == "192.0.2.10"
    assert body["tailnet_url"] == "https://m.tail.ts.net"
    assert body["tailnet_forward"] == "ours"


def test_sharing_state_says_none_when_nothing_is_shared(two_macs, monkeypatch):
    from fichero_server.security import bind_host, tailscale_serve

    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setattr(tailscale_serve, "detected_tailnet_url", lambda *a, **k: "")
    monkeypatch.setattr(tailscale_serve, "forward_state", lambda port: "none")
    monkeypatch.setattr(bind_host, "primary_lan_ip", lambda: (_ for _ in ()).throw(OSError("no network")))

    body = two_macs["a"].get("/api/pair/sharing", headers=_owner(two_macs["a"])).json()
    assert body["public_base_url"] is None
    assert body["lan_ip"] is None  # no network: no address, never a 500
    assert body["tailnet_url"] is None
    assert body["tailnet_forward"] == "none"
