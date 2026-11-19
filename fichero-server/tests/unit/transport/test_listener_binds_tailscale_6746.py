"""#6746: with Sharing on, the server also listens on this Mac's Tailscale address (100.64/10), so a tailnet device
reaches it directly; with Sharing off only loopback."""

from fichero_server import __main__ as backend_main
from fichero_server.security.bind_host import tailscale_interface_ips

INTERFACES = ["127.0.0.1", "131.202.229.82", "100.107.68.106", "10.10.10.1", "100.200.0.1", "8.8.8.8"]


def test_only_the_tailscale_range_counts():
    assert tailscale_interface_ips(INTERFACES) == ["100.107.68.106"]


def test_the_listen_set_includes_the_tailscale_address(monkeypatch):
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: "131.202.229.82")
    monkeypatch.setattr(backend_main, "_private_interface_ips", lambda: ["10.10.10.1"])
    monkeypatch.setattr(backend_main, "_tailscale_interface_ips", lambda: ["100.107.68.106"])
    assert backend_main._listener_hosts("127.0.0.1") == ["127.0.0.1", "131.202.229.82", "10.10.10.1", "100.107.68.106"]


def test_an_address_that_appears_later_is_picked_up(monkeypatch):
    seen = [[], ["100.107.68.106"]]
    monkeypatch.setattr(backend_main, "_tailscale_interface_ips", lambda: seen.pop(0))
    assert backend_main._new_tailscale_hosts(set()) == []
    assert backend_main._new_tailscale_hosts(set()) == ["100.107.68.106"]
    monkeypatch.setattr(backend_main, "_tailscale_interface_ips", lambda: ["100.107.68.106"])
    assert backend_main._new_tailscale_hosts({"100.107.68.106"}) == []
