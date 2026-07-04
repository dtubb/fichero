"""Unit tests for the audited research notes action family (#3024 slice 2)."""

from __future__ import annotations

import fichero.api.routes.research_notes  # noqa: F401
from fichero.actions.registry import ActionContext, registry
from fichero.models import ActionAudit
from fichero.research_models import ResearchChecklist, ResearchNote, SearchSource


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


def _undo(db, audit_id: str, ctx: ActionContext):
    audit = db.get(ActionAudit, audit_id)
    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None
    inverse = reg.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    name, params = inverse
    result = registry.invoke(db, name, params, ctx)
    return name, result


def _mk_checklist(db) -> ResearchChecklist:
    checklist = ResearchChecklist(
        project_id="proj-1",
        title="Archive Verification",
        items=[{"id": "item-1", "label": "Verify date", "checked": False}],
    )
    db.save(checklist)
    return checklist


class TestResearchSourceActions:
    def test_create_source_is_undoable(self, db):
        ctx = _ctx()
        created = registry.invoke(
            db,
            "research.source.create",
            {
                "project_id": "proj-1",
                "source_type": "url",
                "label": "National Archives",
                "url": "https://archives.example",
            },
            ctx,
        )
        source_id = created.result.id
        assert db.get(SearchSource, source_id) is not None
        assert db.get(ActionAudit, created.audit_id).action_name == "research.source.create"

        undo_name, _ = _undo(db, created.audit_id, ctx)
        assert undo_name == "research.source.delete"
        assert db.get(SearchSource, source_id) is None

        restore_name, _ = _undo(db, db.all(ActionAudit)[-1].id, ctx)
        assert restore_name == "research.source.restore"
        assert db.get(SearchSource, source_id) is not None


class TestResearchNoteActions:
    def test_create_and_update_note_are_undoable(self, db):
        ctx = _ctx()
        created = registry.invoke(
            db,
            "research.note.create",
            {
                "project_id": "proj-1",
                "content": "Found a concession record.",
                "tags": ["mining"],
            },
            ctx,
        )
        note_id = created.result.id
        assert db.get(ResearchNote, note_id) is not None
        assert _undo(db, created.audit_id, ctx)[0] == "research.note.delete"
        assert db.get(ResearchNote, note_id) is None
        _undo(db, db.all(ActionAudit)[-1].id, ctx)

        updated = registry.invoke(
            db,
            "research.note.update",
            {
                "note_id": note_id,
                "note_type": "finding",
                "tags": ["mining", "1885"],
            },
            ctx,
        )
        note = db.get(ResearchNote, note_id)
        assert note.note_type.value == "finding"
        assert "1885" in note.tags
        assert db.get(ActionAudit, updated.audit_id).action_name == "research.note.update"
        assert _undo(db, updated.audit_id, ctx)[0] == "research.note.restore"
        restored = db.get(ResearchNote, note_id)
        assert restored.note_type.value == "observation"
        assert restored.tags == ["mining"]


class TestResearchChecklistActions:
    def test_create_and_toggle_checklist_are_undoable(self, db):
        ctx = _ctx()
        created = registry.invoke(
            db,
            "research.checklist.create",
            {
                "project_id": "proj-1",
                "title": "Archive Verification",
                "items": [{"id": "item-1", "label": "Verify date", "checked": False}],
            },
            ctx,
        )
        checklist_id = created.result.id
        assert db.get(ResearchChecklist, checklist_id) is not None
        assert _undo(db, created.audit_id, ctx)[0] == "research.checklist.delete"
        assert db.get(ResearchChecklist, checklist_id) is None
        _undo(db, db.all(ActionAudit)[-1].id, ctx)

        updated = registry.invoke(
            db,
            "research.checklist.update",
            {
                "checklist_id": checklist_id,
                "item_id": "item-1",
                "checked": True,
                "notes": "Confirmed",
            },
            ctx,
        )
        item = db.get(ResearchChecklist, checklist_id).items[0]
        assert item.checked is True
        assert item.notes == "Confirmed"
        assert db.get(ActionAudit, updated.audit_id).action_name == "research.checklist.update"
        assert _undo(db, updated.audit_id, ctx)[0] == "research.checklist.restore"
        restored_item = db.get(ResearchChecklist, checklist_id).items[0]
        assert restored_item.checked is False
        assert restored_item.notes == ""


def test_research_note_write_routes_write_action_audit(client, db):
    source = client.post(
        "/api/research/sources",
        json={
            "project_id": "proj-1",
            "source_type": "url",
            "label": "National Archives",
            "url": "https://archives.example",
        },
    )
    assert source.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "research.source.create"

    note = client.post(
        "/api/research/notes",
        json={
            "project_id": "proj-1",
            "note_type": "observation",
            "content": "Observation",
        },
    )
    assert note.status_code == 200
    note_id = note.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "research.note.create"

    patched_note = client.patch(
        f"/api/research/notes/{note_id}",
        json={"content": "Updated", "note_type": "finding"},
    )
    assert patched_note.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "research.note.update"

    checklist = client.post(
        "/api/research/checklists",
        json={
            "project_id": "proj-1",
            "title": "Archive Verification",
            "items": [{"id": "item-1", "label": "Verify date", "checked": False}],
        },
    )
    assert checklist.status_code == 200
    checklist_id = checklist.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "research.checklist.create"

    toggled = client.patch(
        f"/api/research/checklists/{checklist_id}/items/item-1",
        json={"checked": True, "notes": "Confirmed"},
    )
    assert toggled.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "research.checklist.update"
