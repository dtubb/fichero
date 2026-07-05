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
    """Remote access TLS keeps one explicit LAN address, never a wildcard."""
    material = prepare_remote_access_tls(
        "https://192.168.1.42:9443",
        storage_root=tmp_path,
    )
    assert material.bind_host == "192.168.1.42"

    with pytest.raises(ValueError, match="non-loopback"):
        resolve_bind_host({"FICHERO_BIND_HOST": material.bind_host})

    with pytest.warns(RuntimeWarning, match="non-loopback host"):
        assert (
            resolve_bind_host(
                {
                    "FICHERO_BIND_HOST": material.bind_host,
                    NON_LOOPBACK_BIND_ACK_ENV: NON_LOOPBACK_BIND_ACK_VALUE,
                }
            )
            == "192.168.1.42"
        )


def test_share_on_never_binds_bare_lan_host() -> None:
    """LAN listener stays off until the explicit host flag is set."""
    assert resolve_lan_bind_host({}) is None


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
