"""Updating a workflow writes only what the request sent (#5403).

Found on the Sergio engine (2026-10-03): `fichero workflow update <id> --name … --provider openrouter
--model …` (no --nodes/--edges) left the workflow with 0 nodes and 0 edges. The CLI leaves out what it
was not given, and WorkflowDef's defaults turned the missing graph into empty lists: a rename or a
provider change silently destroyed the workflow.
"""
from __future__ import annotations

import fichero_server.api.routes.workflow.workflows  # noqa: F401  (registers the workflow actions)
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import Workflow

GRAPH = {
    "nodes": [{"id": "files-source", "tool": "files"}, {"id": "transcribe", "tool": "transcribe"}],
    "edges": [{"id": "e1", "source": "files-source", "target": "transcribe",
               "source_port": "files", "target_port": "files"}],
}


def _workflow(db) -> Workflow:
    wf = Workflow(name="Transcribe", format="nodes", provider="openai", model="gpt-4o",
                  nodes=GRAPH["nodes"], edges=GRAPH["edges"])
    db.save(wf)
    return wf


def test_a_provider_change_keeps_the_nodes_and_edges(client, db):
    """WHY (the issue's own case): changing the model a workflow uses must not erase the workflow."""
    wf = _workflow(db)
    r = client.put(f"/api/workflows/{wf.id}", json={
        "name": "Transcribe (Gemini)", "provider": "openrouter", "model": "google/gemini-3-flash-preview"})
    assert r.status_code == 200, r.text
    stored = db.get(Workflow, wf.id)
    assert (stored.name, stored.provider, stored.model) == ("Transcribe (Gemini)", "openrouter",
                                                           "google/gemini-3-flash-preview")
    assert [n["id"] for n in stored.nodes] == ["files-source", "transcribe"] and len(stored.edges) == 1


def test_the_app_saving_an_emptied_graph_still_empties_it(client, db):
    """WHY: the app's editor always sends the whole definition; a person who deleted every node and
    saved must get an empty workflow, not their old graph back. Sent-and-empty is not missing."""
    wf = _workflow(db)
    r = client.put(f"/api/workflows/{wf.id}", json={"name": "Transcribe", "nodes": [], "edges": []})
    assert r.status_code == 200, r.text
    stored = db.get(Workflow, wf.id)
    assert stored.nodes == [] and stored.edges == []


def test_nodes_without_edges_are_refused_and_nothing_changes(client, db):
    """WHY: replacing the nodes but keeping the old edges could leave edges pointing at nodes that are
    gone; the graph is replaced as a whole or not at all, and the refusal says which half was missing."""
    wf = _workflow(db)
    r = client.put(f"/api/workflows/{wf.id}", json={"name": "X", "nodes": [{"id": "only", "tool": "files"}]})
    assert r.status_code == 422 and "nodes and edges together" in r.json()["detail"]
    stored = db.get(Workflow, wf.id)
    assert stored.name == "Transcribe" and len(stored.nodes) == 2


def test_the_update_action_keeps_the_graph_on_a_rename(db, monkeypatch):
    """WHY: `workflow.update` (the audited action the app's undo and agents use) shares this code; its
    name-only updates erased the graph the same way, and undo would then 'restore' an emptied row."""
    monkeypatch.setenv("FICHERO_MULTIUSER", "0")
    wf = _workflow(db)
    registry.invoke(db, "workflow.update", {"workflow_id": wf.id, "workflow": {"name": "Renamed"}},
                    ActionContext(actor="ui", library_path="/tmp/Lib.fichero"))
    stored = db.get(Workflow, wf.id)
    assert stored.name == "Renamed" and len(stored.nodes) == 2 and stored.provider == "openai"
