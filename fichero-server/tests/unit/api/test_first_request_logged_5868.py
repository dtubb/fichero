"""The engine logs `first request on <uds|https> after start` once per transport, saying nothing else (#5868)."""
from __future__ import annotations

import logging

import pytest

from fichero_server.api import transport_diagnostics as td


@pytest.fixture(autouse=True)
def _fresh():
    td._FIRST_SEEN.clear()
    yield
    td._FIRST_SEEN.clear()


def test_each_transport_is_named_once_and_only_by_name(caplog):
    caplog.set_level(logging.INFO, logger=td.logger.name)
    uds = {"server": ("/Users/bob/Library/fichero.sock", None), "scheme": "http", "headers": [(b"authorization", b"Bearer SECRET")]}
    tcp = {"server": ("127.0.0.1", 8765), "scheme": "https"}
    assert td.note_first_request(uds) == "uds"
    assert td.note_first_request(uds) is None
    assert td.note_first_request(tcp) == "https"
    assert td.note_first_request(tcp) is None
    lines = [r.getMessage() for r in caplog.records]
    assert lines == ["first request on uds after start", "first request on https after start"]
    assert not any(word in " ".join(lines) for word in ("bob", "SECRET", "8765", "127.0.0.1"))



def test_a_plain_http_listener_is_named_http(caplog):
    caplog.set_level(logging.INFO, logger=td.logger.name)
    assert td.note_first_request({"server": ("0.0.0.0", 8765), "scheme": "http"}) == "http"
    assert td.note_first_request({"server": ("0.0.0.0", 8765), "scheme": "http"}) is None
    assert [r.getMessage() for r in caplog.records] == ["first request on http after start"]
