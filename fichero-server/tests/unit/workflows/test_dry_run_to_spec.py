"""`workflows.canvas.dry-run` (docs/contributor_manual/specs/ui/workflows.md, Step 2.3, #4370): a workflow can be tested before a
real run is spent. `POST /api/workflow-execution/dry-run` asks the same checks `/execute` makes and answers every problem in words,
with the steps and which call a model. It starts no run, calls no model and writes nothing.
"""

from __future__ import annotations

from fichero_server.models import Workflow


def _dry(client, workflow, **extra):
    return client.post("/api/workflow-execution/dry-run", json={"workflow_id": workflow.id, **extra})


def test_a_workflow_that_would_run_is_ok_and_lists_its_steps(client, db):
    wf = Workflow(name="Just files", format="nodes", nodes=[{"id": "f", "tool": "files", "label": "Files"}])
    db.save(wf)
    r = _dry(client, wf)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["problems"] == []
    assert [(s["node_id"], s["tool"], s["uses_model"]) for s in body["steps"]] == [("f", "files", False)]
    assert body["model_steps"] == 0 and body["scope"] == "per_file"


def test_a_step_with_a_required_input_nothing_feeds_is_a_problem_in_words(client, db):
    wf = Workflow(name="Unfed", format="nodes", nodes=[{"id": "r", "tool": "text_reflow", "label": "Reflow"}])
    db.save(wf)
    body = _dry(client, wf).json()
    assert body["ok"] is False and any("Required input port 'text'" in p for p in body["problems"])


def test_a_workflow_with_no_steps_says_so_instead_of_starting(client, db):
    wf = Workflow(name="Empty", format="nodes", nodes=[])
    db.save(wf)
    body = _dry(client, wf).json()
    assert body["ok"] is False and any("no nodes" in p for p in body["problems"])


def test_it_asks_the_same_checks_as_execute_and_agrees_with_it(client, db):
    wf = Workflow(name="Empty again", format="nodes", nodes=[])
    db.save(wf)
    refused = client.post("/api/workflow-execution/execute", json={"workflow_id": wf.id})
    assert refused.status_code == 400
    assert all(p in refused.json()["detail"] for p in _dry(client, wf).json()["problems"])


def test_a_dry_run_starts_no_run(client, db):
    wf = Workflow(name="Text only 2", format="nodes", nodes=[{"id": "r", "tool": "text_reflow"}])
    db.save(wf)
    before = client.get("/api/workflow-execution/runs").json()
    _dry(client, wf)
    assert client.get("/api/workflow-execution/runs").json() == before


def test_an_unknown_workflow_is_a_404(client):
    assert client.post("/api/workflow-execution/dry-run", json={"workflow_id": "nope"}).status_code == 404
