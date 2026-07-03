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


async def _put_json(client, path: str, payload: dict):
    return await asyncio.to_thread(client.put, path, json=payload)


async def _patch_json(client, path: str, payload: dict):
    return await asyncio.to_thread(client.patch, path, json=payload)


async def _put(client, path: str):
    return await asyncio.to_thread(client.put, path)


async def _delete(client, path: str):
    return await asyncio.to_thread(client.delete, path)


async def _get(client, path: str):
    return await asyncio.to_thread(client.get, path)


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


def _assert_no_server_errors(responses) -> None:
    for response in responses:
        assert response.status_code < 500, response.text
        assert "CatalogException" not in response.text


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

    @pytest.mark.asyncio
    async def test_document_move_same_document_concurrent_writes_audit_emit_and_state(
        self, client, db, emit_calls
    ):
        source_parent = Document(id="update-source", name="Source", doc_type=DocType.folder)
        left_parent = Document(id="update-left", name="Left", doc_type=DocType.folder)
        right_parent = Document(id="update-right", name="Right", doc_type=DocType.folder)
        doc = Document(
            id="update-doc",
            name="Before",
            parent_id=source_parent.id,
            doc_type=DocType.file,
        )
        db.save(source_parent)
        db.save(left_parent)
        db.save(right_parent)
        db.save(doc)

        parent_ids = [left_parent.id if i % 2 == 0 else right_parent.id for i in range(DOCUMENT_N)]
        responses = await asyncio.gather(
            *[
                _put(client, f"/api/documents/{doc.id}/move?parent_id={parent_id}")
                for parent_id in parent_ids
            ]
        )

        _assert_no_server_errors(responses)
        assert all(response.status_code == 200 for response in responses)
        assert len(_audits_for_action(db, "document.move")) == DOCUMENT_N
        assert _audit_targets(db, "document.move") == {doc.id}

        emitted_ids = _emitted_document_ids(emit_calls, "document.updated")
        assert emitted_ids.count(doc.id) == DOCUMENT_N

        reloaded = db.get(Document, doc.id)
        assert reloaded is not None
        assert reloaded.parent_id in {left_parent.id, right_parent.id}

    @pytest.mark.asyncio
    async def test_claim_patch_concurrent_writes_audit_emit_and_state(
        self, client, db, emit_calls
    ):
        create_response = await _post_json(client, "/api/claims", {"text": "Before"})
        assert create_response.status_code == 200
        claim_id = create_response.json()["id"]

        texts = [f"After claim {i}" for i in range(CLAIM_N)]
        responses = await asyncio.gather(
            *[
                _patch_json(client, f"/api/claims/{claim_id}", {"text": text})
                for text in texts
            ]
        )

        _assert_no_server_errors(responses)
        assert all(response.status_code == 200 for response in responses)
        assert len(_audits_for_action(db, "claim.patch")) == CLAIM_N
        assert _audit_targets(db, "claim.patch") == {claim_id}

        emitted_ids = _emitted_claim_ids(emit_calls, "claim.updated")
        assert emitted_ids.count(claim_id) == CLAIM_N + 1

        claim_response = await _get(client, f"/api/claims/{claim_id}")
        assert claim_response.status_code == 200
        assert claim_response.json()["text"] in set(texts)

    @pytest.mark.xfail(
        strict=True,
        reason="Existing-id entity upserts only audit the initial create on main; concurrent update semantics are not yet action-audited per mutation.",
    )
    @pytest.mark.asyncio
    async def test_entity_upsert_concurrent_updates_audit_emit_and_state(
        self, client, db, emit_calls
    ):
        create_response = await _post_json(
            client,
            "/api/entities",
            {"canonical_name": "Before", "entity_type": "person"},
        )
        assert create_response.status_code == 200
        entity_id = create_response.json()["id"]

        names = [f"Entity After {i}" for i in range(ENTITY_N)]
        responses = await asyncio.gather(
            *[
                _post_json(
                    client,
                    "/api/entities",
                    {
                        "id": entity_id,
                        "canonical_name": name,
                        "entity_type": "person",
                    },
                )
                for name in names
            ]
        )

        _assert_no_server_errors(responses)
        assert all(response.status_code == 200 for response in responses)
        assert len(_audits_for_action(db, "entity.create")) == ENTITY_N + 1
        assert _audit_targets(db, "entity.create") == {entity_id}

        emitted_ids = _emitted_entity_ids(emit_calls, "entity.created")
        assert emitted_ids.count(entity_id) == ENTITY_N + 1

        entity_response = await _get(client, f"/api/entities/{entity_id}")
        assert entity_response.status_code == 200
        assert entity_response.json()["canonical_name"] in set(names)

    @pytest.mark.asyncio
    async def test_cross_table_lazy_ensure_table_concurrent_writes_stay_consistent(
        self, client, db, emit_calls
    ):
        responses = await asyncio.gather(
            *[
                _post_json(client, "/api/claims", {"text": f"Claim lazy {i}"})
                for i in range(CLAIM_N)
            ],
            *[
                _post_json(
                    client,
                    "/api/entities",
                    {"canonical_name": f"Entity lazy {i}", "entity_type": "person"},
                )
                for i in range(ENTITY_N)
            ],
        )

        _assert_no_server_errors(responses)
        assert all(response.status_code == 200 for response in responses)

        claim_ids = {response.json()["id"] for response in responses[:CLAIM_N]}
        entity_ids = {response.json()["id"] for response in responses[CLAIM_N:]}
        assert len(claim_ids) == CLAIM_N
        assert len(entity_ids) == ENTITY_N

        assert _audit_targets(db, "claim.create") == claim_ids
        assert _audit_targets(db, "entity.create") == entity_ids

        emitted_claim_ids = _emitted_claim_ids(emit_calls, "claim.updated")
        emitted_entity_ids = _emitted_entity_ids(emit_calls, "entity.created")
        assert set(emitted_claim_ids) == claim_ids
        assert set(emitted_entity_ids) == entity_ids

    @pytest.mark.asyncio
    async def test_mixed_create_update_delete_storm_in_one_library(
        self, client, db, emit_calls
    ):
        parent = Document(id="storm-parent", name="Storm Parent", doc_type=DocType.folder)
        target = Document(id="storm-target", name="Storm Target", doc_type=DocType.folder)
        move_doc = Document(
            id="storm-move-doc",
            name="Before Move",
            parent_id=parent.id,
            doc_type=DocType.file,
        )
        delete_doc = Document(
            id="storm-delete-doc",
            name="Before Delete",
            parent_id=parent.id,
            doc_type=DocType.file,
        )
        db.save(parent)
        db.save(target)
        db.save(move_doc)
        db.save(delete_doc)

        claim_response = await _post_json(
            client,
            "/api/claims",
            {"text": "Storm Claim Before Patch"},
        )
        assert claim_response.status_code == 200
        claim_id = claim_response.json()["id"]

        entity_response = await _post_json(
            client,
            "/api/entities",
            {"canonical_name": "Storm Entity", "entity_type": "person"},
        )
        assert entity_response.status_code == 200

        responses = await asyncio.gather(
            _post_json(client, "/api/notes", {"title": "Storm Note", "body": "body", "folder_id": parent.id}),
            _post_json(client, "/api/documents", {"name": "Storm Doc", "parent_id": parent.id}),
            _post_json(client, "/api/claims", {"text": "Storm Claim"}),
            _post_json(client, "/api/mind-palace/rooms", {"name": "Storm Room", "room_type": "research"}),
            _patch_json(client, f"/api/claims/{claim_id}", {"text": "Storm Claim After Patch"}),
            _put(client, f"/api/documents/{move_doc.id}/move?parent_id={target.id}"),
            _delete(client, f"/api/documents/{delete_doc.id}"),
            _post_json(client, "/api/entities", {"canonical_name": "Storm Entity 2", "entity_type": "person"}),
        )

        _assert_no_server_errors(responses)
        assert [response.status_code for response in responses] == [200, 201, 200, 200, 200, 200, 204, 200]

        assert len(_audits_for_action(db, "note.create")) == 1
        assert len(_audits_for_action(db, "document.create")) == 1
        assert len(_audits_for_action(db, "claim.create")) == 2
        assert len(_audits_for_action(db, "claim.patch")) == 1
        assert len(_audits_for_action(db, "room.create")) == 1
        assert len(_audits_for_action(db, "document.move")) == 1
        assert len(_audits_for_action(db, "document.delete")) == 1
        assert len(_audits_for_action(db, "entity.create")) == 2

        assert db.get(Document, move_doc.id).parent_id == target.id
        assert db.get(Document, delete_doc.id).deleted_at is not None

    @pytest.mark.asyncio
    async def test_reads_during_writes_return_consistent_payloads(
        self, client, db, emit_calls
    ):
        parent = Document(id="read-parent", name="Read Parent", doc_type=DocType.folder)
        db.save(parent)

        async def create_documents():
            return await asyncio.gather(
                *[
                    _post_json(
                        client,
                        "/api/documents",
                        {"name": f"Read Doc {i}", "parent_id": parent.id},
                    )
                    for i in range(DOCUMENT_N)
                ]
            )

        async def create_claims():
            return await asyncio.gather(
                *[
                    _post_json(client, "/api/claims", {"text": f"Read Claim {i}"})
                    for i in range(CLAIM_N)
                ]
            )

        async def read_documents():
            return await asyncio.gather(
                *[_get(client, "/api/documents") for _ in range(DOCUMENT_N)]
            )

        async def read_claims():
            return await asyncio.gather(
                *[_get(client, "/api/claims") for _ in range(CLAIM_N)]
            )

        doc_writes, claim_writes, doc_reads, claim_reads = await asyncio.gather(
            create_documents(),
            create_claims(),
            read_documents(),
            read_claims(),
        )

        _assert_no_server_errors(doc_writes + claim_writes + doc_reads + claim_reads)
        assert all(response.status_code == 201 for response in doc_writes)
        assert all(response.status_code == 200 for response in claim_writes)
        assert all(response.status_code == 200 for response in doc_reads)
        assert all(response.status_code == 200 for response in claim_reads)

        for response in doc_reads:
            ids = [item["id"] for item in response.json()["items"]]
            assert len(ids) == len(set(ids))

        for response in claim_reads:
            ids = [item["id"] for item in response.json()["items"]]
            assert len(ids) == len(set(ids))

        assert len(_audits_for_action(db, "document.create")) == DOCUMENT_N
        assert len(_audits_for_action(db, "claim.create")) == CLAIM_N
