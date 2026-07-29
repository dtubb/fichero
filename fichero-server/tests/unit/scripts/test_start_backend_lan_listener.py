from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_LAUNCHER = Path(__file__).resolve().parents[3] / "scripts" / "start_backend.py"


def _load():
    spec = importlib.util.spec_from_file_location("start_backend", _LAUNCHER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_lan_listener_requires_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _load()
    monkeypatch.setattr(mod, "resolve_bind_host", lambda: "127.0.0.1")
    monkeypatch.setattr(mod, "resolve_lan_bind_host", lambda: "192.168.1.42")
    monkeypatch.setattr(mod, "uvicorn_ssl_kwargs_from_env", lambda: {})

    with pytest.raises(SystemExit, match="requires TLS"):
        mod.main([])


def test_lan_listener_binds_loopback_and_specific_lan_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mod = _load()
    bound_hosts: list[str] = []
    captured: dict[str, object] = {}

    class _FakeSocket:
        def close(self) -> None:
            return None

    class _FakeServer:
        def __init__(self, config):
            captured["config"] = config

        def run(self, sockets=None):
            captured["socket_count"] = len(sockets or [])

    def fake_bind_listener_socket(host: str, port: int):
        bound_hosts.append(f"{host}:{port}")
        return _FakeSocket()

    fake_uvicorn = types.SimpleNamespace(
        Config=lambda **kwargs: kwargs,
        Server=_FakeServer,
        run=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("unexpected uvicorn.run")),
    )

    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    monkeypatch.setattr(mod, "resolve_bind_host", lambda: "127.0.0.1")
    monkeypatch.setattr(mod, "resolve_lan_bind_host", lambda: "192.168.1.42")
    monkeypatch.setattr(
        mod,
        "uvicorn_ssl_kwargs_from_env",
        lambda: {"ssl_certfile": "/tmp/test.crt", "ssl_keyfile": "/tmp/test.key"},
    )
    monkeypatch.setattr(mod, "_bind_listener_socket", fake_bind_listener_socket)

    mod.main([])

    assert bound_hosts == ["127.0.0.1:8765", "192.168.1.42:8765"]
    assert captured["socket_count"] == 2
