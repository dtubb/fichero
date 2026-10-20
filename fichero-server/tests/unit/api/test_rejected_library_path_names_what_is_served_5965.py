"""A library path the engine rejects ends with what it serves (#5965, `sharing.guest-addresses-the-hosts-library`): a guest that
sent its own local path learns which libraries to address. The sentences the allowlist tests pin are unchanged."""
from __future__ import annotations

from fichero_server.api import main as api_main


def test_the_refusal_names_the_libraries_this_mac_serves(monkeypatch):
    monkeypatch.setattr(api_main, "_served_library_names", lambda: ["Marshall Diaries", "Letters"])
    payload = api_main._rejected_library_path_payload("/var/mobile/Containers/Data/Application/X/Documents/global.fichero")
    assert payload["detail"].endswith("This Mac serves: Marshall Diaries, Letters.")
    assert "/var/mobile/" in payload["detail"]


def test_with_nothing_served_the_refusal_is_unchanged(monkeypatch):
    monkeypatch.setattr(api_main, "_served_library_names", lambda: [])
    payload = api_main._rejected_library_path_payload("/var/mobile/X/global.fichero")
    assert "This Mac serves" not in payload["detail"]
    assert payload["detail"] == api_main._rejected_library_path_detail("/var/mobile/X/global.fichero")


def test_a_failure_to_read_the_registry_never_hides_the_refusal(monkeypatch):
    def broken():
        raise RuntimeError("registry unavailable")

    monkeypatch.setattr(api_main, "_served_library_names_unsafe", broken)
    assert api_main._served_library_names() == []
