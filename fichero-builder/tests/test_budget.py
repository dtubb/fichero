"""dev-workflows.run.watch-tick: free memory before a job, a spawn cap, backoff with jitter."""
from __future__ import annotations

import pytest

from fichero_builder import budget


def test_room_for_refuses_critical_pressure_and_short_memory():
    ok, why = budget.room_for("pi", {"pi": 0}, {"free_mb": 50000, "pressure": "critical", "load1": 1})
    assert not ok and "critical" in why
    ok, why = budget.room_for("pi", {"pi": 1000}, {"free_mb": 100, "pressure": "normal", "load1": 1})
    assert not ok and why == "pi needs 1000 MB, 100 MB free"
    assert budget.room_for("pi", {"pi": 1000}, {"free_mb": 9000, "pressure": "normal", "load1": 1})[0]


def test_backoff_grows_with_full_jitter_and_a_cap():
    assert [budget.backoff(i, rng=lambda: 1.0) for i in range(6)] == [2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
    assert [budget.backoff(3, rng=lambda: 0.0), budget.backoff(3, rng=lambda: 0.5)] == [8.0, 12.0]
    assert budget.backoff(20, rng=lambda: 1.0) == 120.0


def test_never_spawns_past_the_cap():
    sp = budget.Spawns({"coders": 1, "test_runs": 1})
    sp.add("coders", "coder-a")
    assert sp.can("coders", "coder-b") == (False, "coders cap 1 reached")
    assert sp.can("coders", "coder-a") == (False, "coders coder-a already running")
    with pytest.raises(RuntimeError):
        sp.add("coders", "coder-b")
    sp.remove("coders", "coder-a")
    assert sp.can("coders", "coder-b")[0]


def test_machine_reads_this_mac():
    m = budget.machine()
    assert m["free_mb"] >= 0 and m["pressure"] in ("normal", "warn", "critical", "?") and m["load1"] >= 0
