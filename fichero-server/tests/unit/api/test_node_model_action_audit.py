"""Audit coverage for node-model fold create mutations (#1848 / #2591).

Lean by design: prove the audited action path where it exists, and pin the
current bypasses as strict xfails for manager follow-up.
"""

from __future__ import annotations

import fichero_server.api.routes.bookmarks  # noqa: F401
import fichero_server.api.routes.claim.claims  # noqa: F401
import fichero_server.api.routes.document.documents  # noqa: F401
import fichero_server.api.routes.entity.entities  # noqa: F401
import fichero_server.api.routes.document.notes  # noqa: F401
import fichero_server.api.routes.search  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity, NoteKind
from fichero_server.models import ActionAudit, DocType, Document


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


def _audits_for_target(db, target_id: str) -> list[ActionAudit]:
    return [row for row in db.all(ActionAudit) if target_id in (row.target_ids or [])]


def test_saved_search_create_action_writes_action_audit(db):
    result = registry.invoke(
        db,
        "savedsearch.save",
        {"query": "Asprilla", "folder_path": "/people"},
        _ctx(),
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "ui"
    assert audit.action_name == "savedsearch.save"
    assert audit.target_ids == [result.result["id"]]


def test_note_create_action_writes_action_audit(db):
    folder = Document(name="Folder", doc_type=DocType.folder)
    db.save(folder)

    result = registry.invoke(
        db,
        "note.create",
        {
            "title": "Fold note",
            "body": "captured by audit",
            "kind": NoteKind.zettel.value,
            "folder_id": folder.id,
        },
        _ctx(),
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "ui"
    assert audit.action_name == "note.create"
    assert audit.target_ids == [result.result["id"]]


def test_claim_create_action_writes_action_audit(db):
    result = registry.invoke(
        db,
        "claim.create",
        {"text": "Manual claim from action layer"},
        _ctx(),
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "ui"
    assert audit.action_name == "claim.create"
    assert audit.target_ids == [result.result["id"]]


def test_claim_patch_action_writes_action_audit(db):
    claim = KnowledgeClaim(text="Before patch")
    db.save(claim)

    result = registry.invoke(
        db,
        "claim.patch",
        {"claim_id": claim.id, "patch": {"text": "After patch"}},
        _ctx(),
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "ui"
    assert audit.action_name == "claim.patch"
    assert audit.target_ids == [claim.id]


def test_claim_delete_action_writes_action_audit(db):
    claim = KnowledgeClaim(text="Delete me")
    db.save(claim)

    result = registry.invoke(db, "claim.delete", {"claim_id": claim.id}, _ctx())

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "ui"
    assert audit.action_name == "claim.delete"
    assert audit.target_ids == [claim.id]


def test_document_create_action_writes_action_audit(db):
    result = registry.invoke(
        db,
        "document.create",
        {"name": "Action Doc"},
        _ctx(),
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "ui"
    assert audit.action_name == "document.create"
    assert audit.target_ids == [result.result["id"]]


def test_folder_create_action_writes_action_audit(db):
    result = registry.invoke(
        db,
        "document.create",
        {"name": "Action Folder", "doc_type": "folder"},
        _ctx(),
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "ui"
    assert audit.action_name == "document.create"
    assert audit.target_ids == [result.result["id"]]


def test_document_move_action_writes_action_audit(db):
    parent = Document(name="Parent", doc_type=DocType.folder)
    child = Document(name="Child", doc_type=DocType.file)
    db.save(parent)
    db.save(child)

    result = registry.invoke(
        db,
        "document.move",
        {"doc_id": child.id, "parent_id": parent.id},
        _ctx(),
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "ui"
    assert audit.action_name == "document.move"
    assert audit.target_ids == [child.id]


def test_document_delete_action_writes_action_audit(db):
    doc = Document(name="Delete Doc", doc_type=DocType.file)
    db.save(doc)

    result = registry.invoke(db, "document.delete", {"doc_id": doc.id}, _ctx())

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "ui"
    assert audit.action_name == "document.delete"
    assert audit.target_ids == [doc.id]


def test_entity_create_action_writes_action_audit(db):
    result = registry.invoke(
        db,
        "entity.create",
        {"canonical_name": "Asprilla"},
        _ctx(),
    )

    audit = db.get(ActionAudit, result.audit_id)
    assert audit is not None
    assert audit.actor == "ui"
    assert audit.action_name == "entity.create"
    assert audit.target_ids == [result.result["id"]]


def test_saved_search_create_route_writes_action_audit(client, db):
    response = client.post(
        "/api/search/saved",
        json={"query": "Asprilla", "folder_path": "/people"},
    )
    assert response.status_code == 200

    saved_id = response.json()["id"]
    audits = _audits_for_target(db, saved_id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "savedsearch.save"
    assert audits[0].target_ids == [saved_id]


def test_note_create_route_writes_action_audit(client, db):
    folder = Document(name="Folder", doc_type=DocType.folder)
    db.save(folder)

    response = client.post(
        "/api/notes",
        json={
            "title": "Route note",
            "body": "created via HTTP",
            "kind": NoteKind.zettel.value,
            "folder_id": folder.id,
        },
    )
    assert response.status_code == 200

    note_id = response.json()["id"]
    audits = _audits_for_target(db, note_id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "note.create"
    assert audits[0].target_ids == [note_id]


def test_claim_create_route_writes_action_audit(client, db):
    response = client.post("/api/claims", json={"text": "Route claim"})
    assert response.status_code == 200

    claim_id = response.json()["id"]
    audits = _audits_for_target(db, claim_id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "claim.create"
    assert audits[0].target_ids == [claim_id]


def test_claim_patch_route_writes_action_audit(client, db):
    claim = KnowledgeClaim(text="Before route patch")
    db.save(claim)

    response = client.patch(f"/api/claims/{claim.id}", json={"text": "After route patch"})
    assert response.status_code == 200

    audits = _audits_for_target(db, claim.id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "claim.patch"
    assert audits[0].target_ids == [claim.id]


def test_claim_delete_route_writes_action_audit(client, db):
    claim = KnowledgeClaim(text="Delete via route")
    db.save(claim)

    response = client.delete(f"/api/claims/{claim.id}")
    assert response.status_code == 204

    audits = _audits_for_target(db, claim.id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "claim.delete"
    assert audits[0].target_ids == [claim.id]


def test_bookmark_create_route_writes_action_audit(client, db):
    target = Document(name="Target", doc_type=DocType.file)
    db.save(target)

    response = client.post(
        "/api/bookmarks",
        json={"target_id": target.id, "name": "Bookmark"},
    )
    assert response.status_code == 201

    bookmark_id = response.json()["id"]
    audits = _audits_for_target(db, bookmark_id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "bookmark.create"
    assert audits[0].target_ids == [bookmark_id]


def test_document_create_route_writes_action_audit(client, db):
    response = client.post("/api/documents", json={"name": "Route Doc"})
    assert response.status_code == 201

    doc_id = response.json()["id"]
    audits = _audits_for_target(db, doc_id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "document.create"
    assert audits[0].target_ids == [doc_id]


def test_folder_create_route_writes_action_audit(client, db):
    response = client.post(
        "/api/documents",
        json={"name": "Route Folder", "doc_type": "folder"},
    )
    assert response.status_code == 201

    folder_id = response.json()["id"]
    audits = _audits_for_target(db, folder_id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "document.create"
    assert audits[0].target_ids == [folder_id]


def test_document_move_route_writes_action_audit(client, db):
    parent = Document(name="Route Parent", doc_type=DocType.folder)
    child = Document(name="Route Child", doc_type=DocType.file)
    db.save(parent)
    db.save(child)

    response = client.put(f"/api/documents/{child.id}/move?parent_id={parent.id}")
    assert response.status_code == 200

    audits = _audits_for_target(db, child.id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "document.move"
    assert audits[0].target_ids == [child.id]


def test_document_delete_route_writes_action_audit(client, db):
    doc = Document(name="Route Delete Doc", doc_type=DocType.file)
    db.save(doc)

    response = client.delete(f"/api/documents/{doc.id}")
    assert response.status_code == 204

    audits = _audits_for_target(db, doc.id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "document.delete"
    assert audits[0].target_ids == [doc.id]


def test_entity_create_route_writes_action_audit(client, db):
    response = client.post("/api/entities", json={"canonical_name": "Asprilla"})
    assert response.status_code == 200

    entity_id = response.json()["id"]
    audits = _audits_for_target(db, entity_id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "entity.create"
    assert audits[0].target_ids == [entity_id]


def test_entity_patch_route_writes_action_audit(client, db):
    entity = KnowledgeEntity(canonical_name="Before Patch")
    db.save(entity)

    response = client.patch(
        f"/api/entities/{entity.id}",
        json={"canonical_name": "After Patch"},
    )
    assert response.status_code == 200

    audits = _audits_for_target(db, entity.id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "entity.update"
    assert audits[0].target_ids == [entity.id]


def test_entity_delete_route_writes_action_audit(client, db):
    entity = KnowledgeEntity(canonical_name="Delete Me")
    db.save(entity)

    response = client.delete(f"/api/entities/{entity.id}")
    assert response.status_code == 204

    audits = _audits_for_target(db, entity.id)
    assert len(audits) == 1
    assert audits[0].actor == "owner"
    assert audits[0].action_name == "entity.delete"
    assert audits[0].target_ids == [entity.id]


def test_milestone_create_writes_action_audit(db):
    parent = Document(name="Parent Folder", doc_type=DocType.folder)
    db.save(parent)

    result = registry.invoke(
        db,
        "milestone.create",
        {"title": "Phase 1", "parent_id": parent.id, "status": "active"},
        _ctx(),
    )

    milestone_id = result.result["id"]
    audits = _audits_for_target(db, milestone_id)
    assert len(audits) == 1
    assert audits[0].actor == "ui"
    assert audits[0].action_name == "milestone.create"
    assert audits[0].target_ids == [milestone_id]
