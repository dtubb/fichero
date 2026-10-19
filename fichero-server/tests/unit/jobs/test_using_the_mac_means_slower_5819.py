"""'Run automatically' keeps working while the person uses the Mac, slower; it holds back fully only on battery,
memory pressure, heat or a build (#5819, `activity.throttle.use-means-slower`).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. Seen live: a Transcribe run sat on
"Waiting: you're using the Mac" for a long time. The throttle's real probes with the Mac's signals faked.
"""
from __future__ import annotations

import re

import pytest

from fichero_server.execution import throttle


@pytest.fixture
def mac(monkeypatch):
    """A calm Mac on AC with the throttle on and no build; every signal switchable."""
    state = {"pressure": 1, "thermal": 0, "battery": False, "procs": [], "calls": [], "idle": 600.0}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: state["pressure"])
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 64 * 1024**3)
    monkeypatch.setattr(throttle, "thermal_state_level", lambda: state["thermal"])
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: state["battery"])
    monkeypatch.setattr(throttle, "seconds_since_input", lambda: state["idle"])
    # The probe list holds the function itself, so fake what it reads. The build reading is cached for 10 s: clear it
    # here and make every read stale (a negative age limit), so a test that toggles a process between two
    # `why_wait()` calls sees the toggle (review 206).
    monkeypatch.setattr(throttle, "_build", None)
    monkeypatch.setattr(throttle, "BUILD_READING_SECONDS", -1.0)

    def pgrep(cmd, **kwargs):  # pgrep -x <regex>: a process whose whole name matches
        state["calls"].append((cmd, kwargs))
        found = any(re.fullmatch(cmd[2], name) for name in state["procs"])
        return type("R", (), {"returncode": 0 if found else 1})()

    monkeypatch.setattr(throttle.subprocess, "run", pgrep)
    return state


def test_using_the_mac_alone_holds_nothing_back(mac):
    mac["idle"] = 3.0
    assert throttle.why_wait() is None
    assert throttle.why_wait(person_waiting=True) is None


@pytest.mark.parametrize("change,sentence", [
    ({"battery": True}, "Waiting: the Mac is on battery"),
    ({"pressure": 4}, throttle.MEMORY_REASON),
    ({"thermal": 2}, "Waiting: the Mac is hot"),
    ({"procs": ["swift-frontend"]}, "Waiting: a build is running"),
])
def test_each_of_the_four_holds_background_work_with_its_sentence(mac, change, sentence):
    mac["idle"] = 3.0  # in use as well: use does not matter, the hold does
    mac.update(change)
    assert throttle.why_wait().startswith(sentence)


def test_leaving_the_hold_resumes(mac):
    mac["procs"] = ["xcodebuild"]
    assert throttle.why_wait() == "Waiting: a build is running"
    mac["procs"] = []
    assert throttle.why_wait() is None


def test_a_build_does_not_hold_work_a_person_waits_for(mac):
    mac["procs"] = ["xcodebuild"]
    assert throttle.why_wait(person_waiting=True) is None


def test_xcode_open_is_not_a_build(mac):
    """Review 200: SWBBuildService lives as long as Xcode is open; only what runs while compiling is a build."""
    mac["procs"] = ["Xcode", "SWBBuildService", "XCBBuildService"]
    assert throttle.why_wait() is None


@pytest.mark.parametrize("name", ["xcodebuild", "swift-build", "swift-frontend", "clang"])
def test_each_compiling_process_is_a_build(mac, name):
    mac["procs"] = [name]
    assert throttle.why_wait() == "Waiting: a build is running"


def test_one_pgrep_with_a_short_timeout(mac):
    mac["procs"] = []
    throttle.why_wait()
    assert len(mac["calls"]) == 1 and mac["calls"][0][1]["timeout"] == 1
