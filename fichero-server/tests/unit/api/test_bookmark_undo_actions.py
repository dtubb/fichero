from __future__ import annotations

import fichero_server.api.routes.system.actions_registry  # noqa: F401
import fichero_server.api.routes.system.bookmarks  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, DocType, Document


def test_bookmark_create_is_undoable_via_document_delete(client, db):
    target = Document(id="target-undo", name="Target Undo", doc_type=DocType.file)
    db.save(target)

    response = client.post(
        "/api/bookmarks",
        json={"target_id": target.id, "name": "Undo Bookmark"},
    )

    assert response.status_code == 201
    bookmark_id = response.json()["id"]
    audit = db.all(ActionAudit)[-1]
    assert audit.action_name == "bookmark.create"
    assert audit.target_ids == [bookmark_id]
    assert audit.after["id"] == bookmark_id

    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None
    inverse_name, inverse_params = reg.invert(
        audit.before,
        audit.after,
        ActionContext(actor="ui", library_path=str(db.path.parent)),
    )
    assert inverse_name == "document.delete"

    inverse = registry.invoke(
        db,
        inverse_name,
        inverse_params,
        ActionContext(actor="ui", library_path=str(db.path.parent)),
    )

    bookmark = db.get(Document, bookmark_id)
    assert bookmark is not None
    assert bookmark.deleted_at is not None
    inverse_audit = db.get(ActionAudit, inverse.audit_id)
    assert inverse_audit is not None
    assert inverse_audit.action_name == "document.delete"
