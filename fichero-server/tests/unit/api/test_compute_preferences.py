"""The person chooses how hard local model work may push the Mac, and on which processor.

WHY: Kraken ran at one fixed throttle (utility QoS, half the cores) on a fixed device. The maintainer
wants it adjustable: balanced by default so the Mac stays usable, fast when they want a run done (or
a test), background for work nobody waits on; and the CPU/GPU choice too. An environment override
lets a test run go flat out without changing the person's saved choice.
"""
from __future__ import annotations

import pytest

from fichero_server.core import compute_preferences as cp


def test_the_default_is_balanced_on_auto(client):
    body = client.get("/api/settings/compute").json()
    assert (body["priority"], body["device"]) == ("balanced", "auto")


def test_a_saved_choice_applies_and_the_environment_overrides_it_for_a_test_run(client, monkeypatch):
    r = client.put("/api/settings/compute", json={"priority": "background", "device": "cpu"})
    assert r.status_code == 200, r.text
    assert cp.compute_preferences() == {"priority": "background", "device": "cpu"}
    monkeypatch.setenv("FICHERO_COMPUTE_PRIORITY", "fast")
    body = client.get("/api/settings/compute").json()
    assert body["priority"] == "background" and body["effective"]["priority"] == "fast"


def test_an_unknown_choice_is_refused(client):
    assert client.put("/api/settings/compute", json={"priority": "turbo", "device": "auto"}).status_code == 422


@pytest.mark.parametrize("priority, more_threads_than_balanced", [("fast", True), ("background", False)])
def test_priority_sets_the_thread_budget(priority, more_threads_than_balanced):
    import threading

    budgets: dict[str, int] = {}

    def run(name: str) -> None:  # its own thread: the QoS it sets must not slow the test runner
        budgets[name] = cp.apply_to_this_thread(name)

    for name in ("balanced", priority):
        t = threading.Thread(target=run, args=(name,))
        t.start()
        t.join()
    balanced, other = budgets["balanced"], budgets[priority]
    assert (other > balanced) == more_threads_than_balanced or other == balanced == 1


def test_cpu_is_cpu_whatever_the_hardware():
    assert cp.torch_accelerator("cpu") == "cpu"
