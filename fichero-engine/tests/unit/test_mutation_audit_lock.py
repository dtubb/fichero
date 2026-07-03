"""Regression lock for the #2789 audited mutation sweep.

One parametrized guard over the shipped node-model mutation create routes:
note, document, claim, entity, and mind-palace room. If any future change drops
either ActionAudit or emit_change on these paths, this file should fail loudly.
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


def _audits_for_target(db, target_id: str) -> list[ActionAudit]:
    return [row for row in db.all(ActionAudit) if target_id in (row.target_ids or [])]


def _install_emit_recorder(monkeypatch, emit_calls: list[tuple[tuple, dict]]) -> None:
    def _record(*args, **kwargs):
        emit_calls.append((args, kwargs))

    monkeypatch.setattr("fichero.api.routes.notes.emit_change", _record)
    monkeypatch.setattr("fichero.api.routes.claims.emit_change", _record)
    monkeypatch.setattr("fichero.api.routes.entities.emit_change", _record)
    monkeypatch.setattr("fichero.api.routes.documents.emit_change", _record)
    monkeypatch.setattr("fichero.api.change_stream.emit_change", _record)


def _create_note(client, db) -> tuple[object, str, str, str, str]:
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
    return response, response.json()["id"], "note.create", "document_ids", folder.id


def _create_document(client, db) -> tuple[object, str, str, str, str]:
    response = client.post("/api/documents", json={"name": "Audit Lock Doc"})
    doc_id = response.json()["id"]
    return response, doc_id, "document.create", "document_ids", doc_id


def _create_claim(client, db) -> tuple[object, str, str, str, str]:
    response = client.post("/api/claims", json={"text": "Audit lock claim"})
    claim_id = response.json()["id"]
    return response, claim_id, "claim.create", "claim_ids", claim_id


def _create_entity(client, db) -> tuple[object, str, str, str, str]:
    response = client.post("/api/entities", json={"canonical_name": "Audit Lock Entity"})
    entity_id = response.json()["id"]
    return response, entity_id, "entity.create", "entity_ids", entity_id


def _create_room(client, db) -> tuple[object, str, str, str, str]:
    response = client.post(
        "/api/mind-palace/rooms",
        json={
            "name": "Audit Lock Room",
            "room_type": "research",
            "description": "must audit and emit",
        },
    )
    room_id = response.json()["id"]
    return response, room_id, "room.create", "document_ids", room_id


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

    response, target_id, action_name, emit_key, emit_target = creator(client, db)

    assert response.status_code in {200, 201}, f"{label} status {response.status_code}"

    audits = _audits_for_target(db, target_id)
    assert len(audits) == 1, f"{label} expected one audit row for {target_id}"
    audit = audits[0]
    assert audit.actor == "system"
    assert audit.action_name == action_name
    assert audit.target_ids == [target_id]

    assert emit_calls, f"{label} expected emit_change call"
    emit_kwargs = emit_calls[-1][1]
    assert emit_kwargs["actor"] == audit.actor
    assert emit_target in (emit_kwargs.get(emit_key) or [])

