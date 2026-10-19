"""#5358: the engine reports its own memory and energy from the OS (macOS); elsewhere None."""
import sys

import pytest

from fichero_server.core import background_compute as bc


@pytest.mark.skipif(sys.platform != "darwin", reason="proc_pid_rusage is macOS")
def test_rusage_reports_memory_and_energy_then_watts():
    usage = bc.process_rusage()
    assert usage["memory_bytes"] > 0 and usage["energy_nj"] > 0
    bc._energy_last_sample = None
    assert bc.process_energy_watts() is None  # primes
    sum(i * i for i in range(2_000_000))
    assert bc.process_energy_watts() > 0


@pytest.mark.skipif(sys.platform != "darwin", reason="proc_pid_rusage is macOS")
def test_the_buffer_is_the_whole_v6_struct():
    """The kernel writes all of rusage_info_v6 (464 bytes, sys/resource.h); a shorter buffer is overwritten past its end."""
    import ctypes

    bc.process_rusage()
    assert ctypes.sizeof(bc._libproc[1]) == 464 and len(bc._libproc) == 2


def test_rusage_is_none_off_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert bc.process_rusage() is None and bc.process_energy_watts() is None


@pytest.mark.skipif(sys.platform != "darwin", reason="proc_pid_rusage is macOS")
def test_the_tree_includes_a_running_child(monkeypatch):
    """A child that works counts: the tree's memory is more than this process alone, and the child is found."""
    import subprocess

    child = subprocess.Popen([sys.executable, "-c", "import time; x = bytearray(80_000_000); time.sleep(5)"])
    try:
        import time

        time.sleep(1)
        import subprocess

        def no_subprocess(*a, **k):
            raise AssertionError("the tree is read without a subprocess")

        monkeypatch.setattr(subprocess, "run", no_subprocess)
        monkeypatch.setattr(subprocess, "Popen", no_subprocess)
        assert child.pid in bc._descendant_pids(__import__("os").getpid())
        assert bc.process_tree_rusage()["memory_bytes"] >= bc.process_rusage()["memory_bytes"] + 50_000_000
    finally:
        child.kill()
        child.wait()
