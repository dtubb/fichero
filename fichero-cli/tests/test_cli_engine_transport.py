"""`fichero engine start` transport selection: UDS vs TLS TCP (#4227).

`engine_manager.start` is the one place in this product that chooses a
*transport* rather than a base URL. The two invariants worth a test, both
security-relevant:

* `FICHERO_UDS_PATH` set → uvicorn on a Unix-domain socket, no port, no TLS
  flags (there is no network listener to protect).
* no UDS → TLS is MANDATORY. Missing cert/key must abort, never fall back to
  plaintext HTTP on a TCP port.

Nothing here spawns a process: `subprocess.Popen` is replaced with a recorder,
so the assertions are about the argv that would be launched.
"""

from __future__ import annotations

import subprocess

import pytest
import typer

from fichero_cli import engine_manager


class _FakePopen:
    """Records the argv it was handed instead of launching anything."""

    calls: list[list[str]] = []

    def __init__(self, argv, **kwargs):
        type(self).calls.append(list(argv))
        self.pid = 4242
        self.kwargs = kwargs


@pytest.fixture
def launched(monkeypatch, tmp_path):
    _FakePopen.calls = []
    monkeypatch.setattr(subprocess, "Popen", _FakePopen)
    # Keep PID bookkeeping and port polling out of the developer's home dir.
    monkeypatch.setattr(engine_manager, "PID_FILE", tmp_path / "engine.pid")
    monkeypatch.setattr(engine_manager, "_wait_for_port", lambda *a, **k: True)
    return _FakePopen.calls


def _argv(calls) -> list[str]:
    assert len(calls) == 1, f"expected exactly one launch, got {calls}"
    return calls[0]


def test_uds_path_launches_the_uds_transport_without_tls(
    launched, monkeypatch, tmp_path
):
    socket_path = tmp_path / "fichero.sock"
    monkeypatch.setenv("FICHERO_UDS_PATH", str(socket_path))

    engine_manager.start(port=8765)

    argv = _argv(launched)
    assert "fichero_server.api.uds_transport:app" in argv
    assert argv[argv.index("--uds") + 1] == str(socket_path)
    assert "--port" not in argv
    assert "--ssl-certfile" not in argv and "--ssl-keyfile" not in argv


def test_stale_socket_is_unlinked_before_bind(launched, monkeypatch, tmp_path):
    socket_path = tmp_path / "fichero.sock"
    socket_path.write_text("stale", encoding="utf-8")
    monkeypatch.setenv("FICHERO_UDS_PATH", str(socket_path))

    engine_manager.start()

    # A leftover socket file from a crashed run makes the re-bind fail with
    # EADDRINUSE, so start() must remove it first.
    assert not socket_path.exists()


def test_tcp_start_without_tls_material_aborts(launched, monkeypatch):
    with pytest.raises(typer.Exit) as excinfo:
        engine_manager.start(port=8765)

    assert excinfo.value.exit_code == 1
    assert launched == [], "no server may be launched without TLS"


def test_tcp_start_with_tls_uses_the_tcp_transport(launched, monkeypatch, tmp_path):
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    cert.write_text("cert", encoding="utf-8")
    key.write_text("key", encoding="utf-8")
    monkeypatch.setenv("FICHERO_TLS_CERTFILE", str(cert))
    monkeypatch.setenv("FICHERO_TLS_KEYFILE", str(key))

    engine_manager.start(port=8799)

    argv = _argv(launched)
    assert "fichero_server.api.tcp_transport:app" in argv
    assert argv[argv.index("--port") + 1] == "8799"
    assert argv[argv.index("--host") + 1] == "127.0.0.1"
    assert argv[argv.index("--ssl-certfile") + 1] == str(cert)
    assert argv[argv.index("--ssl-keyfile") + 1] == str(key)
    assert "--uds" not in argv


def test_engine_always_starts_single_process(launched, monkeypatch, tmp_path):
    """DuckDB is single-writer and the change-stream hub is in-process."""
    monkeypatch.setenv("FICHERO_UDS_PATH", str(tmp_path / "fichero.sock"))

    engine_manager.start(workers=4)

    argv = _argv(launched)
    assert argv[argv.index("--workers") + 1] == "1"
