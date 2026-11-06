"""sharing.listener-slots-bind-alone (t52, live 2026-11-06): Sharing was on on the Air, but nothing listened on 8765,
not even loopback. Every listener slot was bound in one try, so one failing slot closed them all. Now each slot binds
on its own, a port the replaced engine still holds is tried again, and a LAN address the Mac no longer has is replaced
by the one it has now.
"""

import errno

import pytest

from fichero_server import __main__ as backend_main

LOOP, OLD_LAN, NEW_LAN = "127.0.0.1", "131.202.228.242", "131.202.228.65"


class _Sock:
    def __init__(self, addr):
        self.addr = addr

    def getsockname(self):
        return (self.addr, 8765)


@pytest.fixture(autouse=True)
def _resolve(monkeypatch):
    monkeypatch.setattr(backend_main, "_slot_address", lambda host, bind_host, port: host)
    monkeypatch.setattr(backend_main, "_primary_lan_ip", lambda: NEW_LAN)
    monkeypatch.setattr(backend_main.time, "sleep", lambda _s: None)


def _binder(fail):
    calls = []

    def bind(addr, port):
        calls.append(addr)
        err = fail(addr, len(calls))
        if err:
            raise OSError(err, "boom")
        return _Sock(addr)

    return bind, calls


def test_a_lan_slot_that_cannot_bind_leaves_loopback_up():
    bind, _ = _binder(lambda addr, n: errno.EACCES if addr != LOOP else None)
    socks = backend_main._bind_sharing_listeners([LOOP, OLD_LAN], LOOP, 8765, bind=bind)
    assert [s.addr for s in socks] == [LOOP]


def test_a_port_still_held_by_the_replaced_engine_is_tried_again():
    bind, calls = _binder(lambda addr, n: errno.EADDRINUSE if n <= 2 else None)
    socks = backend_main._bind_sharing_listeners([LOOP], LOOP, 8765, bind=bind)
    assert [s.addr for s in socks] == [LOOP] and len(calls) == 3


def test_a_lan_address_the_mac_no_longer_has_follows_the_current_one():
    bind, _ = _binder(lambda addr, n: errno.EADDRNOTAVAIL if addr == OLD_LAN else None)
    socks = backend_main._bind_sharing_listeners([LOOP, OLD_LAN], LOOP, 8765, bind=bind)
    assert [s.addr for s in socks] == [LOOP, NEW_LAN]
