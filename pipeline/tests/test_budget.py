"""pipeline.machine-budget (Stage 0: a free-memory check, one test run at a time, a spawn cap, backoff)."""
from __future__ import annotations

import fcntl
import threading
import time

import pytest

from pipeline import budget, journal


def test_item_waits_with_reason_when_memory_is_short(scratch, issues, fake_coder, monkeypatch):
    from pipeline import core
    fake_coder()
    readings = iter([{"free_mb": 100, "pressure": "normal", "load1": 1.0}, {"free_mb": 100, "pressure": "normal", "load1": 1.0},
                     {"free_mb": 9000, "pressure": "normal", "load1": 1.0}])
    monkeypatch.setattr(budget, "machine", lambda: next(readings, {"free_mb": 9000, "pressure": "normal", "load1": 1.0}))
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    scratch["cfg"]["workers"]["needs_mb"] = {"pi": 1000, "pytest": 0}
    assert core.start([1001])["items"]["1001"] == "checked"
    waits = [e for e in journal.read() if e["event"] == "wait"]
    assert len(waits) == 2 and "pi needs 1000 MB, 100 MB free" in waits[0]["text"]


def test_room_for_refuses_critical_pressure():
    ok, why = budget.room_for("pi", {"pi": 0}, {"free_mb": 50000, "pressure": "critical", "load1": 1})
    assert not ok and "critical" in why


def test_429_backs_off_with_growing_delays():
    delays = [budget.backoff(i, rng=lambda: 1.0) for i in range(6)]
    assert delays == [2.0, 4.0, 8.0, 16.0, 32.0, 64.0]
    jittered = [budget.backoff(3, rng=lambda: 0.0), budget.backoff(3, rng=lambda: 0.5)]
    assert jittered == [8.0, 12.0], "full jitter between half and the whole delay"
    assert budget.backoff(20, rng=lambda: 1.0) == 120.0, "capped"


def test_second_test_run_waits_on_the_lock(scratch):
    with journal.Lock("test-run"):
        with pytest.raises(BlockingIOError):
            with journal.Lock("test-run", wait=False):
                pass
        got = []

        def second():
            with journal.Lock("test-run"):
                got.append(time.time())

        t = threading.Thread(target=second)
        t.start()
        time.sleep(0.3)
        assert got == [], "the second run is still waiting"
        released = time.time()
    t.join(2)
    assert got and got[0] >= released


def test_never_spawns_past_the_cap():
    sp = budget.Spawns({"coders": 1, "test_runs": 1})
    sp.add("coders", "coder-a")
    assert sp.can("coders", "coder-b") == (False, "coders cap 1 reached")
    assert sp.can("coders", "coder-a") == (False, "coders coder-a already running"), "de-duplicated"
    with pytest.raises(RuntimeError):
        sp.add("coders", "coder-b")
    sp.remove("coders", "coder-a")
    assert sp.can("coders", "coder-b")[0]


def test_coder_cap_refuses_a_second_live_coder(scratch, issues, fake_coder, monkeypatch):
    from pipeline import core
    fake_coder()
    journal.append("worker", window="coder-other", task="other", role="coder", model="m", session_dir="s", cwd="")
    monkeypatch.setattr(core.coder, "status", lambda d: {"idle": False, "cost_usd": 0.0, "last_text": "", "turns": 0, "context": 0})
    monkeypatch.setattr(core.coder, "live_windows", lambda cfg: {"coder-other"})
    with pytest.raises(RuntimeError, match="coder cap"):
        core.start([1001])
    # a window that died no longer counts (review MED 15)
    monkeypatch.setattr(core.coder, "live_windows", lambda cfg: set())
    assert core.start([1001])["items"]["1001"] == "checked"
    assert any(e["event"] == "worker_gone" and e["window"] == "coder-other" for e in journal.read())


def test_lock_is_a_real_flock(scratch):
    with journal.Lock("x") as lk, open(lk.p) as other:
        with pytest.raises(BlockingIOError):
            fcntl.flock(other.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
