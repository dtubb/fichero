"""#5898 sharing.synced-project-names-its-host: the guest engine reads and validates `sharing-host.json`."""

import json

import pytest

from fichero_server.security.synced_host import FILE_NAME, MAX_BYTES, host_to_ask, read_synced_host

GOOD = {"hostURL": "https://studio.local:8765", "hostName": "Studio", "person": "Ana", "hostEngineId": "eng-host-1"}


def _write(root, data):
    (root / FILE_NAME).write_text(data if isinstance(data, str) else json.dumps(data))


def test_a_valid_file_is_read(tmp_path):
    _write(tmp_path, GOOD)
    host = read_synced_host(tmp_path)
    assert host.model_dump() == GOOD


@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD, "token": "x"},  # an extra key (a secret must never travel in it)
        {"hostURL": GOOD["hostURL"], "hostName": "Studio", "person": "Ana"},  # no hostEngineId  # a missing key
        {**GOOD, "hostURL": "http://studio.local:8765"},  # not https
        {**GOOD, "hostURL": "fichero://pair?x=1"},
        {**GOOD, "hostURL": "https://studio.local:8765/pair?code=ABCD"},  # more than an origin
        {**GOOD, "hostURL": "https://user:pw@studio.local:8765"},
        {**GOOD, "person": "fichero://pair?payload=x"},  # link-like
        {**GOOD, "person": ""},
        {**GOOD, "hostName": "x" * 201},
        "not json",
    ],
)
def test_anything_else_names_no_host(tmp_path, bad):
    _write(tmp_path, bad)
    assert read_synced_host(tmp_path) is None


def test_a_file_over_the_size_cap_is_ignored(tmp_path):
    # only the four keys, valid JSON: refused for its SIZE alone (trailing whitespace)
    _write(tmp_path, json.dumps(GOOD) + " " * MAX_BYTES)
    assert read_synced_host(tmp_path) is None


def test_the_hosts_own_copy_asks_nobody_whatever_its_address(tmp_path, monkeypatch):
    from fichero_server.security import synced_host

    _write(tmp_path, GOOD)
    monkeypatch.setattr(synced_host, "is_this_engine", lambda engine_id: engine_id == "eng-host-1")
    # Sharing off (no FICHERO_PUBLIC_BASE_URL) and a changed address (hostURL differs from any current one): still nobody
    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    assert host_to_ask(tmp_path) is None
    _write(tmp_path, {**GOOD, "hostURL": "https://old-address.local:8765"})
    assert host_to_ask(tmp_path) is None


def test_a_different_engine_id_asks(tmp_path, monkeypatch):
    from fichero_server.security import synced_host

    _write(tmp_path, GOOD)
    monkeypatch.setattr(synced_host, "is_this_engine", lambda engine_id: engine_id == "another-engine")
    assert host_to_ask(tmp_path).person == "Ana"


def test_is_this_engine_compares_the_engines_own_id(monkeypatch):
    from fichero_server.api.routes.auth import accounts
    from fichero_server.security import synced_host

    monkeypatch.setattr("fichero_server.db.app.get_app_db", lambda: object())
    monkeypatch.setattr(accounts, "_engine_id", lambda db: "eng-host-1")
    synced_host.this_engine_id.cache_clear()
    try:
        assert synced_host.this_engine_id() == "eng-host-1"
        monkeypatch.setattr(accounts, "_engine_id", lambda db: "changed")
        assert synced_host.this_engine_id() == "eng-host-1"  # cached: no second app-DB read
    finally:
        synced_host.this_engine_id.cache_clear()
    monkeypatch.setattr(accounts, "_engine_id", lambda db: "eng-host-1")
    try:
        assert synced_host.is_this_engine("eng-host-1")
        assert not synced_host.is_this_engine("eng-other")
    finally:
        synced_host.this_engine_id.cache_clear()
    assert not synced_host.is_this_engine(None)
    assert not synced_host.is_this_engine("")


def test_no_file_names_no_host(tmp_path):
    assert read_synced_host(tmp_path) is None


def test_the_open_handle_carries_the_host(tmp_path, monkeypatch):
    from fichero_server.api.routes.library import registry

    _write(tmp_path, GOOD)
    monkeypatch.setattr(registry.db_manager, "open_library_paths", lambda: [str(tmp_path)])
    monkeypatch.setattr("fichero_server.security.synced_host.is_this_engine", lambda engine_id: False)
    handles = registry.list_open_libraries().libraries
    assert handles[0].synced_host.person == "Ana"
