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


def test_rusage_is_none_off_macos(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert bc.process_rusage() is None and bc.process_energy_watts() is None
