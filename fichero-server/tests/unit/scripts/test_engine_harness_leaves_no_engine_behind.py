"""`scripts/_engine_harness.EngineProcess` never leaves an engine behind (the Air, 2026-10-30).

Four `python -m uvicorn fichero_server.api.uds_transport:app --uds /tmp/fich_uds_*` from check scripts that died
had sat on the Air since Oct 24 at 1.5-1.7 GB each: 6.4 GB of an 8 GB Mac, the reason it was swapping while the
maintainer ran a recipe. Three guards, each tested with a stand-in child (no real engine: the Pro is under a gate):
the starter stops its engines at exit; it stops them on SIGTERM; and the engine ends itself when its starter is
SIGKILLed (no atexit runs then).
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[3] / "scripts" / "_engine_harness.py"


def _gone(pid: int, seconds: float = 8.0) -> bool:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        # a child of a dead starter is reparented, so waitpid is not ours; `kill 0` is the test
        time.sleep(0.05)
    return False


#: A starter: imports the harness, launches a long sleeper the way `start_engine` does (the parent watch, its own
#: group, registered as live), prints the child's pid, then does what `MODE` says.
_STARTER = textwrap.dedent("""
    import os, subprocess, sys, time, signal
    sys.path.insert(0, {harness_dir!r})
    import _engine_harness as h
    h._install_hooks()
    cmd = [sys.executable, "-c", h._WATCH_THE_PARENT.replace("from uvicorn.main import main\\nmain()", "time.sleep(600)")]
    proc = subprocess.Popen(cmd, start_new_session=True)
    ep = h.EngineProcess(proc, token="t", base_path="/tmp/x")
    print(proc.pid, flush=True)
    mode = sys.argv[1]
    if mode == "exit":
        sys.exit(0)            # atexit stops it
    time.sleep(600)            # 'signal': SIGTERM stops it; 'kill': SIGKILL, the child notices its parent is gone
""").format(harness_dir=str(HARNESS.parent))


def _start(mode: str) -> tuple[subprocess.Popen, int]:
    starter = subprocess.Popen([sys.executable, "-c", _STARTER, mode], stdout=subprocess.PIPE, text=True)
    child_pid = int(starter.stdout.readline().strip())
    return starter, child_pid


def test_the_engine_is_stopped_when_the_starter_exits():
    starter, child = _start("exit")
    starter.wait(10)
    assert _gone(child), "the engine outlived a starter that exited normally"


def test_the_engine_is_stopped_when_the_starter_is_terminated():
    starter, child = _start("signal")
    time.sleep(0.3)
    starter.send_signal(signal.SIGTERM)
    starter.wait(10)
    assert _gone(child), "the engine outlived a starter that was SIGTERMed"


def test_the_engine_is_stopped_on_ctrl_c_through_atexit():
    """Ctrl-C is KeyboardInterrupt, not a handler of ours: the engine stops because atexit runs."""
    starter, child = _start("signal")
    time.sleep(0.3)
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler
    starter.send_signal(signal.SIGINT)
    starter.wait(10)
    assert _gone(child), "the engine outlived Ctrl-C"


def test_the_engine_ends_itself_when_the_starter_is_killed():
    """SIGKILL runs no atexit and no handler: the child's own parent watch is the only guard, as on the Air."""
    starter, child = _start("kill")
    time.sleep(0.3)
    starter.kill()
    starter.wait(10)
    assert _gone(child), "the engine outlived a starter that was SIGKILLed"


@pytest.mark.parametrize("transport", ["uds", "tcp"])
def test_start_engine_launches_in_its_own_group_with_the_parent_watch(monkeypatch, transport):
    """What `start_engine` passes to Popen: the watch wrapper, its own session."""
    sys.path.insert(0, str(HARNESS.parent))
    import _engine_harness as h

    seen = {}

    class _Proc:
        pid = 4242
        returncode = 0

        def poll(self):
            return 0

    def popen(cmd, **kwargs):
        seen["cmd"], seen["kwargs"] = cmd, kwargs
        return _Proc()

    monkeypatch.setattr(h.subprocess, "Popen", popen)
    monkeypatch.setattr(h, "refuse_real_base", lambda *_: None, raising=False)
    with pytest.raises(RuntimeError, match="exited early"):
        h.start_engine(transport=transport, base_path="/tmp/fich_base_test", ready_timeout=1)
    assert seen["kwargs"]["start_new_session"] is True
    assert seen["cmd"][1:3] == ["-c", h._WATCH_THE_PARENT]
