"""#5819: Find Lines slept between pages whenever "you're using the Mac" or "a build is running". Work the person
started waits only for memory and heat; any work goes slower, never stops, while the Mac is used or a build runs.

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md (`activity.throttle.use-means-slower`).
The throttle's real probes with the Mac's signals faked; the pages have no image, so only the waiting is exercised.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fichero_server.execution import jobs, throttle
from fichero_server.recipes import regions


@pytest.fixture
def mac(monkeypatch):
    state = {"build": False, "idle": 600.0, "battery": False, "pressure": 1, "sleeps": []}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: state["pressure"])
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 64 * 1024**3)
    monkeypatch.setattr(throttle, "thermal_state_level", lambda: 0)
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: state["battery"])
    monkeypatch.setattr(throttle, "seconds_since_input", lambda: state["idle"])
    # "in use" is no longer a probe of why_wait; the run must not stop for it if one reports it (a build, or in use)
    monkeypatch.setattr(throttle, "a_build_is_running", lambda: throttle.BUILD_REASON if state["build"] else None)
    monkeypatch.setattr(throttle, "PROBES", [(throttle.memory_is_tight, True), (throttle.mac_is_hot, True),
                                             (throttle.on_battery, False), (throttle.mac_is_in_use, False),
                                             (throttle.a_build_is_running, False)])
    monkeypatch.setattr(regions.time, "sleep", lambda seconds: state["sleeps"].append(seconds))
    return state


def _find_lines(monkeypatch, tmp_path, person: bool, pages: int = 3, stop_after_sleeps: int = 50):
    monkeypatch.setattr(jobs, "person_waits_on", lambda _db, _id: person)
    said = []
    db = SimpleNamespace(path=tmp_path / "lib" / "x.duckdb",
                         get=lambda *_a: SimpleNamespace(path=str(tmp_path / "no-such-image.jpg"), id="d", name="n"))
    account = regions.find_regions(db, [f"d{i}" for i in range(pages)], "run", "m", provider="yolo", say=said.append)
    return account, said


def test_a_person_started_run_over_3_pages_finishes_without_waiting_on_use_or_a_build(mac, monkeypatch, tmp_path):
    mac.update(build=True, idle=1.0)  # the Mac is in use and a build runs
    account, said = _find_lines(monkeypatch, tmp_path, person=True)
    assert account["no_image"] == 3 and mac["sleeps"] == []  # no sleep at all
    assert not any("build" in s or "using the Mac" in s for s in said)


def test_a_background_run_makes_progress_slower_under_a_build_or_use(mac, monkeypatch, tmp_path):
    mac.update(build=True, idle=1.0)
    account, said = _find_lines(monkeypatch, tmp_path, person=False)
    assert account["no_image"] == 3  # all three pages were reached
    assert mac["sleeps"] == [regions.SLOWER_YIELD_SECONDS] * 3  # one short yield per page, never the 5 s wait loop
    assert any("going slower" in s for s in said)


def test_memory_still_holds_a_person_started_run(mac, monkeypatch, tmp_path):
    mac["pressure"] = 4  # critical
    calls = {"n": 0}

    def clears_after_two_sleeps(seconds):
        mac["sleeps"].append(seconds)
        calls["n"] += 1
        if calls["n"] == 2:
            mac["pressure"] = 1

    monkeypatch.setattr(regions.time, "sleep", clears_after_two_sleeps)
    account, _ = _find_lines(monkeypatch, tmp_path, person=True, pages=1)
    assert mac["sleeps"] == [regions.WAIT_POLL_SECONDS] * 2 and account["no_image"] == 1  # held, then went on


def test_battery_still_holds_background_work_but_not_the_person_started_run(mac, monkeypatch, tmp_path):
    mac["battery"] = True
    account, _ = _find_lines(monkeypatch, tmp_path, person=True, pages=2)
    assert mac["sleeps"] == [] and account["no_image"] == 2
