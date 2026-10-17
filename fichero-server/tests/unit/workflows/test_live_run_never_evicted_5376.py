"""A live run is never dropped from the engine's run registry (#5376, `activity.run.live-run-never-evicted`):
the cap evicts only runs that have exited, so a reopen sweep never fails a run that is still going."""
from __future__ import annotations

from fichero_server.execution import runner


def test_the_cap_never_evicts_a_live_run(monkeypatch):
    monkeypatch.setattr(runner, "_RUNNING_WORKFLOWS_LIMIT", 3)
    monkeypatch.setattr(runner, "_running_workflows", {})
    for n in range(5):
        runner._running_workflows[f"live-{n}"] = {"status": "running"}
    runner._running_workflows["done"] = {"status": "completed"}

    runner._cap_workflow_state_registry()

    assert "done" not in runner._running_workflows, "an exited run goes first"
    assert all(f"live-{n}" in runner._running_workflows for n in range(5)), "no live run is dropped"
