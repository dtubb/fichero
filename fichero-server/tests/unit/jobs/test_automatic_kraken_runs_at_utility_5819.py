"""An import's automatic Kraken reading runs at utility QoS with few threads even while the Mac is used; other automatic
work stays at the lowest class (owner ruling 2026-10-20, amends #5819).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md (`activity.throttle.use-means-slower`).
The throttle's use signal and the QoS setters are faked; nothing reads the real Mac.
"""
from __future__ import annotations

import pytest

from fichero_server.core import background_compute as bc
from fichero_server.execution import throttle
from fichero_server.llm import kraken_runtime


@pytest.fixture
def qos(monkeypatch):
    set_to = []
    monkeypatch.setenv("FICHERO_JOB_THROTTLE", "1")
    monkeypatch.delenv("FICHERO_COMPUTE_PRIORITY", raising=False)
    monkeypatch.setattr("fichero_server.core.compute_preferences.stored_preferences",
                        lambda: {"priority": "balanced", "device": "auto"})
    for name, check in (("memory_pressure_level", 1), ("thermal_state_level", 0)):
        monkeypatch.setattr(throttle, name, lambda check=check: check)
    monkeypatch.setattr(throttle, "memory_available_bytes", lambda: 64 * 1024**3)
    monkeypatch.setattr(throttle, "battery_or_low_power", lambda: False)
    monkeypatch.setattr(throttle, "seconds_since_input", lambda: 1.0)  # the Mac is in use
    monkeypatch.setattr(throttle, "a_build_is_running", lambda: None)
    monkeypatch.setattr(bc, "embed_threads", lambda: 4)
    monkeypatch.setattr(bc, "cpu_count", lambda: 8)
    monkeypatch.setattr(bc, "set_background_qos", lambda *a: set_to.append("background"))
    monkeypatch.setattr(bc, "set_utility_qos", lambda: set_to.append("utility"))
    monkeypatch.setattr(bc, "set_fast_qos", lambda: set_to.append("fast"))
    return set_to


def test_automatic_kraken_while_the_mac_is_used_is_utility_with_few_threads(qos):
    priority, label, cores = kraken_runtime.set_page_priority(person=False)
    assert (priority, label, cores) == ("background", "utility", 2)  # embed_threads // 2: the same few threads
    assert qos == ["utility"]


def test_other_automatic_work_in_the_same_state_still_picks_background(qos):
    from fichero_server.core.compute_preferences import apply_to_this_thread, priority_for

    assert priority_for(False) == "background"
    assert apply_to_this_thread("background") == 2 and qos == ["background"]


def test_a_persons_kraken_page_is_still_fast(qos):
    assert kraken_runtime.set_page_priority(person=True) == ("fast", "user-initiated", 8)
    assert qos == ["fast"]
