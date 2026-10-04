"""Scheduled and file-triggered runs are runs of the one runner (#5372, #5374).

Spec: docs/contributor_manual/specs/ui/activity-and-automatic-work.md:
`activity.run.scheduled-runs-execute` ("a scheduled or file-triggered run executes through the same
path as a run started by hand"; today they pass the stored workflow, whose nodes are dicts, to
`build_graph`, which fails) and `activity.run.one-way-to-run`. The plan names the pin:
`test_scheduled_single_run_executes`. Written from the spec's text, and driven through the public
surface: a schedule created with `POST /api/schedules` and run with its `trigger` route, a file
trigger created with `POST /api/triggers` and fired by a file put in its folder; each run is then
followed with `GET /api/workflow-execution/threads/{thread}/status` and `GET /api/activity/jobs/{id}`.
The workflow is one files source: what is under test is the path a run takes, not a model.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.unit.jobs.test_runs_are_jobs import _status, _tree, _wait_for, no_embedding_model  # noqa: F401


@pytest.fixture
def files_only(db):
    """A workflow of one files source: what a file trigger runs here is the path, not a model."""
    from fichero_server.models import Workflow

    wf = Workflow(id="wf-files-only", name="Note the file", nodes=[
        {"id": "files-source", "tool": "files", "label": "Files", "inputs": {}, "config": {}}], edges=[])
    db.save(wf)
    return wf


def test_scheduled_single_run_executes(client, files_only):
    """Behaviour `activity.run.scheduled-runs-execute`, a schedule: its run executes through the same
    path as a run started by hand (today it fails in `build_graph` on the stored workflow's nodes):
    a run of the runner, with its record (its id is the schedule run's) and its steps, which
    finishes, and the schedule's own run record says so. (A schedule's inputs are strings, so it
    cannot name documents; a workflow of one files source is what it runs here.)"""
    r = client.post("/api/schedules", json={
        "name": "Every night", "workflow_id": files_only.id,
        "config": {"schedule_type": "interval", "interval_seconds": 86400}})
    assert r.status_code == 200, r.text
    schedule_id = r.json()["schedule_id"]
    r = client.post(f"/api/schedules/{schedule_id}/trigger")
    assert r.status_code == 200, r.text
    run_id = r.json()["run_id"]

    def schedule_run():
        runs = client.get(f"/api/schedules/{schedule_id}/runs").json()
        runs = runs.get("items", runs.get("runs", [])) if isinstance(runs, dict) else runs
        return next((run for run in runs if run["run_id"] == run_id), {})

    assert _wait_for(lambda: schedule_run().get("status") in ("completed", "failed"))
    assert schedule_run()["status"] == "completed", schedule_run()
    assert _status(client, run_id) == "completed"
    tree = _tree(client, run_id)
    assert (tree["kind"], tree["state"]) == ("workflow", "done")
    assert [step["subject"].split(":")[-1] for step in tree["children"]] == ["Files"]


def test_scheduled_runs_execute__a_file_trigger_run_is_a_run_of_the_runner(client, db, files_only, tmp_path):
    """Behaviour `activity.run.scheduled-runs-execute`, a file trigger: a file put in a watched folder
    starts a run through the same path as a run started by hand: a run of the runner, with its
    record, which finishes."""
    from fichero_server.workflows.activity import get_activity_tracker

    watched = tmp_path / "inbox"
    watched.mkdir()
    r = client.post("/api/triggers", json={
        "name": "Inbox", "workflow_id": files_only.id, "use_batch": False,
        "config": {"watch_path": str(watched), "events": ["created"], "filter_mode": "extension",
                   "filter_extensions": [".txt"], "debounce_seconds": 0.1, "batch_delay_seconds": 0.2}})
    assert r.status_code == 200, r.text
    trigger_id = r.json()["trigger_id"]
    (watched / "letter.txt").write_text("A letter.", encoding="utf-8")

    def executions():
        return client.get(f"/api/triggers/{trigger_id}/executions").json()["items"]

    assert _wait_for(lambda: any(e["status"] in ("completed", "failed") for e in executions()))
    assert [e["status"] for e in executions()] == ["completed"], executions()
    runs = asyncio.run(get_activity_tracker(str(db.path)).store.list_workflow_runs(limit=10))
    mine = [run for run in runs if run.workflow_id == files_only.id]
    assert len(mine) == 1 and mine[0].status == "completed"
    assert _status(client, mine[0].thread_id) == "completed"
