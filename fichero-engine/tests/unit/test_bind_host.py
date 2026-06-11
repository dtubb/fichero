from __future__ import annotations

import types

import pytest

from fichero.bind_host import DEFAULT_BIND_HOST, resolve_bind_host
from fichero.cli import engine_manager


def test_resolve_bind_host_defaults_to_loopback() -> None:
    assert resolve_bind_host({}) == DEFAULT_BIND_HOST


def test_resolve_bind_host_uses_specific_env_address() -> None:
    assert resolve_bind_host({"FICHERO_BIND_HOST": "100.64.12.34"}) == "100.64.12.34"


def test_resolve_bind_host_refuses_blanket_wildcard() -> None:
    with pytest.raises(ValueError, match="0\\.0\\.0\\.0 is not allowed"):
        resolve_bind_host({"FICHERO_BIND_HOST": "0.0.0.0"})


def test_start_uses_resolved_bind_host_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    class _FakeProc:
        pid = 4242

    def _fake_popen(cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        return _FakeProc()

    monkeypatch.setenv("FICHERO_BIND_HOST", "100.64.12.34")
    monkeypatch.setattr(engine_manager, "_read_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_write_pid", lambda _pid: None)
    monkeypatch.setattr(engine_manager, "_remove_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(
        engine_manager,
        "subprocess",
        types.SimpleNamespace(Popen=_fake_popen, DEVNULL=-3),
    )

    engine_manager.start()

    cmd = captured["cmd"]
    host_index = cmd.index("--host")
    assert cmd[host_index + 1] == "100.64.12.34"
