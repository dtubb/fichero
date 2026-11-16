"""`workflows.requires-vision-unknown` (docs/contributor_manual/specs/ui/workflows.md, Step 1.6, #4506): the SERVED
`requires_vision` is true, false, or null (could not be determined), so the route no longer spends "unknown" as "no".

WHY: an unresolvable sub-workflow came back as False, the permissive answer, on a guess. The app treats null as "may need a
vision model" and shows the model picker (manager ruling 2026-11-02).
"""

from __future__ import annotations

from fichero_server.models import Workflow


def _served(client, db, name, nodes):
    wf = Workflow(name=name, format="nodes", nodes=nodes)
    db.save(wf)
    items = {i["id"]: i for i in client.get("/api/workflows").json()["items"]}
    return items[wf.id]


def test_an_unresolvable_sub_workflow_is_served_as_null(client, db):
    item = _served(client, db, "Delegates to nothing",
                   [{"id": "s", "tool": "sub_workflow", "config": {"workflow_ref": "no-such-workflow"}}])
    assert item["requires_vision"] is None


def test_a_workflow_that_needs_vision_is_true_and_one_that_does_not_is_false(client, db):
    assert _served(client, db, "Reads pictures", [{"id": "t", "tool": "transcribe"}])["requires_vision"] is True
    assert _served(client, db, "Text only", [{"id": "s", "tool": "summarize_file"}])["requires_vision"] is False
