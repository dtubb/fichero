"""#5898 sharing.synced-project-names-its-host: the guest engine reads and validates `sharing-host.json`."""

import json

import pytest

from fichero_server.security.synced_host import FILE_NAME, MAX_BYTES, host_to_ask, own_origin, read_synced_host

GOOD = {"hostURL": "https://studio.local:8765", "hostName": "Studio", "person": "Ana"}


def _write(root, data):
    (root / FILE_NAME).write_text(data if isinstance(data, str) else json.dumps(data))


def test_a_valid_file_is_read(tmp_path):
    _write(tmp_path, GOOD)
    host = read_synced_host(tmp_path)
    assert (host.hostURL, host.hostName, host.person) == tuple(GOOD.values())


@pytest.mark.parametrize(
    "bad",
    [
        {**GOOD, "token": "x"},  # an extra key (a secret must never travel in it)
        {"hostURL": GOOD["hostURL"], "hostName": "Studio"},  # a missing key
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
    # only the three keys, valid JSON: refused for its SIZE alone (trailing whitespace)
    _write(tmp_path, json.dumps(GOOD) + " " * MAX_BYTES)
    assert read_synced_host(tmp_path) is None


def test_the_hosts_own_copy_asks_nobody(tmp_path, monkeypatch):
    _write(tmp_path, GOOD)
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://STUDIO.local:8765/")
    assert own_origin() == "https://studio.local:8765"
    assert host_to_ask(tmp_path) is None  # this engine IS the recorded host
    monkeypatch.setenv("FICHERO_PUBLIC_BASE_URL", "https://other.local:8765")
    assert host_to_ask(tmp_path).person == "Ana"  # another engine is a guest
    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL")
    assert host_to_ask(tmp_path).person == "Ana"


def test_no_file_names_no_host(tmp_path):
    assert read_synced_host(tmp_path) is None


def test_the_open_handle_carries_the_host(tmp_path, monkeypatch):
    from fichero_server.api.routes.library import registry

    _write(tmp_path, GOOD)
    monkeypatch.delenv("FICHERO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.setattr(registry.db_manager, "open_library_paths", lambda: [str(tmp_path)])
    handles = registry.list_open_libraries().libraries
    assert handles[0].synced_host.person == "Ana"
