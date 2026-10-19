"""'Run automatically' keeps working while the person uses the Mac, slower; it holds back fully only on battery,
memory pressure, heat or a build (#5819, `activity.throttle.use-means-slower`).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. Seen live: a Transcribe run sat on
"Waiting: you're using the Mac" for a long time. The throttle's real probes with the Mac's signals faked.
"""
from __future__ import annotations

import pytest

from fichero_server.core import background_compute
from fichero_server.execution import throttle


@pytest.fixture
def mac(monkeypatch):
    """A calm Mac on AC with the throttle on and no build; every signal switchable."""
    state = {"pressure": 1, "thermal": 0, "battery": False, "build": False, "idle": 600.0}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setenv("FICHERO_EMBED_THREADS", "8")
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: state["pressure"])
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 64 * 1024**3)
    monkeypatch.setattr(throttle, "thermal_state_level", lambda: state["thermal"])
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: state["battery"])
    monkeypatch.setattr(throttle, "seconds_since_input", lambda: state["idle"])
    # the probe list holds the function itself, so fake what it reads: a trusted cached reading
    monkeypatch.setattr(throttle, "_build", None)
    monkeypatch.setattr(throttle.subprocess, "run", lambda *a, **k: type(
        "R", (), {"returncode": 0 if state["build"] else 1})())
    monkeypatch.setattr(throttle, "BUILD_READING_SECONDS", 0.0)
    return state


def test_using_the_mac_alone_holds_nothing_back(mac):
    mac["idle"] = 3.0
    assert throttle.why_wait() is None
    assert throttle.why_wait(person_waiting=True) is None


def test_using_the_mac_runs_background_work_with_fewer_workers(mac):
    assert background_compute.embed_threads() == 8
    mac["idle"] = 3.0
    assert background_compute.embed_threads() == 4
    assert throttle.slowed_for_use(1) == 1  # never fewer than one


@pytest.mark.parametrize("change,sentence", [
    ({"battery": True}, "Waiting: the Mac is on battery"),
    ({"pressure": 4}, throttle.MEMORY_REASON),
    ({"thermal": 2}, "Waiting: the Mac is hot"),
    ({"build": True}, "Waiting: a build is running"),
])
def test_each_of_the_four_holds_background_work_with_its_sentence(mac, change, sentence):
    mac["idle"] = 3.0  # in use as well: use does not matter, the hold does
    mac.update(change)
    assert throttle.why_wait().startswith(sentence)


def test_leaving_the_hold_resumes(mac):
    mac["build"] = True
    assert throttle.why_wait() == "Waiting: a build is running"
    mac["build"] = False
    assert throttle.why_wait() is None


def test_a_build_does_not_hold_work_a_person_waits_for(mac):
    mac["build"] = True
    assert throttle.why_wait(person_waiting=True) is None
