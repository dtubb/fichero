from __future__ import annotations

import json
from types import SimpleNamespace

from engine import __main__ as backend_main


def _manifest_json(material: SimpleNamespace) -> str:
    return json.dumps(
        {
            "bind_host": material.bind_host,
            "certificate_path": material.certificate_path,
            "key_path": material.key_path,
            "spki_pin": material.spki_pin,
        },
        sort_keys=True,
    )


def test_prepare_local_access_flag_prints_manifest_and_returns(monkeypatch, capsys, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_prepare_remote_access_tls(public_base_url: str, storage_root=None, allow_loopback=False):
        captured["public_base_url"] = public_base_url
        captured["storage_root"] = storage_root
        captured["allow_loopback"] = allow_loopback
        return SimpleNamespace(
            bind_host="127.0.0.1",
            certificate_path=str(tmp_path / "server.crt"),
            key_path=str(tmp_path / "server.key"),
            spki_pin="spki-pin",
        )

    monkeypatch.setattr(backend_main, "prepare_remote_access_tls", fake_prepare_remote_access_tls)
    monkeypatch.setattr(backend_main, "material_manifest_json", _manifest_json)

    backend_main.main(["--prepare-local-access", "--remote-access-dir", str(tmp_path)])

    assert captured == {
        "public_base_url": "https://127.0.0.1:8765",
        "storage_root": str(tmp_path),
        "allow_loopback": True,
    }
    assert json.loads(capsys.readouterr().out) == {
        "bind_host": "127.0.0.1",
        "certificate_path": str(tmp_path / "server.crt"),
        "key_path": str(tmp_path / "server.key"),
        "spki_pin": "spki-pin",
    }


def test_prepare_remote_access_flag_prints_manifest_and_returns(monkeypatch, capsys, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_prepare_remote_access_tls(public_base_url: str, storage_root=None, allow_loopback=False):
        captured["public_base_url"] = public_base_url
        captured["storage_root"] = storage_root
        captured["allow_loopback"] = allow_loopback
        return SimpleNamespace(
            bind_host="192.168.1.42",
            certificate_path=str(tmp_path / "server.crt"),
            key_path=str(tmp_path / "server.key"),
            spki_pin="spki-pin",
        )

    monkeypatch.setattr(backend_main, "prepare_remote_access_tls", fake_prepare_remote_access_tls)
    monkeypatch.setattr(backend_main, "material_manifest_json", _manifest_json)

    backend_main.main(
        [
            "--prepare-remote-access",
            "--public-base-url",
            "https://192.168.1.42:9443",
            "--remote-access-dir",
            str(tmp_path),
        ]
    )

    assert captured["public_base_url"] == "https://192.168.1.42:9443"
    assert captured["storage_root"] == str(tmp_path)
    assert captured["allow_loopback"] is False
    assert json.loads(capsys.readouterr().out) == {
        "bind_host": "192.168.1.42",
        "certificate_path": str(tmp_path / "server.crt"),
        "key_path": str(tmp_path / "server.key"),
        "spki_pin": "spki-pin",
    }
