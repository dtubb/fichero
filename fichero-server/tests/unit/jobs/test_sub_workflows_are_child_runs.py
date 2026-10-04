"""A sub-workflow is a child run of the step that called it: Stop and Pause reach it (#5375, #5374).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md: `activity.run.stop-reaches-sub-workflows`
("Stop and Pause reach a sub-workflow. Today the child gets its own task id, so its cancel check is
never true") and "What is deleted": a sub-workflow's `ainvoke` becomes "a child run job of the step
that called it, so pause, cancel and the record reach it". Written from the spec's text, and driven
through the public surface: a parent run started with `POST /api/workflow-execution/execute`, Stop
and Pause pressed on its row, and its tree read with `GET /api/activity/jobs/{run}`. Only the model is
a stub: a cloud vision model that answers from memory.
"""
from __future__ import annotations

import threading
import time

import pytest

from fichero_server.execution import jobs
from tests.unit.jobs.test_runs_are_jobs import (  # noqa: F401
    _execute, _status, _tree, _wait_for, cloud, no_embedding_model, pages, workflow,
)


@pytest.fixture
def parent(db, workflow):
    """A workflow of one step: the cloud transcription workflow, called as a sub-workflow."""
    from fichero_server.models import Workflow

    wf = Workflow(id="wf-parent", name="Transcribe, as a part", provider="openai", model="gpt-5", nodes=[
        {"id": "part", "tool": "sub_workflow", "label": "Transcribe part", "inputs": {},
         "config": {"workflow_ref": workflow.id}}], edges=[])
    db.save(wf)
    return wf


def _pages_under(tree):
    found = []
    for child in tree["children"]:
        found += [child] if child["kind"] == "read-a-page" else _pages_under(child)
    return found


def test_activity_jobs_are_a_tree__a_sub_workflow_is_a_child_run_of_its_step(client, parent, pages, cloud):
    """Spec, "What is deleted": a sub-workflow is "a child run job of the step that called it". The
    parent's step holds the child run, the child run its steps, and they its pages, which roll up
    to the parent run."""
    run = _execute(client, parent, pages)
    assert _wait_for(lambda: _status(client, run) in ("completed", "failed"))
    assert _status(client, run) == "completed"
    tree = _tree(client, run)
    [step] = tree["children"]
    assert step["subject"].endswith("Transcribe part")
    [child] = step["children"]
    assert child["kind"] == "workflow" and child["state"] == "done"
    assert {s["subject"].split(":")[-1] for s in child["children"]} == {"Files", "Transcribe"}
    assert len(_pages_under(tree)) == 3 and (tree["done"], tree["total"]) == (3, 3)


def test_activity_run_stop_reaches_sub_workflows__stop_on_the_parent_reaches_the_childs_pages(
        client, parent, pages, cloud, monkeypatch):
    """Behaviour `activity.run.stop-reaches-sub-workflows`: "Stop ... reach[es] a sub-workflow." With
    the network lane one wide and the child's first page held, Stop on the PARENT run's row ends
    the run, and the child's waiting pages never call the model."""
    monkeypatch.setitem(jobs.LANES, "network", 1)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    cloud.gate = threading.Event()
    run = _execute(client, parent, pages)
    try:
        assert cloud.first_call.wait(30)
        assert _wait_for(lambda: sum(1 for p in _pages_under(_tree(client, run)) if p["state"] == "waiting") == 2)
        assert client.post(f"/api/activity/jobs/{run}/cancel").status_code == 200
    finally:
        cloud.gate.set()
    assert _wait_for(lambda: _status(client, run) == "cancelled")
    time.sleep(0.3)
    assert cloud.calls == 1


def test_activity_run_stop_reaches_sub_workflows__pause_on_the_parent_holds_the_child(
        client, parent, pages, cloud, monkeypatch):
    """Behaviour `activity.run.stop-reaches-sub-workflows`: "Stop and Pause reach a sub-workflow."
    With the child's first page held, Pause on the parent's row holds the child: its pages still
    waiting never call the model, and the parent says paused."""
    monkeypatch.setitem(jobs.LANES, "network", 1)
    monkeypatch.setattr(jobs, "_scheduler", jobs._Scheduler())
    cloud.gate = threading.Event()
    run = _execute(client, parent, pages)
    try:
        assert cloud.first_call.wait(30)
        r = client.put(f"/api/activity/jobs/{run}/paused", json={"paused": True})
        assert r.status_code == 200, r.text
    finally:
        cloud.gate.set()
    assert _wait_for(lambda: _status(client, run) == "paused")
    time.sleep(0.5)
    assert cloud.calls == 1
