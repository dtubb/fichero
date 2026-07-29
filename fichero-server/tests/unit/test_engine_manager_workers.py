"""The engine must launch as a single uvicorn process (#2044).

DuckDB serializes writes only within one process, and the change-stream hub +
DB connection manager are in-process singletons. Multiple worker processes
corrupt the single-writer DuckDB file AND split SSE fan-out, so ``start()`` must
clamp ``workers`` to 1 regardless of what the caller asks for.
"""

from __future__ import annotations

import types

import pytest

from fichero_cli import engine_manager


def _captured_start(monkeypatch, workers: int) -> list[str]:
    """Run ``start(workers=...)`` with all side effects stubbed; return the
    argv that would have been handed to ``subprocess.Popen``."""
    captured: dict[str, list[str]] = {}

    class _FakeProc:
        pid = 4242

    def _fake_popen(cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        return _FakeProc()

    # Neutralize every real side effect of start().
    monkeypatch.setenv("FICHERO_TLS_CERTFILE", "/tmp/fichero-test.crt")
    monkeypatch.setenv("FICHERO_TLS_KEYFILE", "/tmp/fichero-test.key")
    monkeypatch.setattr(engine_manager, "_read_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_write_pid", lambda _pid: None)
    monkeypatch.setattr(engine_manager, "_remove_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(
        engine_manager, "subprocess", types.SimpleNamespace(Popen=_fake_popen, DEVNULL=-3)
    )

    engine_manager.start(port=8765, workers=workers)
    return captured["cmd"]


@pytest.mark.parametrize("requested", [1, 2, 4, 8])
def test_start_always_launches_single_worker(monkeypatch, requested):
    """Whatever ``workers`` is requested, the spawned uvicorn uses --workers 1."""
    cmd = _captured_start(monkeypatch, requested)
    assert "--workers" in cmd
    idx = cmd.index("--workers")
    assert cmd[idx + 1] == "1", f"requested {requested} -> expected clamp to 1"


def test_start_default_is_single_worker(monkeypatch):
    """The default (no explicit workers) is a single process."""
    captured: dict[str, list[str]] = {}

    class _FakeProc:
        pid = 1

    def _fake_popen(cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        return _FakeProc()

    monkeypatch.setenv("FICHERO_TLS_CERTFILE", "/tmp/fichero-test.crt")
    monkeypatch.setenv("FICHERO_TLS_KEYFILE", "/tmp/fichero-test.key")
    monkeypatch.setattr(engine_manager, "_read_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_write_pid", lambda _pid: None)
    monkeypatch.setattr(engine_manager, "_remove_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(
        engine_manager, "subprocess", types.SimpleNamespace(Popen=_fake_popen, DEVNULL=-3)
    )

    engine_manager.start()  # no workers arg -> default
    cmd = captured["cmd"]
    assert cmd[cmd.index("--workers") + 1] == "1"
