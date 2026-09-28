"""#5188: seeding the shared test library reaches nothing off this machine.

Every live-engine fixture and the contract walk build their library with `seed()`. It writes
entities and claims, which auto-embed; before #5188 that downloaded FastEmbed's model from Hugging
Face whenever the cache was cold. This wraps `seed()` with every non-loopback connection refused
and recorded: a new network reach anywhere in seeding (a model, a gazetteer, a geocoder, a
licence check) fails here naming the host, instead of silently slowing or degrading a fixture.
"""

from __future__ import annotations

import socket

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def test_seeding_the_test_library_makes_no_outbound_connection(tmp_path, monkeypatch):
    from tests.integration._seedlib import seed

    tried: list[object] = []
    real_create = socket.create_connection
    real_connect = socket.socket.connect

    def _host(address):
        return address[0] if isinstance(address, tuple) else address

    def guarded_create(address, *args, **kwargs):
        if _host(address) not in _LOOPBACK:
            tried.append(address)
            raise OSError(f"seeding tried the network: {address}")
        return real_create(address, *args, **kwargs)

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and _host(address) not in _LOOPBACK:
            tried.append(address)
            raise OSError(f"seeding tried the network: {address}")
        return real_connect(self, address)

    monkeypatch.setattr(socket, "create_connection", guarded_create)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setenv("HOME", str(tmp_path))  # a cold model cache, as on a fresh machine or CI

    summary = seed(tmp_path / "library.fichero")

    assert summary["path"], "the seeder built a library"
    assert tried == [], f"seeding reached off the machine: {tried}"
