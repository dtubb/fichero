"""A step of a run a person started is never held for the Mac being in use or on battery (#6263,
`runner.mac.stays-usable`): the throttle's one decision (`throttle.decide`) says go or slow, never hold, and only memory
or heat holds it. The Mac's signals are faked at the throttle's readings."""
from __future__ import annotations

import pytest

from fichero_server.execution import throttle


@pytest.fixture
def mac(monkeypatch):
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.setattr(throttle, "_started", lambda: False)
    monkeypatch.setattr(throttle, "memory_pressure_level", lambda: 1)
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 64 * 1024**3)
    monkeypatch.setattr(throttle, "thermal_state_level", lambda: 0)
    monkeypatch.setattr(throttle, "seconds_since_input", lambda: 1.0)  # in use
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: True)
    monkeypatch.setattr(throttle, "a_build_is_running", lambda: None)


@pytest.mark.parametrize("model", [None, "kraken:blla", "omlx:some-model"])
def test_a_started_runs_step_is_never_held_while_the_mac_is_in_use_and_on_battery(mac, model):
    assert throttle.why_wait(person_waiting=True, model=model) is None
    assert throttle.decide(True, model=model).action != "hold"


def test_automatic_work_in_the_same_state_is_held_for_battery_and_a_started_runs_is_not(mac):
    assert throttle.decide(False).action == "hold"
    assert throttle.decide(True).action == "slow"  # on battery: slower, begun at once


def test_a_started_runs_step_still_holds_for_memory_and_says_why(mac, monkeypatch):
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 1024**3)
    decision = throttle.decide(True)
    assert decision.action == "hold" and "memory is tight" in decision.reason
