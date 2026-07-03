"""Concurrency hardening tests for audited mutation paths.

These stress the recently-audited create/move routes against the same library
using concurrent client calls. The contract is:

- every successful mutation writes exactly one ActionAudit row
- every successful mutation emits exactly one observable-layer change
- created/mutated state is not corrupted or lost

The manager owns the full suite; this worker only runs this focused file.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from fichero.models import ActionAudit, DocType, Document


NOTE_N = 8
DOCUMENT_N = 8
CLAIM_N = 8
ENTITY_N = 8
ROOM_N = 8
MOVE_N = 8


@pytest.fixture
def emit_calls(monkeypatch):
    """Capture change events from both registry-level and route-level emit paths."""
    calls: list[dict] = []
    lock = threading.Lock()

    def spy(*args, **kwargs):
        with lock:
            calls.append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr("fichero.api.change_stream.emit_change", spy)
    monkeypatch.setattr("fichero.api.routes.notes.emit_change", spy)
    monkeypatch.setattr("fichero.api.routes.documents.emit_change", spy)
    monkeypatch.setattr("fichero.api.routes.claims.emit_change", spy)
    monkeypatch.setattr("fichero.api.routes.entities.emit_change", spy)
    return calls


async def _post_json(client, path: str, payload: dict):
    return await asyncio.to_thread(client.post, path, json=payload)


async def _put(client, path: str):
    return await asyncio.to_thread(client.put, path)


def _audits_for_action(db, action_name: str) -> list[ActionAudit]:
    return [row for row in db.all(ActionAudit) if row.action_name == action_name]


def _audit_targets(db, action_name: str) -> set[str]:
    ids: set[str] = set()
    for row in _audits_for_action(db, action_name):
        ids.update(row.target_ids or [])
    return ids


def _emitted_document_ids(calls: list[dict], event_type: str) -> list[str]:
    ids: list[str] = []
    for call in calls:
        kwargs = call["kwargs"]
        if kwargs.get("type") == event_type:
            ids.extend(kwargs.get("document_ids") or [])
    return ids


def _emitted_claim_ids(calls: list[dict], event_type: str) -> list[str]:
    ids: list[str] = []
    for call in calls:
        kwargs = call["kwargs"]
        if kwargs.get("type") == event_type:
            ids.extend(kwargs.get("claim_ids") or [])
    return ids


def _emitted_entity_ids(calls: list[dict], event_type: str) -> list[str]:
    ids: list[str] = []
    for call in calls:
        kwargs = call["kwargs"]
        if kwargs.get("type") == event_type:
            ids.extend(kwargs.get("entity_ids") or [])
    return ids


class TestAuditedMutationConcurrency:
    @pytest.mark.asyncio
    async def test_note_create_concurrent_writes_audit_emit_and_rows(
        self, client, db, emit_calls
    ):
        folder = Document(id="note-parent", name="Notes", doc_type=DocType.folder)
        db.save(folder)

        responses = await asyncio.gather(
            *[
                _post_json(
                    client,
                    "/api/notes",
                    {
                        "title": f"Note {i}",
                        "body": f"body-{i}",
                        "folder_id": folder.id,
                    },
                )
                for i in range(NOTE_N)
            ]
        )

        assert all(response.status_code == 200 for response in responses)
        note_ids = [response.json()["id"] for response in responses]
        assert len(note_ids) == NOTE_N
        assert len(set(note_ids)) == NOTE_N

        audits = _audits_for_action(db, "note.create")
        assert len(audits) == NOTE_N
        assert _audit_targets(db, "note.create") == set(note_ids)

        emitted_ids = _emitted_document_ids(emit_calls, "note.created")
        assert len(emitted_ids) == NOTE_N
        assert emitted_ids.count(folder.id) == NOTE_N

    @pytest.mark.asyncio
    async def test_document_create_concurrent_writes_audit_emit_and_rows(
        self, client, db, emit_calls
    ):
        parent = Document(id="doc-parent", name="Folder", doc_type=DocType.folder)
        db.save(parent)

        responses = await asyncio.gather(
            *[
                _post_json(
                    client,
                    "/api/documents",
                    {"name": f"Doc {i}", "parent_id": parent.id},
                )
                for i in range(DOCUMENT_N)
            ]
        )

        assert all(response.status_code == 201 for response in responses)
        doc_ids = [response.json()["id"] for response in responses]
        assert len(set(doc_ids)) == DOCUMENT_N
        assert _audit_targets(db, "document.create") == set(doc_ids)

        emitted_ids = _emitted_document_ids(emit_calls, "document.created")
        assert len(emitted_ids) == DOCUMENT_N
        assert set(emitted_ids) == set(doc_ids)
        assert all(db.get(Document, doc_id).parent_id == parent.id for doc_id in doc_ids)

    @pytest.mark.asyncio
    async def test_claim_create_concurrent_writes_audit_emit_and_rows(
        self, client, db, emit_calls
    ):
        responses = await asyncio.gather(
            *[
                _post_json(client, "/api/claims", {"text": f"Claim {i}"})
                for i in range(CLAIM_N)
            ]
        )

        assert all(response.status_code == 200 for response in responses)
        claim_ids = [response.json()["id"] for response in responses]
        assert len(set(claim_ids)) == CLAIM_N
        assert _audit_targets(db, "claim.create") == set(claim_ids)

        emitted_ids = _emitted_claim_ids(emit_calls, "claim.updated")
        assert len(emitted_ids) == CLAIM_N
        assert set(emitted_ids) == set(claim_ids)

    @pytest.mark.asyncio
    async def test_entity_create_concurrent_writes_audit_emit_and_rows(
        self, client, db, emit_calls
    ):
        responses = await asyncio.gather(
            *[
                _post_json(
                    client,
                    "/api/entities",
                    {"canonical_name": f"Entity {i}", "entity_type": "person"},
                )
                for i in range(ENTITY_N)
            ]
        )

        assert all(response.status_code == 200 for response in responses)
        entity_ids = [response.json()["id"] for response in responses]
        assert len(set(entity_ids)) == ENTITY_N
        assert _audit_targets(db, "entity.create") == set(entity_ids)

        emitted_ids = _emitted_entity_ids(emit_calls, "entity.created")
        assert len(emitted_ids) == ENTITY_N
        assert set(emitted_ids) == set(entity_ids)

    @pytest.mark.asyncio
    async def test_room_create_concurrent_writes_audit_emit_and_dual_write(
        self, client, db, emit_calls
    ):
        responses = await asyncio.gather(
            *[
                _post_json(
                    client,
                    "/api/mind-palace/rooms",
                    {"name": f"Room {i}", "room_type": "research"},
                )
                for i in range(ROOM_N)
            ]
        )

        assert all(response.status_code == 200 for response in responses)
        room_ids = [response.json()["id"] for response in responses]
        assert len(set(room_ids)) == ROOM_N
        assert _audit_targets(db, "room.create") == set(room_ids)

        emitted_ids = _emitted_document_ids(emit_calls, "document.created")
        room_emits = [room_id for room_id in emitted_ids if room_id in set(room_ids)]
        assert len(room_emits) == ROOM_N

        legacy_ids = {room.id for room in db._legacy_all_spatial_room_rows()}
        for room_id in room_ids:
            mirrored = db.get(Document, room_id)
            assert mirrored is not None
            assert mirrored.node_kind == "room"
            assert room_id in legacy_ids

    @pytest.mark.asyncio
    async def test_document_move_concurrent_writes_audit_emit_and_state(
        self, client, db, emit_calls
    ):
        source_parent = Document(
            id="move-source-parent",
            name="Source",
            doc_type=DocType.folder,
        )
        target_parent = Document(
            id="move-target-parent",
            name="Target",
            doc_type=DocType.folder,
        )
        db.save(source_parent)
        db.save(target_parent)

        docs: list[Document] = []
        for i in range(MOVE_N):
            doc = Document(
                id=f"move-doc-{i}",
                name=f"Move Doc {i}",
                parent_id=source_parent.id,
                doc_type=DocType.file,
            )
            db.save(doc)
            docs.append(doc)

        responses = await asyncio.gather(
            *[
                _put(client, f"/api/documents/{doc.id}/move?parent_id={target_parent.id}")
                for doc in docs
            ]
        )

        assert all(response.status_code == 200 for response in responses)
        moved_ids = [response.json()["id"] for response in responses]
        assert len(set(moved_ids)) == MOVE_N
        assert _audit_targets(db, "document.move") == set(moved_ids)

        emitted_ids = _emitted_document_ids(emit_calls, "document.updated")
        moved_emits = [doc_id for doc_id in emitted_ids if doc_id in set(moved_ids)]
        assert len(moved_emits) == MOVE_N

        for doc_id in moved_ids:
            reloaded = db.get(Document, doc_id)
            assert reloaded is not None
            assert reloaded.parent_id == target_parent.id
