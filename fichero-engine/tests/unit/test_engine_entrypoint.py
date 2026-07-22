from __future__ import annotations

import json
import signal
import socket
from types import SimpleNamespace

import pytest

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


@pytest.fixture
def _restore_sigpipe():
    """Save and restore the SIGPIPE disposition around a test that changes it."""
    previous = signal.getsignal(signal.SIGPIPE)
    try:
        yield
    finally:
        signal.signal(signal.SIGPIPE, previous)


def test_ignore_sigpipe_installs_sig_ign(_restore_sigpipe) -> None:
    # Start from the terminating default so the assertion proves the helper acts.
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    assert signal.getsignal(signal.SIGPIPE) == signal.SIG_DFL

    backend_main._ignore_sigpipe()

    assert signal.getsignal(signal.SIGPIPE) == signal.SIG_IGN


def test_ignore_sigpipe_is_idempotent(_restore_sigpipe) -> None:
    """Calling the guard twice keeps SIG_IGN — no toggle back to the killer default.

    ``main()`` installs the guard once, but the disposition can also be touched by
    the Briefcase launch wrapper and by asyncio loop setup; a second explicit call
    (or a redundant one on a restart path) must leave SIG_IGN in place, never flip
    back to SIG_DFL. If it did, the very next write to a hung-up peer would deliver
    SIGPIPE and terminate the engine (the "code 13" cascade, #3108).
    """
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    backend_main._ignore_sigpipe()
    backend_main._ignore_sigpipe()

    assert signal.getsignal(signal.SIGPIPE) == signal.SIG_IGN


def test_write_to_hung_up_peer_raises_not_kills(_restore_sigpipe) -> None:
    """With SIGPIPE ignored, writing to a closed peer raises BrokenPipeError.

    This is the exact scenario that was killing the engine: uvicorn writing a
    response to a socket whose peer (the app) already hung up. Under SIG_DFL the
    process receives SIGPIPE and dies (reported as "code 13"); under SIG_IGN the
    write raises EPIPE -> BrokenPipeError, which the caller handles and lives.
    """
    backend_main._ignore_sigpipe()

    left, right = socket.socketpair()
    try:
        # Peer hangs up mid-conversation, exactly like the app dropping the UDS
        # connection after a readiness probe / 401.
        right.close()
        with pytest.raises(BrokenPipeError):
            # Enough writes to overflow the send buffer and force the EPIPE that
            # would otherwise be delivered as SIGPIPE.
            for _ in range(1024):
                left.send(b"x" * 4096)
    finally:
        left.close()

    # The process is still alive and the interpreter still running: reaching
    # this line at all is the assertion — SIGPIPE did not terminate us.
    assert signal.getsignal(signal.SIGPIPE) == signal.SIG_IGN


def test_main_ignores_sigpipe_before_serving(monkeypatch) -> None:
    """main() calls the SIGPIPE guard first, before any socket/server work."""
    calls: list[str] = []

    def _record_and_stop() -> None:
        calls.append("ignore_sigpipe")
        # Abort main() right after the guard so we never spin up a real server;
        # reaching here proves the guard runs before argparse/serving.
        raise RuntimeError("stop after sigpipe guard")

    monkeypatch.setattr(backend_main, "_ignore_sigpipe", _record_and_stop)

    with pytest.raises(RuntimeError, match="stop after sigpipe guard"):
        backend_main.main([])

    assert calls == ["ignore_sigpipe"]


def test_prepare_local_access_flag_prints_manifest_and_returns(monkeypatch, capsys, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_prepare_remote_access_tls(
        public_base_url: str,
        storage_root=None,
        allow_loopback=False,
        subject_alt_hosts=(),
    ):
        captured["public_base_url"] = public_base_url
        captured["storage_root"] = storage_root
        captured["allow_loopback"] = allow_loopback
        captured["subject_alt_hosts"] = tuple(subject_alt_hosts)
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
        "subject_alt_hosts": (),
    }
    assert json.loads(capsys.readouterr().out) == {
        "bind_host": "127.0.0.1",
        "certificate_path": str(tmp_path / "server.crt"),
        "key_path": str(tmp_path / "server.key"),
        "spki_pin": "spki-pin",
    }


def test_prepare_remote_access_flag_prints_manifest_and_returns(monkeypatch, capsys, tmp_path) -> None:
    captured: dict[str, object] = {}

    def fake_prepare_remote_access_tls(
        public_base_url: str,
        storage_root=None,
        allow_loopback=False,
        subject_alt_hosts=(),
    ):
        captured["public_base_url"] = public_base_url
        captured["storage_root"] = storage_root
        captured["allow_loopback"] = allow_loopback
        captured["subject_alt_hosts"] = tuple(subject_alt_hosts)
        return SimpleNamespace(
            bind_host="127.0.0.1",
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
    assert captured["subject_alt_hosts"] == ()
    assert json.loads(capsys.readouterr().out) == {
        "bind_host": "127.0.0.1",
        "certificate_path": str(tmp_path / "server.crt"),
        "key_path": str(tmp_path / "server.key"),
        "spki_pin": "spki-pin",
    }


def test_prepare_local_access_uses_lan_host_as_subject_alt_name(
    monkeypatch, capsys, tmp_path
) -> None:
    captured: dict[str, object] = {}

    def fake_prepare_remote_access_tls(
        public_base_url: str,
        storage_root=None,
        allow_loopback=False,
        subject_alt_hosts=(),
    ):
        captured["public_base_url"] = public_base_url
        captured["storage_root"] = storage_root
        captured["allow_loopback"] = allow_loopback
        captured["subject_alt_hosts"] = tuple(subject_alt_hosts)
        return SimpleNamespace(
            bind_host="127.0.0.1",
            certificate_path=str(tmp_path / "server.crt"),
            key_path=str(tmp_path / "server.key"),
            spki_pin="spki-pin",
        )

    monkeypatch.setattr(backend_main, "prepare_remote_access_tls", fake_prepare_remote_access_tls)
    monkeypatch.setattr(backend_main, "material_manifest_json", _manifest_json)
    monkeypatch.setenv("FICHERO_LAN_HOST", "192.168.1.42")

    backend_main.main(["--prepare-local-access", "--remote-access-dir", str(tmp_path)])

    assert captured["subject_alt_hosts"] == ("192.168.1.42",)
    assert json.loads(capsys.readouterr().out)["spki_pin"] == "spki-pin"
