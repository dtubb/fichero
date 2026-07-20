from __future__ import annotations

from pathlib import Path
import types

import pytest
import typer

from fichero.bind_host import (
    DEFAULT_BIND_HOST,
    LAN_BIND_HOST_ENV,
    NON_LOOPBACK_BIND_ACK_ENV,
    NON_LOOPBACK_BIND_ACK_VALUE,
    PUBLIC_URL_ENV,
    resolve_bind_host,
    resolve_lan_bind_host,
)
from fichero.cli import engine_manager
from fichero.remote_access_tls import prepare_remote_access_tls


def _fake_popen_factory(captured: dict[str, list[str]]):
    class _FakeProc:
        pid = 4242

    def _fake_popen(cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        return _FakeProc()

    return _fake_popen


def test_resolve_bind_host_defaults_to_loopback() -> None:
    assert resolve_bind_host({}) == DEFAULT_BIND_HOST


def test_resolve_bind_host_accepts_loopback_variants() -> None:
    assert resolve_bind_host({"FICHERO_BIND_HOST": "localhost"}) == "localhost"
    assert resolve_bind_host({"FICHERO_BIND_HOST": "::1"}) == "::1"


def test_resolve_bind_host_rejects_non_loopback_without_ack() -> None:
    with pytest.raises(ValueError, match="non-loopback"):
        resolve_bind_host({"FICHERO_BIND_HOST": "100.64.12.34"})


def test_resolve_bind_host_accepts_non_loopback_with_explicit_ack() -> None:
    with pytest.warns(RuntimeWarning, match="non-loopback host"):
        assert (
            resolve_bind_host(
                {
                    "FICHERO_BIND_HOST": "100.64.12.34",
                    NON_LOOPBACK_BIND_ACK_ENV: NON_LOOPBACK_BIND_ACK_VALUE,
                }
            )
            == "100.64.12.34"
        )


def test_resolve_bind_host_refuses_wildcard_without_ack() -> None:
    with pytest.raises(ValueError, match=r"0\.0\.0\.0 is not allowed"):
        resolve_bind_host({"FICHERO_BIND_HOST": "0.0.0.0"})


def test_resolve_bind_host_accepts_wildcard_with_explicit_ack() -> None:
    with pytest.warns(RuntimeWarning, match="non-loopback host"):
        assert (
            resolve_bind_host(
                {
                    "FICHERO_BIND_HOST": "0.0.0.0",
                    NON_LOOPBACK_BIND_ACK_ENV: NON_LOOPBACK_BIND_ACK_VALUE,
                }
            )
            == "0.0.0.0"
        )


def test_resolve_bind_host_refuses_ipv6_blanket_wildcard() -> None:
    with pytest.raises(ValueError, match="FICHERO_BIND_HOST=:: is not allowed"):
        resolve_bind_host({"FICHERO_BIND_HOST": "::"})


def test_share_off_defaults_to_loopback() -> None:
    """Without a public base URL (share OFF), the engine stays on loopback."""
    assert resolve_bind_host({}) == DEFAULT_BIND_HOST


def test_share_on_uses_wildcard_only_with_ack(tmp_path: Path) -> None:
    """Sharing keeps the engine on loopback; the public URL is perimeter only."""
    material = prepare_remote_access_tls(
        "https://192.168.1.42:9443",
        storage_root=tmp_path,
    )
    assert material.bind_host == DEFAULT_BIND_HOST


def test_share_on_never_binds_bare_lan_host() -> None:
    """LAN listener stays off until the explicit host flag is set."""
    assert resolve_lan_bind_host({}) is None


def test_public_base_url_keeps_primary_bind_on_loopback() -> None:
    assert (
        resolve_bind_host(
            {
                PUBLIC_URL_ENV: "https://fichero.tail123.ts.net",
                "FICHERO_BIND_HOST": "100.64.12.34",
                NON_LOOPBACK_BIND_ACK_ENV: NON_LOOPBACK_BIND_ACK_VALUE,
            }
        )
        == DEFAULT_BIND_HOST
    )


def test_resolve_lan_bind_host_requires_explicit_ack() -> None:
    with pytest.raises(ValueError, match="non-loopback"):
        resolve_lan_bind_host({LAN_BIND_HOST_ENV: "192.168.1.42"})


def test_resolve_lan_bind_host_accepts_specific_non_loopback_host() -> None:
    with pytest.warns(RuntimeWarning, match="non-loopback host"):
        assert (
            resolve_lan_bind_host(
                {
                    LAN_BIND_HOST_ENV: "192.168.1.42",
                    NON_LOOPBACK_BIND_ACK_ENV: NON_LOOPBACK_BIND_ACK_VALUE,
                }
            )
            == "192.168.1.42"
        )


def test_resolve_lan_bind_host_refuses_wildcard() -> None:
    with pytest.raises(ValueError, match=r"0\.0\.0\.0 is not allowed"):
        resolve_lan_bind_host(
            {
                LAN_BIND_HOST_ENV: "0.0.0.0",
                NON_LOOPBACK_BIND_ACK_ENV: NON_LOOPBACK_BIND_ACK_VALUE,
            }
        )


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost"])
def test_resolve_lan_bind_host_refuses_loopback_addresses(host: str) -> None:
    """The LAN listener is the *second* socket; loopback is already the first.

    Pointing it back at loopback would silently give you one socket where the
    operator asked for two, so it must raise rather than quietly collapse.
    """
    with pytest.raises(ValueError, match="must be a non-loopback address"):
        resolve_lan_bind_host(
            {
                LAN_BIND_HOST_ENV: host,
                NON_LOOPBACK_BIND_ACK_ENV: NON_LOOPBACK_BIND_ACK_VALUE,
            }
        )


def test_resolve_bind_host_treats_unresolvable_names_as_non_loopback() -> None:
    """A DNS name is not an IP literal, so the loopback check must fall through.

    `_is_loopback_host` swallows the ValueError from `ip_address()` and answers
    False, which is what forces a hostname down the ack-required path instead of
    being mistaken for a safe loopback bind.
    """
    with pytest.raises(ValueError, match="non-loopback"):
        resolve_bind_host({"FICHERO_BIND_HOST": "pairing.example.com"})


def test_start_uses_resolved_bind_host_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    monkeypatch.setenv("FICHERO_BIND_HOST", "127.0.0.1")
    monkeypatch.setenv("FICHERO_TLS_CERTFILE", "/tmp/fichero-test.crt")
    monkeypatch.setenv("FICHERO_TLS_KEYFILE", "/tmp/fichero-test.key")
    monkeypatch.setattr(engine_manager, "_read_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_write_pid", lambda _pid: None)
    monkeypatch.setattr(engine_manager, "_remove_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(
        engine_manager,
        "subprocess",
        types.SimpleNamespace(Popen=_fake_popen_factory(captured), DEVNULL=-3),
    )

    engine_manager.start()

    cmd = captured["cmd"]
    host_index = cmd.index("--host")
    assert cmd[host_index + 1] == "127.0.0.1"


def test_start_includes_tls_args_when_env_set(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    monkeypatch.setenv("FICHERO_TLS_CERTFILE", "/tmp/fichero-test.crt")
    monkeypatch.setenv("FICHERO_TLS_KEYFILE", "/tmp/fichero-test.key")
    monkeypatch.setattr(engine_manager, "_read_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_write_pid", lambda _pid: None)
    monkeypatch.setattr(engine_manager, "_remove_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(
        engine_manager,
        "subprocess",
        types.SimpleNamespace(Popen=_fake_popen_factory(captured), DEVNULL=-3),
    )

    engine_manager.start()

    cmd = captured["cmd"]
    assert "--ssl-certfile" in cmd
    assert "--ssl-keyfile" in cmd
    assert cmd[cmd.index("--ssl-certfile") + 1] == "/tmp/fichero-test.crt"
    assert cmd[cmd.index("--ssl-keyfile") + 1] == "/tmp/fichero-test.key"


def test_start_refuses_plain_http_without_tls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The engine must not have a plain-HTTP bind path (#2606)."""
    captured: dict[str, list[str]] = {}

    monkeypatch.delenv("FICHERO_TLS_CERTFILE", raising=False)
    monkeypatch.delenv("FICHERO_TLS_KEYFILE", raising=False)
    monkeypatch.setattr(engine_manager, "_read_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_write_pid", lambda _pid: None)
    monkeypatch.setattr(engine_manager, "_remove_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(
        engine_manager,
        "subprocess",
        types.SimpleNamespace(Popen=_fake_popen_factory(captured), DEVNULL=-3),
    )

    with pytest.raises(typer.Exit):
        engine_manager.start()

    assert captured.get("cmd") is None


# --- UDS transport (S2, additive behind FICHERO_UDS_PATH) --------------------


def _install_start_stubs(
    monkeypatch: pytest.MonkeyPatch, captured: dict[str, list[str]]
) -> None:
    monkeypatch.setattr(engine_manager, "_read_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_write_pid", lambda _pid: None)
    monkeypatch.setattr(engine_manager, "_remove_pid", lambda: None)
    monkeypatch.setattr(engine_manager, "_wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(
        engine_manager,
        "subprocess",
        types.SimpleNamespace(Popen=_fake_popen_factory(captured), DEVNULL=-3),
    )


def test_engine_binds_uds_without_tls_when_path_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With FICHERO_UDS_PATH the launch builds a --uds command, no TLS, no port."""
    captured: dict[str, list[str]] = {}
    uds = tmp_path / "f.sock"

    monkeypatch.setenv("FICHERO_UDS_PATH", str(uds))
    # No TLS env set on purpose: UDS is exempt from the TLS requirement.
    monkeypatch.delenv("FICHERO_TLS_CERTFILE", raising=False)
    monkeypatch.delenv("FICHERO_TLS_KEYFILE", raising=False)
    _install_start_stubs(monkeypatch, captured)

    engine_manager.start()

    cmd = captured["cmd"]
    assert "--uds" in cmd
    assert cmd[cmd.index("--uds") + 1] == str(uds)
    assert cmd[-1] != "fichero.api.main:app"
    assert "fichero.api.uds_transport:app" in cmd
    assert "--host" not in cmd
    assert "--port" not in cmd
    assert "--ssl-certfile" not in cmd
    assert "--ssl-keyfile" not in cmd


def test_engine_still_requires_tls_for_tcp_without_uds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without FICHERO_UDS_PATH the TCP path still refuses to launch sans TLS."""
    captured: dict[str, list[str]] = {}

    monkeypatch.delenv("FICHERO_UDS_PATH", raising=False)
    monkeypatch.delenv("FICHERO_TLS_CERTFILE", raising=False)
    monkeypatch.delenv("FICHERO_TLS_KEYFILE", raising=False)
    _install_start_stubs(monkeypatch, captured)

    with pytest.raises(typer.Exit):
        engine_manager.start()

    assert captured.get("cmd") is None


def test_uds_socket_is_unlinked_before_bind() -> None:
    """A pre-existing file at the UDS path is removed before bind (no EADDRINUSE)."""
    import os as _os
    import socket as _socket
    import tempfile

    from engine.__main__ import _bind_uds_socket

    # A SHORT path: AF_UNIX sun_path is capped at ~104 bytes, so pytest's long
    # tmp_path cannot host a socket. Build a short dir under the system tmp.
    short_dir = tempfile.mkdtemp(prefix="fu", dir="/tmp")
    path = Path(short_dir) / "s.sock"
    path.write_text("stale")  # a regular file here would block bind() if not unlinked

    sock = _bind_uds_socket(str(path))
    try:
        assert sock.family == _socket.AF_UNIX
        assert path.exists()  # now a real, bound socket
    finally:
        sock.close()
        path.unlink(missing_ok=True)
        _os.rmdir(short_dir)


def _make_request(scope_extra: dict | None = None, client=None):
    from starlette.requests import Request

    scope: dict = {
        "type": "http",
        "method": "GET",
        "path": "/api/private",
        "headers": [],
    }
    if client is not None:
        scope["client"] = client
    if scope_extra:
        scope.update(scope_extra)
    return Request(scope)


def test_uds_request_is_treated_as_loopback_owner() -> None:
    from fichero.api.auth import _is_loopback_request

    # UDS marker -> trusted as loopback-owner.
    marked = _make_request(scope_extra={"fichero.transport": "uds"}, client=None)
    assert _is_loopback_request(marked) is True

    # No marker + client is None -> NOT loopback (must not key off client None).
    no_client = _make_request(client=None)
    assert _is_loopback_request(no_client) is False

    # No marker + non-loopback TCP client -> NOT loopback.
    tcp = _make_request(client=("192.0.2.10", 5000))
    assert _is_loopback_request(tcp) is False
