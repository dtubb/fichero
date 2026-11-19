"""The keychain write keeps the secret off argv, `security` is called by absolute path (#4818), and the engine's Unix
socket is 0600 after bind (#6704).

Spec: docs/contributor_manual/specs/compute/runner-reliability.md (`runner.security.*`).
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
from pathlib import Path

from fichero_server import __main__ as engine_main
from fichero_server.security import keychain

SECRET = "sk-test-SECRET-value"


def _capture(monkeypatch):
    runs = []

    def fake_run(cmd, **kw):
        runs.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(keychain, "_is_macos", lambda: True)
    monkeypatch.setattr(keychain, "_invalidate_llm_api_key_cache", lambda provider: None)
    monkeypatch.setattr(keychain.subprocess, "run", fake_run)
    return runs


def test_the_secret_goes_on_stdin_never_argv(monkeypatch):
    runs = _capture(monkeypatch)
    assert keychain.set_api_key("openai", SECRET) is True
    write = [r for r in runs if "add-generic-password" in (r[1].get("input") or "")]
    assert len(write) == 1
    assert SECRET in write[0][1]["input"]
    assert all(SECRET not in " ".join(cmd) for cmd, _ in runs)


def test_security_is_called_by_absolute_path(monkeypatch):
    runs = _capture(monkeypatch)
    keychain.set_api_key("openai", SECRET)
    keychain.delete_api_key("openai")
    assert runs and all(cmd[0] == "/usr/bin/security" for cmd, _ in runs)


def test_a_key_with_a_newline_is_refused_not_run_as_a_second_command(monkeypatch):
    runs = _capture(monkeypatch)
    assert keychain.set_api_key("openai", 'abc"\ndelete-generic-password') is False
    assert not [r for r in runs if "add-generic-password" in (r[1].get("input") or "")]


def test_the_uds_socket_is_0600_after_bind(monkeypatch):
    monkeypatch.setattr("fichero_server.api.uds_claim.claim_uds_path", lambda path: None)
    folder = tempfile.mkdtemp(dir="/tmp", prefix="fsk-")
    old = os.umask(0)  # the worst case: a umask that would leave the socket world-writable
    try:
        sock = engine_main._bind_uds_socket(str(Path(folder) / "e.sock"))
        try:
            assert stat.S_IMODE(os.stat(Path(folder) / "e.sock").st_mode) == 0o600
        finally:
            sock.close()
    finally:
        os.umask(old)
        shutil.rmtree(folder, ignore_errors=True)


def test_httpx_and_httpcore_do_not_log_request_urls_at_info():
    import logging

    assert logging.getLogger("httpx").level == logging.WARNING
    assert logging.getLogger("httpcore").level == logging.WARNING
