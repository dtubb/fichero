"""A live run is never dropped from the engine's run registry (#5376, `activity.run.live-run-never-evicted`): the cap
drops finished runs only, so the reopen sweep never fails a run that is still going."""
from fichero_server.execution import runner


def test_the_cap_drops_finished_runs_and_keeps_live_ones(monkeypatch):
    monkeypatch.setattr(runner, "_RUNNING_WORKFLOWS_LIMIT", 2)
    monkeypatch.setattr(runner, "_running_workflows", {
        "live-1": {"status": "running"}, "done": {"status": "completed"},
        "live-2": {"status": "running"}, "live-3": {"status": "running"}})
    runner._cap_workflow_state_registry()
    assert "done" not in runner._running_workflows
    assert {"live-1", "live-2", "live-3"} <= set(runner._running_workflows)


def test_with_only_live_runs_the_registry_stands_above_its_cap(monkeypatch):
    monkeypatch.setattr(runner, "_RUNNING_WORKFLOWS_LIMIT", 1)
    monkeypatch.setattr(runner, "_running_workflows", {"a": {"status": "running"}, "b": {"status": "accepted"}})
    runner._cap_workflow_state_registry()
    assert set(runner._running_workflows) == {"a", "b"}
