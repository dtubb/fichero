"""Audited agent workspace membership actions (#3561)."""

from __future__ import annotations

import pytest

from fichero import accounts, authz
from fichero.actions.registry import ActionContext, registry
from fichero.knowledge_models import KnowledgeClaim
from fichero.models import ActionAudit, DocType, Document


def _workspace(db) -> Document:
    workspace = Document(
        name="Agent workspace",
        doc_type=DocType.folder,
        node_kind="workspace",
        is_workspace=True,
        metadata={"workspace_kind": "agent", "message_history_ref": "conversation-1"},
    )
    db.save(workspace)
    return workspace


def _ctx(db, actor: str = "agent") -> ActionContext:
    return ActionContext(actor=actor, library_path=str(db.path.parent))


def _undo(db, result, ctx: ActionContext) -> None:
    audit = db.get(ActionAudit, result.audit_id)
    registration = registry.get(audit.action_name)
    inverse = registration.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    registry.invoke(db, inverse[0], inverse[1], ctx)


def test_add_source_mutates_audits_and_undoes(db):
    workspace = _workspace(db)
    source = Document(name="Source")
    db.save(source)
    ctx = _ctx(db)

    result = registry.invoke(
        db,
        "workspace.add_source",
        {"workspace_id": workspace.id, "document_id": source.id},
        ctx,
    )
    assert db.get(Document, workspace.id).curated_items[0]["target_id"] == source.id
    assert db.get(ActionAudit, result.audit_id).actor == "agent"
    _undo(db, result, ctx)
    assert db.get(Document, workspace.id).curated_items == []


def test_remove_source_mutates_audits_and_undoes(db):
    workspace = _workspace(db)
    source = Document(name="Source")
    db.save(source)
    ctx = _ctx(db)
    registry.invoke(
        db,
        "workspace.add_source",
        {"workspace_id": workspace.id, "document_id": source.id},
        ctx,
    )

    result = registry.invoke(
        db,
        "workspace.remove_source",
        {"workspace_id": workspace.id, "document_id": source.id},
        ctx,
    )
    assert db.get(Document, workspace.id).curated_items == []
    assert db.get(ActionAudit, result.audit_id).action_name == "workspace.remove_source"
    _undo(db, result, ctx)
    assert db.get(Document, workspace.id).curated_items[0]["target_id"] == source.id


def test_surface_claim_mutates_audits_and_undoes(db):
    workspace = _workspace(db)
    claim = KnowledgeClaim(text="The petition was filed in 1844.")
    db.save(claim)
    ctx = _ctx(db)

    result = registry.invoke(
        db,
        "workspace.surface_claim",
        {"workspace_id": workspace.id, "claim_id": claim.id},
        ctx,
    )
    assert db.get(Document, workspace.id).curated_items[0]["target_id"] == claim.id
    assert db.get(ActionAudit, result.audit_id).action_name == "workspace.surface_claim"
    _undo(db, result, ctx)
    assert db.get(Document, workspace.id).curated_items == []


def test_add_note_mutates_audits_and_undoes(db):
    workspace = _workspace(db)
    ctx = _ctx(db)

    result = registry.invoke(
        db,
        "workspace.add_note",
        {"workspace_id": workspace.id, "text": "Check the ledger date."},
        ctx,
    )
    assert db.get(Document, workspace.id).curated_items[0]["notes"] == "Check the ledger date."
    assert db.get(ActionAudit, result.audit_id).action_name == "workspace.add_note"
    _undo(db, result, ctx)
    assert db.get(Document, workspace.id).curated_items == []


def test_workspace_actions_deny_unauthorized_actor(db, app_db, monkeypatch):
    monkeypatch.setenv("FICHERO_MULTIUSER", "1")
    agent = app_db.create_user(
        username="agent", display_name="Agent", password_hash=accounts.hash_password("agent")
    )
    viewer = app_db.create_user(
        username="viewer", display_name="Viewer", password_hash=accounts.hash_password("viewer")
    )
    library_path = str(db.path.parent)
    normalized = authz.normalize_library_path(library_path)
    app_db.set_library_role(user_id=agent.id, library_path=normalized, role="editor")
    app_db.set_library_role(user_id=viewer.id, library_path=normalized, role="viewer")
    workspace = _workspace(db)
    source = Document(name="Source")
    db.save(source)

    with pytest.raises(authz.AuthorizationError):
        registry.invoke(
            db,
            "workspace.add_source",
            {"workspace_id": workspace.id, "document_id": source.id},
            _ctx(db, viewer.username),
        )
