"""sharing.listener-binds-private-interfaces (#6383, owner ruling 2026-11-07, extends #5897): with Sharing on, the engine
also listens on every private interface address of the Mac (the Thunderbolt bridge's 10.10.10.x), never on 0.0.0.0, a
public address it was not named, Tailscale's 100.64/10 or loopback; with Sharing off only the loopback port."""

from fichero_server import __main__ as backend_main
from fichero_server.security.bind_host import private_interface_ips

INTERFACES = ["127.0.0.1", "131.202.228.31", "100.119.93.85", "10.10.10.2", "169.254.182.246", "0.0.0.0", "8.8.8.8"]


def test_only_private_interface_addresses_count():
    assert private_interface_ips(INTERFACES) == ["10.10.10.2", "169.254.182.246"]


def test_the_named_lan_address_stays_bound_and_the_bridge_is_added_beside_it(monkeypatch):
    # The campus LAN address (131.202.228.x, #5897) is what the app names: it is bound as before even though it is not
    # private; only the EXTRA interface addresses are filtered, and Tailscale's 100.x is never bound (the serve forward).
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: "131.202.228.31")
    monkeypatch.setattr(backend_main, "_private_interface_ips", lambda: private_interface_ips(INTERFACES))
    hosts = backend_main._listener_hosts("127.0.0.1")
    assert hosts[:2] == ["127.0.0.1", "131.202.228.31"], "loopback and the named LAN address, unchanged"
    assert hosts == ["127.0.0.1", "131.202.228.31", "10.10.10.2", "169.254.182.246"]
    assert "100.119.93.85" not in hosts


def test_sharing_off_binds_loopback_only(monkeypatch):
    monkeypatch.setattr(backend_main, "resolve_lan_bind_host", lambda: None)
    monkeypatch.setattr(backend_main, "_private_interface_ips", lambda: ["10.10.10.2"])
    assert backend_main._listener_hosts("127.0.0.1") == ["127.0.0.1"]


def test_the_bridge_address_is_bound_as_its_own_slot():
    bound = []

    class FakeSocket:
        def __init__(self, addr):
            self.addr = addr

        def getsockname(self):
            return (self.addr, 8765)

    def bind(addr, port):
        bound.append(addr)
        return FakeSocket(addr)

    backend_main._bind_sharing_listeners(["127.0.0.1", "10.10.10.2"], "127.0.0.1", 8765, bind=bind)
    assert bound == ["127.0.0.1", "10.10.10.2"]
