"""Direct tests for cli/engine_manager.py process helpers (#1982 Test Coverage).

`_is_process_alive` and `_get_uptime` underpin `status`/`stop`/`restart` but had
no direct test. Cover the liveness signal branches and the uptime subprocess
fallback (lsof -> ps -> None) without spawning real engine processes.
"""

from __future__ import annotations

import os
import subprocess
import types

from fichero_cli import engine_manager as em


# ---------------------------------------------------------------------------
# _is_process_alive
# ---------------------------------------------------------------------------


def test_is_process_alive_true_for_current_process() -> None:
    # The test process itself is, by definition, alive.
    assert em._is_process_alive(os.getpid()) is True


def test_is_process_alive_false_when_process_missing(monkeypatch) -> None:
    def _raise(_pid, _sig):
        raise ProcessLookupError

    monkeypatch.setattr(em.os, "kill", _raise)
    assert em._is_process_alive(424242) is False


def test_is_process_alive_false_on_oserror(monkeypatch) -> None:
    # e.g. a permission error probing another user's process -> treated as not
    # signalable/alive by this helper.
    def _raise(_pid, _sig):
        raise OSError("EPERM")

    monkeypatch.setattr(em.os, "kill", _raise)
    assert em._is_process_alive(1) is False


# ---------------------------------------------------------------------------
# _get_uptime — lsof gate, then ps -o etime=
# ---------------------------------------------------------------------------


def _run_result(returncode: int, stdout: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(returncode=returncode, stdout=stdout)


def test_get_uptime_returns_ps_etime_when_available(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_run(cmd, **_kwargs):
        calls.append(cmd)
        if cmd[0] == "lsof":
            return _run_result(0, "header\nproc info")
        if cmd[0] == "ps":
            return _run_result(0, "  01:23:45  \n")
        raise AssertionError(cmd)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert em._get_uptime(123) == "01:23:45"
    assert calls[0][0] == "lsof" and calls[1][0] == "ps"


def test_get_uptime_none_when_ps_etime_blank(monkeypatch) -> None:
    def fake_run(cmd, **_kwargs):
        if cmd[0] == "lsof":
            return _run_result(0)
        return _run_result(0, "   \n")  # ps returns whitespace only

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert em._get_uptime(123) is None


def test_get_uptime_none_when_lsof_missing(monkeypatch) -> None:
    def fake_run(cmd, **_kwargs):
        raise FileNotFoundError("lsof not installed")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert em._get_uptime(123) is None


def test_get_uptime_none_when_lsof_nonzero(monkeypatch) -> None:
    # lsof present but reports the pid as unknown -> never reaches ps -> None.
    def fake_run(cmd, **_kwargs):
        if cmd[0] == "lsof":
            return _run_result(1)
        raise AssertionError("ps should not run when lsof fails")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert em._get_uptime(123) is None


def test_get_uptime_none_when_ps_times_out(monkeypatch) -> None:
    def fake_run(cmd, **_kwargs):
        if cmd[0] == "lsof":
            return _run_result(0)
        raise subprocess.TimeoutExpired(cmd, 2)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert em._get_uptime(123) is None
