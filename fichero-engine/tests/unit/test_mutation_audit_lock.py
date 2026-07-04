"""Regression lock for the #2789 audited mutation sweep.

Parametrized guards over the shipped node-model mutation routes. If any future
change drops either ActionAudit or emit_change on these paths, this file should
fail loudly. Known bypasses stay as strict xfails until the route is pushed
through the action layer.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

import fichero.api.routes.claims  # noqa: F401
import fichero.api.routes.documents  # noqa: F401
import fichero.api.routes.entities  # noqa: F401
import fichero.api.routes.notes  # noqa: F401
from fichero.models import ActionAudit, DocType, Document


def _audits_for_target(
    db, target_id: str, *, action_name: str | None = None
) -> list[ActionAudit]:
    rows = [row for row in db.all(ActionAudit) if target_id in (row.target_ids or [])]
    if action_name is not None:
        rows = [row for row in rows if row.action_name == action_name]
    return rows


def _install_emit_recorder(monkeypatch, emit_calls: list[tuple[tuple, dict]]) -> None:
    def _record(*args, **kwargs):
        emit_calls.append((args, kwargs))

    monkeypatch.setattr("fichero.api.routes.notes.emit_change", _record)
    monkeypatch.setattr("fichero.api.routes.claims.emit_change", _record)
    monkeypatch.setattr("fichero.api.routes.entities.emit_change", _record)
    monkeypatch.setattr("fichero.api.routes.documents.emit_change", _record)
    monkeypatch.setattr("fichero.api.change_stream.emit_change", _record)


def _matching_emit_calls(
    emit_calls: list[tuple[tuple, dict]],
    *,
    emit_type: str,
    emit_key: str,
    emit_target: str,
) -> list[dict]:
    return [
        kwargs
        for _args, kwargs in emit_calls
        if kwargs.get("type") == emit_type
        and emit_target in (kwargs.get(emit_key) or [])
    ]


def _create_note(client, db) -> tuple[object, str, str, str, str, str]:
    folder = Document(name="Audit Lock Folder", doc_type=DocType.folder)
    db.save(folder)
    response = client.post(
        "/api/notes",
        json={
            "title": "Audit lock note",
            "body": "must audit and emit",
            "folder_id": folder.id,
        },
    )
    return (
        response,
        response.json()["id"],
        "note.create",
        "note.created",
        "document_ids",
        folder.id,
    )


def _create_document(client, db) -> tuple[object, str, str, str, str, str]:
    response = client.post("/api/documents", json={"name": "Audit Lock Doc"})
    doc_id = response.json()["id"]
    return response, doc_id, "document.create", "document.created", "document_ids", doc_id


def _create_claim(client, db) -> tuple[object, str, str, str, str, str]:
    response = client.post("/api/claims", json={"text": "Audit lock claim"})
    claim_id = response.json()["id"]
    return response, claim_id, "claim.create", "claim.updated", "claim_ids", claim_id


def _create_entity(client, db) -> tuple[object, str, str, str, str, str]:
    response = client.post("/api/entities", json={"canonical_name": "Audit Lock Entity"})
    entity_id = response.json()["id"]
    return response, entity_id, "entity.create", "entity.created", "entity_ids", entity_id


def _create_folder(client, db) -> tuple[object, str, str, str, str, str]:
    response = client.post(
        "/api/documents",
        json={"name": "Audit Lock Folder", "doc_type": "folder"},
    )
    doc_id = response.json()["id"]
    return response, doc_id, "document.create", "document.created", "document_ids", doc_id


def _move_document(client, db) -> tuple[object, str, str, str, str, str]:
    source = Document(name="Move Source", doc_type=DocType.folder)
    target = Document(name="Move Target", doc_type=DocType.folder)
    doc = Document(name="Move Me", parent_id=source.id)
    db.save(source)
    db.save(target)
    db.save(doc)
    response = client.put(f"/api/documents/{doc.id}/move?parent_id={target.id}")
    return response, doc.id, "document.move", "document.updated", "document_ids", doc.id


def _delete_document(client, db) -> tuple[object, str, str, str, str, str]:
    doc = Document(name="Delete Me")
    db.save(doc)
    response = client.delete(f"/api/documents/{doc.id}")
    return response, doc.id, "document.delete", "document.deleted", "document_ids", doc.id


def _patch_claim(client, db) -> tuple[object, str, str, str, str, str]:
    create = client.post("/api/claims", json={"text": "Before claim patch"})
    claim_id = create.json()["id"]
    response = client.patch(f"/api/claims/{claim_id}", json={"text": "After claim patch"})
    return response, claim_id, "claim.patch", "claim.updated", "claim_ids", claim_id


def _delete_claim(client, db) -> tuple[object, str, str, str, str, str]:
    create = client.post("/api/claims", json={"text": "Delete claim"})
    claim_id = create.json()["id"]
    response = client.delete(f"/api/claims/{claim_id}")
    return response, claim_id, "claim.delete", "claim.deleted", "claim_ids", claim_id


def _entity_upsert_update(client, db) -> tuple[object, str, str, str, str, str]:
    create = client.post("/api/entities", json={"canonical_name": "Before Upsert"})
    entity_id = create.json()["id"]
    response = client.post(
        "/api/entities",
        json={"id": entity_id, "canonical_name": "After Upsert"},
    )
    return response, entity_id, "entity.update", "entity.updated", "entity_ids", entity_id


def _patch_entity(client, db) -> tuple[object, str, str, str, str, str]:
    create = client.post("/api/entities", json={"canonical_name": "Before Entity Patch"})
    entity_id = create.json()["id"]
    response = client.patch(
        f"/api/entities/{entity_id}",
        json={"canonical_name": "After Entity Patch"},
    )
    return response, entity_id, "entity.update", "entity.updated", "entity_ids", entity_id


def _delete_entity(client, db) -> tuple[object, str, str, str, str, str]:
    create = client.post("/api/entities", json={"canonical_name": "Delete Entity"})
    entity_id = create.json()["id"]
    response = client.delete(f"/api/entities/{entity_id}")
    return response, entity_id, "entity.delete", "entity.deleted", "entity_ids", entity_id


def _patch_note(client, db) -> tuple[object, str, str, str, str, str]:
    folder = Document(name="Patch Note Folder", doc_type=DocType.folder)
    db.save(folder)
    create = client.post(
        "/api/notes",
        json={"title": "Before note patch", "body": "before", "folder_id": folder.id},
    )
    note_id = create.json()["id"]
    response = client.patch(f"/api/notes/{note_id}", json={"body": "after"})
    return response, note_id, "note.update", "note.updated", "document_ids", folder.id


def _delete_note(client, db) -> tuple[object, str, str, str, str, str]:
    folder = Document(name="Delete Note Folder", doc_type=DocType.folder)
    db.save(folder)
    create = client.post(
        "/api/notes",
        json={"title": "Delete note", "body": "before", "folder_id": folder.id},
    )
    note_id = create.json()["id"]
    response = client.delete(f"/api/notes/{note_id}")
    return response, note_id, "note.delete", "note.deleted", "document_ids", folder.id


def _delete_folder(client, db) -> tuple[object, str, str, str, str, str]:
    doc = Document(name="Delete Folder", doc_type=DocType.folder)
    db.save(doc)
    response = client.delete(f"/api/documents/{doc.id}")
    return response, doc.id, "document.delete", "document.deleted", "document_ids", doc.id


def _update_document(client, db) -> tuple[object, str, str, str, str, str]:
    doc = Document(name="Before Update")
    db.save(doc)
    response = client.put(f"/api/documents/{doc.id}", json={"name": "After Update"})
    return response, doc.id, "document.update", "document.updated", "document_ids", doc.id


def _restore_document(client, db) -> tuple[object, str, str, str, str, str]:
    doc = Document(name="Restore Me")
    db.save(doc)
    delete = client.delete(f"/api/documents/{doc.id}")
    assert delete.status_code == 204
    response = client.post(f"/api/documents/{doc.id}/restore")
    return response, doc.id, "document.restore", "document.updated", "document_ids", doc.id


def _reorder_documents(client, db) -> tuple[object, str, str, str, str, str]:
    a = Document(name="Reorder A")
    b = Document(name="Reorder B")
    db.save(a)
    db.save(b)
    response = client.post("/api/documents/reorder", json=[b.id, a.id])
    return response, a.id, "document.reorder", "document.updated", "document_ids", a.id


def _batch_exclude_documents(client, db) -> tuple[object, str, str, str, str, str]:
    doc = Document(name="Exclude Me")
    db.save(doc)
    response = client.patch(
        "/api/documents/batch-exclude",
        json={"document_ids": [doc.id], "excluded": True},
    )
    return (
        response,
        doc.id,
        "document.batch_exclude",
        "document.updated",
        "document_ids",
        doc.id,
    )


def _put_document_note(client, db) -> tuple[object, str, str, str, str, str]:
    doc = Document(name="Noted")
    db.save(doc)
    response = client.put(
        f"/api/documents/{doc.id}/notes",
        json={"content": "audit note"},
    )
    return (
        response,
        doc.id,
        "document.note_upsert",
        "document.updated",
        "document_ids",
        doc.id,
    )


def _delete_document_note(client, db) -> tuple[object, str, str, str, str, str]:
    doc = Document(name="Delete Noted")
    db.save(doc)
    create = client.put(f"/api/documents/{doc.id}/notes", json={"content": "before"})
    assert create.status_code == 200
    response = client.delete(f"/api/documents/{doc.id}/notes")
    return (
        response,
        doc.id,
        "document.note_delete",
        "document.updated",
        "document_ids",
        doc.id,
    )


def _assign_document_prototype(client, db) -> tuple[object, str, str, str, str, str]:
    doc = Document(name="Prototype Target")
    db.save(doc)
    response = client.put(
        f"/api/documents/{doc.id}/prototype",
        json={"prototype_key": "letter"},
    )
    return (
        response,
        doc.id,
        "document.assign_prototype",
        "document.updated",
        "document_ids",
        doc.id,
    )


def _upsert_page_ranges(client, db) -> tuple[object, str, str, str, str, str]:
    pdf = Document(name="Paged", file_type="pdf", doc_type=DocType.file)
    db.save(pdf)
    response = client.put(
        f"/api/documents/{pdf.id}/page-ranges",
        json={"items": [{"id": "range-1", "name": "Intro", "page_start": 1, "page_end": 2}]},
    )
    return (
        response,
        pdf.id,
        "document.upsert_page_ranges",
        "document.updated",
        "document_ids",
        pdf.id,
    )


@pytest.mark.parametrize(
    ("label", "creator"),
    [
        ("note.create", _create_note),
        ("document.create", _create_document),
        ("claim.create", _create_claim),
        ("entity.create", _create_entity),
        ("folder.create", _create_folder),
    ],
)
def test_node_model_create_routes_write_audit_and_emit_change(
    label: str,
    creator: Callable,
    client,
    db,
    monkeypatch,
):
    emit_calls: list[tuple[tuple, dict]] = []
    _install_emit_recorder(monkeypatch, emit_calls)

    response, target_id, action_name, emit_type, emit_key, emit_target = creator(client, db)

    assert response.status_code in {200, 201}, f"{label} status {response.status_code}"

    audits = _audits_for_target(db, target_id, action_name=action_name)
    assert len(audits) == 1, f"{label} expected one audit row for {target_id}"
    audit = audits[0]
    assert audit.actor == "system"
    assert audit.action_name == action_name
    assert audit.target_ids == [target_id]

    matches = _matching_emit_calls(
        emit_calls,
        emit_type=emit_type,
        emit_key=emit_key,
        emit_target=emit_target,
    )
    assert matches, f"{label} expected emit_change call"
    assert matches[-1]["actor"] == audit.actor


@pytest.mark.parametrize(
    ("label", "mutator"),
    [
        ("document.update", _update_document),
        ("document.move", _move_document),
        ("document.reorder", _reorder_documents),
        ("document.batch_exclude", _batch_exclude_documents),
        ("document.delete", _delete_document),
        ("document.restore", _restore_document),
        ("claim.patch", _patch_claim),
        ("claim.delete", _delete_claim),
        ("entity.upsert", _entity_upsert_update),
        ("entity.patch", _patch_entity),
        ("entity.delete", _delete_entity),
        ("document.note_upsert", _put_document_note),
        ("document.note_delete", _delete_document_note),
        ("document.assign_prototype", _assign_document_prototype),
        ("document.upsert_page_ranges", _upsert_page_ranges),
        ("note.patch", _patch_note),
        ("note.delete", _delete_note),
        ("folder.delete", _delete_folder),
    ],
)
def test_node_model_mutation_routes_write_audit_and_emit_change(
    label: str,
    mutator: Callable,
    client,
    db,
    monkeypatch,
):
    emit_calls: list[tuple[tuple, dict]] = []
    _install_emit_recorder(monkeypatch, emit_calls)

    response, target_id, action_name, emit_type, emit_key, emit_target = mutator(client, db)

    assert response.status_code in {200, 201, 204}, f"{label} status {response.status_code}"

    audits = _audits_for_target(db, target_id, action_name=action_name)
    assert len(audits) == 1, f"{label} expected one {action_name} audit row for {target_id}"
    audit = audits[0]
    assert audit.actor == "system"
    assert audit.action_name == action_name
    assert target_id in audit.target_ids

    matches = _matching_emit_calls(
        emit_calls,
        emit_type=emit_type,
        emit_key=emit_key,
        emit_target=emit_target,
    )
    assert matches, f"{label} expected {emit_type} emit_change call"
    assert matches[-1]["actor"] == audit.actor


def test_document_import_route_writes_action_audit_and_emit_change(
    client,
    db,
    monkeypatch,
    tmp_path,
):
    emit_calls: list[tuple[tuple, dict]] = []
    _install_emit_recorder(monkeypatch, emit_calls)
    upload_path = tmp_path / "audit-import.txt"
    upload_path.write_text("import me", encoding="utf-8")

    with upload_path.open("rb") as handle:
        response = client.post(
            "/api/documents/import",
            files={"file": ("audit-import.txt", handle, "text/plain")},
        )

    assert response.status_code == 200
    document_id = response.json()["id"]

    audits = _audits_for_target(db, document_id, action_name="import.upload_file")
    assert len(audits) == 1
    audit = audits[0]
    assert audit.actor == "system"
    assert audit.target_ids == [document_id]

    matches = _matching_emit_calls(
        emit_calls,
        emit_type="document.created",
        emit_key="document_ids",
        emit_target=document_id,
    )
    assert matches
    assert matches[-1]["actor"] == audit.actor
