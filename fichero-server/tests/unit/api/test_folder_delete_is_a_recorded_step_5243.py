"""`safety.trash.no-hard-delete-by-folder` (#5243): deleting a folder of workflows, searches or chats is a recorded step.

WHY: `DELETE /api/folders/{kind}/folders?delete_contents=true` called `db.delete` on every item: no audit row, no inverse, no
way back, for a whole folder in one click. It now deletes each item through the kind's own audited action, so every item
has a record and an undo.
"""

from __future__ import annotations

import pytest

import fichero_server.api.routes.search.core  # noqa: F401  (registers savedsearch.*)
import fichero_server.api.routes.system.chat  # noqa: F401  (registers conversation.*)
import fichero_server.api.routes.workflow.workflows  # noqa: F401  (registers workflow.*)
from fichero_server.models import ActionAudit, Conversation, SavedSearch, Workflow

KINDS = [
    ("workflow", Workflow, "workflow.delete", lambda: Workflow(name="W", folder_path="/box")),
    ("search", SavedSearch, "savedsearch.delete", lambda: SavedSearch(name="S", query="x", folder_path="/box")),
    ("conversation", Conversation, "conversation.delete", lambda: Conversation(title="C", folder_path="/box")),
]


@pytest.mark.parametrize(("kind", "model", "action", "make"), KINDS, ids=[k[0] for k in KINDS])
def test_deleting_a_folder_with_contents_records_each_item_and_undo_brings_it_back(client, db, kind, model, action, make):
    item = make()
    db.save(item)

    response = client.delete(f"/api/folders/{kind}/folders", params={"folder_path": "/box", "delete_contents": "true"})
    assert response.status_code == 200, response.text
    assert response.json()["deleted_count"] == 1
    assert db.get(model, item.id) is None

    audits = db.query(ActionAudit, action_name=action)
    assert len(audits) == 1, "the delete must leave a record"
    undone = client.post(f"/api/actions/audit/{audits[0].id}/undo")
    assert undone.status_code == 200, undone.text
    assert db.get(model, item.id) is not None, "undo puts the item back"
