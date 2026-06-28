"""Audit coverage for node-model fold create mutations (#1848 / #2591).

Lean by design: prove the audited action path where it exists, and pin the
current bypasses as strict xfails for manager follow-up.
"""

from __future__ import annotations

import pytest

import fichero.api.routes.notes  # noqa: F401
import fichero.api.routes.search  # noqa: F401
from fichero.actions.registry import ActionContext, registry
from fichero.knowledge_models import Milestone, NoteKind
from fichero.models import ActionAudit, DocType, Document


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


@pytest.mark.xfail(
    strict=True,
    reason="POST /api/search/saved still calls save_search_impl directly and writes no ActionAudit row.",
)
def test_saved_search_create_route_writes_action_audit(client, db):
    response = client.post(
        "/api/search/saved",
        json={"query": "Asprilla", "folder_path": "/people"},
    )
    assert response.status_code == 200

    saved_id = response.json()["id"]
    audits = _audits_for_target(db, saved_id)
    assert len(audits) == 1
    assert audits[0].actor == "system"
    assert audits[0].action_name == "savedsearch.save"
    assert audits[0].target_ids == [saved_id]


@pytest.mark.xfail(
    strict=True,
    reason="POST /api/notes still calls create_note_impl directly and writes no ActionAudit row.",
)
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
    assert audits[0].actor == "system"
    assert audits[0].action_name == "note.create"
    assert audits[0].target_ids == [note_id]


@pytest.mark.xfail(
    strict=True,
    reason="POST /api/bookmarks creates alias-backed bookmark nodes directly; no bookmark.create audited action exists yet.",
)
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
    assert audits[0].actor == "system"
    assert audits[0].action_name == "bookmark.create"
    assert audits[0].target_ids == [bookmark_id]


@pytest.mark.xfail(
    strict=True,
    reason="Milestones fold into Document rows on db.save, but no milestone.create audited action or route exists yet.",
)
def test_milestone_create_writes_action_audit(db):
    parent = Document(name="Parent Folder", doc_type=DocType.folder)
    db.save(parent)

    milestone = Milestone(title="Phase 1", parent_id=parent.id, status="active")
    db.save(milestone)

    audits = _audits_for_target(db, milestone.id)
    assert len(audits) == 1
    assert audits[0].actor == "ui"
    assert audits[0].action_name == "milestone.create"
    assert audits[0].target_ids == [milestone.id]
