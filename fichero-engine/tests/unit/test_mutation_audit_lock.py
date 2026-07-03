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
import fichero.api.routes.mind_palace  # noqa: F401
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


def _create_room(client, db) -> tuple[object, str, str, str, str, str]:
    response = client.post(
        "/api/mind-palace/rooms",
        json={
            "name": "Audit Lock Room",
            "room_type": "research",
            "description": "must audit and emit",
        },
    )
    room_id = response.json()["id"]
    return response, room_id, "room.create", "document.created", "document_ids", room_id


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


def _update_room(client, db) -> tuple[object, str, str, str, str, str]:
    create = client.post("/api/mind-palace/rooms", json={"name": "Before Room"})
    room_id = create.json()["id"]
    response = client.patch(
        f"/api/mind-palace/rooms/{room_id}",
        json={"description": "After room update"},
    )
    return response, room_id, "room.update", "document.updated", "document_ids", room_id


def _delete_room(client, db) -> tuple[object, str, str, str, str, str]:
    create = client.post("/api/mind-palace/rooms", json={"name": "Delete Room"})
    room_id = create.json()["id"]
    response = client.delete(f"/api/mind-palace/rooms/{room_id}")
    return response, room_id, "room.delete", "document.deleted", "document_ids", room_id


@pytest.mark.parametrize(
    ("label", "creator"),
    [
        ("note.create", _create_note),
        ("document.create", _create_document),
        ("claim.create", _create_claim),
        ("entity.create", _create_entity),
        ("room.create", _create_room),
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
        ("document.move", _move_document),
        ("document.delete", _delete_document),
        ("claim.patch", _patch_claim),
        ("claim.delete", _delete_claim),
        ("entity.upsert", _entity_upsert_update),
        pytest.param(
            "entity.patch",
            _patch_entity,
            marks=pytest.mark.xfail(
                strict=True,
                reason="PATCH /api/entities/{entity_id} still updates directly on main and does not write entity.update ActionAudit.",
            ),
        ),
        pytest.param(
            "note.patch",
            _patch_note,
            marks=pytest.mark.xfail(
                strict=True,
                reason="PATCH /api/notes/{note_id} still bypasses registry.invoke on main and does not write note.update ActionAudit.",
            ),
        ),
        pytest.param(
            "note.delete",
            _delete_note,
            marks=pytest.mark.xfail(
                strict=True,
                reason="DELETE /api/notes/{note_id} still bypasses registry.invoke on main and does not write note.delete ActionAudit.",
            ),
        ),
        ("room.update", _update_room),
        ("room.delete", _delete_room),
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
    assert audit.target_ids == [target_id]

    matches = _matching_emit_calls(
        emit_calls,
        emit_type=emit_type,
        emit_key=emit_key,
        emit_target=emit_target,
    )
    assert matches, f"{label} expected {emit_type} emit_change call"
    assert matches[-1]["actor"] == audit.actor
