"""This Mac's state in the Activity popover (`activity.popover.summary`, #5415).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md. The popover says whether
heavy work is held back and why; it needs the Mac's memory pressure, heat, battery and use, read
from the engine. `GET /api/activity/jobs` serves them as `machine`, read through the SAME
readings the throttle (`execution/throttle.py`) acts on.

The Mac's signals are faked at the throttle's readings (not at its probes), so one fake moves
both the probe that holds work and the state the popover shows: if the two ever read the Mac
by different paths, these tests fail.
"""
from __future__ import annotations

import pytest

from fichero_server.execution import throttle


@pytest.fixture
def mac(monkeypatch):
    """A calm Mac on AC, idle, with the throttle on (the suite turns it off by default)."""
    state = {"pressure": 1, "thermal": 0, "battery": False, "idle": 600.0}
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: state["pressure"])
    monkeypatch.setattr(throttle, "thermal_state_level", lambda: state["thermal"])
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: state["battery"])
    monkeypatch.setattr(throttle, "seconds_since_input", lambda: state["idle"])
    return state


def _machine(client):
    response = client.get("/api/activity/jobs")
    assert response.status_code == 200
    return response.json()["machine"]


def test_activity_popover_summary__the_jobs_route_carries_the_macs_state_with_its_types(client, mac):
    """WHY: the app decodes `machine` through the generated client; a missing key or a wrong
    type (a level as a number, a bool as a string) breaks the popover, not a test, unless the
    real route is pinned here."""
    machine = _machine(client)
    assert machine == {
        "memory_pressure": "normal",
        "thermal_state": "nominal",
        "on_battery": False,
        "in_use": False,
        "why_wait": None,
    }


@pytest.mark.parametrize("change,field,shown", [
    ({"pressure": 2}, "memory_pressure", "warn"),
    ({"pressure": 4}, "memory_pressure", "critical"),
    ({"thermal": 1}, "thermal_state", "fair"),
    ({"thermal": 2}, "thermal_state", "serious"),
    ({"thermal": 3}, "thermal_state", "critical"),
    ({"battery": True}, "on_battery", True),
    ({"idle": 3.0}, "in_use", True),
])
def test_activity_popover_summary__a_tight_hot_battery_or_busy_mac_shows(client, mac, change, field, shown):
    """WHY: each level must reach the popover as the Mac reports it, so the person sees what
    the throttle sees (memory warn vs critical, fair vs serious heat)."""
    mac.update(change)
    assert _machine(client)[field] == shown


@pytest.mark.parametrize("change", [
    {"pressure": 2}, {"pressure": 4}, {"thermal": 2}, {"thermal": 3}, {"battery": True}, {"idle": 3.0},
    {"thermal": 1}, {},
])
def test_activity_popover_summary__why_wait_is_the_throttles_own_reason(client, mac, change):
    """WHY: the popover's "held back because" must be the reason a waiting job is given, never
    a second guess; a fair (not serious) heat or a calm Mac holds nothing back."""
    mac.update(change)
    assert _machine(client)["why_wait"] == throttle.why_wait()
    if change in ({"thermal": 1}, {}):
        assert _machine(client)["why_wait"] is None


def test_activity_popover_summary__the_first_reason_wins_as_in_the_throttle(client, mac):
    """WHY: with memory tight AND the Mac on battery, a job waits on memory (it is the one
    that makes the Mac beachball); the popover must give the same one."""
    mac.update({"pressure": 4, "battery": True})
    machine = _machine(client)
    assert machine["why_wait"] == throttle.MEMORY_REASON
    assert machine["on_battery"] is True


def test_activity_popover_summary__an_unreadable_mac_reads_as_no_level_and_holds_nothing(client, mac):
    """WHY: off macOS or under a sandbox refusal the levels are unknown, not "normal": the
    popover must not claim a calm Mac it never read, and nothing is held back."""
    mac.update({"pressure": None, "thermal": None, "idle": None})
    machine = _machine(client)
    assert machine["memory_pressure"] is None
    assert machine["thermal_state"] is None
    assert machine["in_use"] is False
    assert machine["why_wait"] is None
