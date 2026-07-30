"""Unit tests for the per-library change-stream hub (#1863).

Covers the hub primitives (subscribe → emit_change → queue delivery, per-library
isolation, unsubscribe) plus a light route test that the entity-merge endpoint
actually emits a change event.

The hub tests exercise the queues synchronously: ``asyncio.Queue.put_nowait`` /
``get_nowait`` manipulate the internal deque without needing a running event
loop, so no async runner is required.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime

import pytest

from fichero_server.api import change_stream
from fichero_server.api.change_stream import (
    ChangeEvent,
    _ChangeHub,
    emit_change,
    format_change_sse,
)
from fichero_server.db import db_manager
from fichero_server.models.knowledge import (
    Annotation,
    AnnotationKind,
    Reference,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    Note,
)
from fichero_server.models.hermeneutics import (
    CircleNavigationDirection,
    FrameworkType,
    HermeneuticCircleState,
    Interpretation,
    InterpretiveActType,
    InterpretiveFramework,
    PatternInstance,
    PatternStatus,
)
from fichero_server.models import Artifact, DocType, Document, FileType, Status


# ---------------------------------------------------------------------------
# Hub primitives
# ---------------------------------------------------------------------------


class TestChangeHub:
    def test_subscribe_then_emit_delivers_event(self):
        hub = _ChangeHub()
        queue = hub.subscribe("/lib/A.fichero")

        event = ChangeEvent(type="entity.updated", entity_ids=["e1"])
        delivered = hub.emit("/lib/A.fichero", event)

        assert delivered == 1
        assert queue.get_nowait() is event
        assert event.event_id == 1

    def test_per_library_isolation(self):
        hub = _ChangeHub()
        queue_a = hub.subscribe("/lib/A.fichero")
        queue_b = hub.subscribe("/lib/B.fichero")

        hub.emit("/lib/A.fichero", ChangeEvent(type="entity.merged"))

        # A receives; B stays empty.
        assert queue_a.get_nowait().type == "entity.merged"
        with pytest.raises(asyncio.QueueEmpty):
            queue_b.get_nowait()

    def test_fan_out_to_multiple_windows(self):
        hub = _ChangeHub()
        q1 = hub.subscribe("/lib/A.fichero")
        q2 = hub.subscribe("/lib/A.fichero")

        delivered = hub.emit("/lib/A.fichero", ChangeEvent(type="entity.deleted"))

        assert delivered == 2
        assert q1.get_nowait().type == "entity.deleted"
        assert q2.get_nowait().type == "entity.deleted"

    def test_unsubscribe_stops_delivery(self):
        hub = _ChangeHub()
        queue = hub.subscribe("/lib/A.fichero")
        assert hub.subscriber_count("/lib/A.fichero") == 1

        hub.unsubscribe("/lib/A.fichero", queue)
        assert hub.subscriber_count("/lib/A.fichero") == 0

        delivered = hub.emit("/lib/A.fichero", ChangeEvent(type="entity.updated"))
        assert delivered == 0
        with pytest.raises(asyncio.QueueEmpty):
            queue.get_nowait()

    def test_emit_to_library_with_no_subscribers_is_noop(self):
        hub = _ChangeHub()
        assert hub.emit("/lib/nobody.fichero", ChangeEvent(type="entity.updated")) == 0

    def test_event_ids_are_contiguous_per_library(self):
        hub = _ChangeHub()
        queue_a = hub.subscribe("/lib/A.fichero")
        queue_b = hub.subscribe("/lib/B.fichero")

        hub.emit("/lib/A.fichero", ChangeEvent(type="entity.updated"))
        hub.emit("/lib/B.fichero", ChangeEvent(type="entity.updated"))
        hub.emit("/lib/A.fichero", ChangeEvent(type="entity.deleted"))

        assert queue_a.get_nowait().event_id == 1
        assert queue_a.get_nowait().event_id == 2
        assert queue_b.get_nowait().event_id == 1

    def test_replay_buffers_are_lru_capped_by_library(self):
        hub = _ChangeHub(replay_library_cap=2)

        hub.emit("/lib/A.fichero", ChangeEvent(type="entity.updated"))
        hub.emit("/lib/B.fichero", ChangeEvent(type="entity.updated"))
        hub.emit("/lib/C.fichero", ChangeEvent(type="entity.updated"))

        assert set(hub._replay_buffers) == {"/lib/B.fichero", "/lib/C.fichero"}
        assert "/lib/A.fichero" not in hub._next_event_ids

    def test_slow_subscriber_queue_stays_bounded_and_signals_gap(self):
        hub = _ChangeHub(subscriber_queue_maxsize=4)
        queue = hub.subscribe("/lib/A.fichero")

        for idx in range(6):
            delivered = hub.emit(
                "/lib/A.fichero",
                ChangeEvent(type="entity.updated", entity_ids=[f"e{idx}"]),
            )
            assert delivered == 1

        assert queue.qsize() == 4
        items = [queue.get_nowait() for _ in range(queue.qsize())]
        gaps = [item for item in items if item.type == "stream.gap"]
        assert gaps
        assert all(item.event_id is None for item in gaps)
        data_event_ids = [
            item.event_id for item in items if item.type != "stream.gap"
        ]
        assert len(data_event_ids) == len(set(data_event_ids))
        assert items[-1].entity_ids == ["e5"]

    @pytest.mark.asyncio
    async def test_emit_from_non_loop_thread_delivers_to_loop_subscriber(self):
        hub = _ChangeHub()
        queue = hub.subscribe("/lib/A.fichero")
        thread_done = threading.Event()

        def _emit() -> None:
            hub.emit(
                "/lib/A.fichero",
                ChangeEvent(type="entity.updated", entity_ids=["threaded"]),
            )
            thread_done.set()

        thread = threading.Thread(target=_emit)
        thread.start()
        try:
            event = await asyncio.wait_for(queue.get(), timeout=1.0)
        finally:
            thread.join(timeout=1.0)

        assert thread_done.is_set()
        assert event.entity_ids == ["threaded"]


# ---------------------------------------------------------------------------
# emit_change convenience + event schema
# ---------------------------------------------------------------------------


class TestEmitChange:
    def test_emit_change_builds_event_with_all_fields(self, monkeypatch):
        captured: list[tuple[str, ChangeEvent]] = []
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda lib, event: captured.append((lib, event)) or 1,
        )

        emit_change(
            "/lib/A.fichero",
            type="entity.merged",
            entity_ids=["e1", "e2"],
            claim_ids=["c1"],
            actor="ui",
            metadata={"task_type": "metrics"},
            origin_window="win-7",
            origin_user="alice",
        )

        assert len(captured) == 1
        lib, event = captured[0]
        assert lib == "/lib/A.fichero"
        assert event.type == "entity.merged"
        assert event.entity_ids == ["e1", "e2"]
        assert event.claim_ids == ["c1"]
        assert event.actor == "ui"
        assert event.metadata == {"task_type": "metrics"}
        assert event.origin_window == "win-7"
        assert event.origin_user == "alice"
        assert event.ts  # default timestamp populated

    def test_db_manager_first_open_emits_library_opened(self, monkeypatch, tmp_path):
        captured: list[tuple[str, ChangeEvent]] = []
        monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
        monkeypatch.setattr(
            change_stream._change_hub,
            "emit",
            lambda lib, event: captured.append((lib, event)) or 1,
        )

        package = tmp_path / "Opened.fichero"
        package.mkdir()

        try:
            db_manager.get_database(package)
        finally:
            db_manager.close_database(package)

        assert captured
        library_path, event = captured[-1]
        assert library_path == str(package)
        assert event.type == "library.opened"
        assert event.actor == "system"
        assert event.metadata == {
            "library_name": "Opened.fichero",
            "source": "db_manager",
        }

    def test_emit_change_blank_library_is_noop(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            change_stream._change_hub, "emit", lambda *a: called.append(a)
        )
        emit_change("", type="entity.updated")
        assert called == []

    def test_emit_change_never_raises(self, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("hub exploded")

        monkeypatch.setattr(change_stream._change_hub, "emit", boom)
        # Best-effort contract: must swallow the error, not propagate.
        emit_change("/lib/A.fichero", type="entity.updated")

    def test_format_change_sse_frame(self):
        frame = format_change_sse(ChangeEvent(type="entity.updated", entity_ids=["e1"]))
        assert frame.startswith("data: ")
        assert frame.endswith("\n\n")
        assert '"type":"entity.updated"' in frame

    def test_format_change_sse_includes_id_when_present(self):
        event = ChangeEvent(type="entity.updated", entity_ids=["e1"], event_id=7)
        frame = format_change_sse(event)
        assert frame.startswith("id: 7\n")


# ---------------------------------------------------------------------------
# Light route test: the merge endpoint emits a change event
# ---------------------------------------------------------------------------


def _make_entity(db, name: str) -> KnowledgeEntity:
    entity = KnowledgeEntity(
        canonical_name=name,
        entity_type=EntityType.person,
        aliases=[name.lower()],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(entity)
    return entity


class TestMergeEmitsChange:
    def test_merge_endpoint_calls_emit_change(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []

        def _spy(library_path, **kwargs):
            captured.append({"library_path": library_path, **kwargs})

        monkeypatch.setattr("fichero_server.api.change_stream.emit_change", _spy)

        absorber = _make_entity(db, "Alice")
        absorbed = _make_entity(db, "Alicia")

        r = client.post(
            "/api/kg/entity-curation/merge",
            json={
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
        )
        assert r.status_code == 200

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "entity.merged"
        assert absorber.id in call["entity_ids"]
        assert absorbed.id in call["entity_ids"]


# ---------------------------------------------------------------------------
# Claim + document mutation routes emit change events (#1863 extension)
# ---------------------------------------------------------------------------


def _make_claim(db, text: str = "Marshall kept a diary.") -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text=text,
        source_document_id="doc-claim-src",
        subject_canonical="Marshall",
        predicate_verb="kept",
        object_phrase="a diary",
        source_excerpt=text,
    )
    db.save(claim)
    return claim


def _make_document(db, doc_id: str, name: str) -> Document:
    doc = Document(
        id=doc_id,
        name=name,
        doc_type=DocType.file,
        file_type=FileType.text,
        status=Status.completed,
        page_content="Some body text.",
    )
    db.save(doc)
    return doc


def _make_annotation(
    db,
    document_id: str = "doc-emit-annotation",
    kind: AnnotationKind = AnnotationKind.note,
    text: str = "Highlight me",
    page_id: str | None = None,
    folder_id: str | None = None,
) -> Annotation:
    ann = Annotation(
        document_id=document_id,
        kind=kind,
        text=text,
        page_id=page_id,
        folder_id=folder_id,
    )
    db.save(ann)
    return ann


def _make_folder(db, folder_id: str, name: str) -> Document:
    folder = Document(
        id=folder_id,
        name=name,
        doc_type=DocType.folder,
        status=Status.completed,
    )
    db.save(folder)
    return folder


def _make_note(
    db,
    title: str,
    folder_id: str | None = None,
) -> Note:
    note = Note(title=title, body="", folder_id=folder_id)
    db.save(note)
    return note


class TestClaimMutationsEmitChange:
    def test_create_claim_calls_emit_change(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.claim.claims.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        doc = _make_document(db, "doc-claim-create", "claim-create.txt")
        r = client.post(
            "/api/claims",
            json={"text": "Created claim.", "source_document_id": doc.id},
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "claim.updated"
        assert r.json()["id"] in call["claim_ids"]

    def test_assign_time_period_calls_emit_change(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.claim.claims.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        source_doc = _make_document(db, "doc-claim-src", "source.txt")
        claim = _make_claim(db)
        _ = source_doc

        r = client.post(
            "/api/claims/assign-time-period",
            json={
                "source_document_id": source_doc.id,
                "time_start": "2020-01-01",
                "time_precision": "year",
            },
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "claim.updated"
        assert claim.id in call["claim_ids"]

    def test_patch_claim_calls_emit_change(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.claim.claims.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        claim = _make_claim(db)
        r = client.patch(f"/api/claims/{claim.id}", json={"text": "Updated text."})
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "claim.updated"
        assert claim.id in call["claim_ids"]

    def test_delete_claim_calls_emit_change(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.claim.claims.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        claim = _make_claim(db)
        r = client.delete(f"/api/claims/{claim.id}")
        assert r.status_code == 204, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "claim.deleted"
        assert claim.id in call["claim_ids"]


class TestEntityMutationsEmitChange:
    def test_create_entity_calls_emit_change(self, client, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.entity.entities.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        r = client.post(
            "/api/entities",
            json={"canonical_name": "Nikolai", "entity_type": "person"},
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "entity.created"
        assert r.json()["id"] in call["entity_ids"]

    def test_add_entity_aliases_calls_emit_change(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.entity.entities.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        entity = _make_entity(db, "Nikolai")

        r = client.post(
            f"/api/entities/{entity.id}/aliases",
            json={"aliases": ["Nikolai Tesla"]},
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "entity.updated"
        assert entity.id in call["entity_ids"]

    def test_create_claim_link_emits_linked(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        claim_a = _make_claim(db, "Claim A text.")
        claim_b = _make_claim(db, "Claim B text.")
        r = client.post(
            f"/api/claims/{claim_a.id}/links",
            json={
                "related_claim_id": claim_b.id,
                "relation_type": "supports",
            },
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "claim.linked"
        assert claim_a.id in call["claim_ids"]
        assert claim_b.id in call["claim_ids"]


class TestAnnotationMutationsEmitChange:
    def test_create_annotation_emits_created(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        doc = _make_document(db, "doc-emit-ann", "emit.txt")
        resp = client.post(
            "/api/annotations",
            json={"document_id": doc.id, "kind": "note", "text": "Annotation"},
        )
        assert resp.status_code == 200, resp.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "annotation.created"
        assert doc.id in call["document_ids"]

    def test_patch_annotation_emits_updated(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        ann = _make_annotation(db, document_id="doc-emit-ann-2", text="old")
        resp = client.patch(f"/api/annotations/{ann.id}", json={"text": "updated"})
        assert resp.status_code == 200, resp.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "annotation.updated"
        assert ann.document_id in call["document_ids"]

    def test_delete_annotation_emits_deleted(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        ann = _make_annotation(db, document_id="doc-emit-ann-3", text="bye")
        resp = client.delete(f"/api/annotations/{ann.id}")
        assert resp.status_code == 204, resp.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "annotation.deleted"
        assert ann.document_id in call["document_ids"]

    def test_promote_to_claim_emits_updated_and_claim_created(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.document.annotations.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        ann = _make_annotation(
            db, document_id="doc-emit-ann-promote", text="Promote me"
        )
        resp = client.post(f"/api/annotations/{ann.id}/promote-to-claim")
        assert resp.status_code == 200, resp.text

        assert len(captured) == 2
        events = {call["type"] for call in captured}
        assert events == {"annotation.updated", "claim.created"}
        annotation_events = [
            call for call in captured if call["type"] == "annotation.updated"
        ]
        claim_events = [call for call in captured if call["type"] == "claim.created"]
        assert len(annotation_events) == 1
        assert len(claim_events) == 1
        assert annotation_events[0]["library_path"] == str(test_package)
        assert ann.document_id in annotation_events[0]["document_ids"]
        created = resp.json()
        assert claim_events[0]["library_path"] == str(test_package)
        assert created["claim_id"] in claim_events[0]["claim_ids"]


class TestWorkflowMutationsEmitChange:
    def test_create_workflow_emits_created(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.workflow.workflows.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        r = client.post(
            "/api/workflows",
            json={
                "name": "Coverage Workflow",
                "nodes": [],
                "edges": [],
            },
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "workflow.created"
        assert call["actor"] == "owner"

    def test_delete_workflow_emits_deleted(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.workflow.workflows.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        created = client.post(
            "/api/workflows",
            json={
                "name": "To Delete",
                "nodes": [],
                "edges": [],
            },
        )
        assert created.status_code == 200, created.text
        workflow_id = created.json()["id"]

        del_resp = client.delete(f"/api/workflows/{workflow_id}")
        assert del_resp.status_code == 200, del_resp.text

        assert len(captured) == 2
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "workflow.deleted"
        assert call["actor"] == "owner"


class TestNoteMutationsEmitChange:
    def test_create_note_emits_created(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.document.notes.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        folder = _make_folder(db, "folder-emit-note", "Scope Folder")
        resp = client.post(
            "/api/notes",
            json={"title": "Test", "body": "Hello", "folder_id": folder.id},
        )
        assert resp.status_code == 200, resp.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "note.created"
        assert folder.id in call["document_ids"]

    def test_patch_note_emits_updated(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.document.notes.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        folder = _make_folder(db, "folder-emit-note-2", "Scope Folder 2")
        note = client.post(
            "/api/notes",
            json={
                "title": "Note",
                "body": "Body",
                "folder_id": folder.id,
            },
        ).json()
        assert note["id"]
        resp = client.patch(f"/api/notes/{note['id']}", json={"title": "Updated"})
        assert resp.status_code == 200, resp.text

        assert len(captured) == 2
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "note.updated"
        assert folder.id in call["document_ids"]

    def test_delete_note_emits_deleted(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.document.notes.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        folder = _make_folder(db, "folder-emit-note-3", "Scope Folder 3")
        created = client.post(
            "/api/notes",
            json={"title": "Note", "body": "Body", "folder_id": folder.id},
        )
        assert created.status_code == 200, created.text
        note = created.json()
        del_resp = client.delete(f"/api/notes/{note['id']}")
        assert del_resp.status_code == 204, del_resp.text

        assert len(captured) == 2
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "note.deleted"
        assert folder.id in call["document_ids"]

    def test_create_note_link_emits_updated(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.document.notes.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        folder = _make_folder(db, "folder-emit-note-link", "Scope Folder link")
        source_note = _make_note(db, "Source Note", folder_id=folder.id)
        target_note = _make_note(db, "Target Note")

        r = client.post(
            f"/api/notes/{source_note.id}/links",
            json={"target_note_id": target_note.id},
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "note.updated"
        assert call["actor"] == "owner"
        assert folder.id in call["document_ids"]


class TestResearchNoteMutationsEmitChange:
    def test_create_research_note_emits_created(
        self, client, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.research.notes.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        project = client.post(
            "/api/research/projects", json={"name": "For Research Notes"}
        )
        assert project.status_code == 200, project.text
        project_id = project.json()["id"]

        resp = client.post(
            "/api/research/notes",
            json={
                "project_id": project_id,
                "note_type": "observation",
                "content": "Observation",
            },
        )
        assert resp.status_code == 200, resp.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "note.created"

    def test_update_research_note_emits_updated(
        self, client, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.research.notes.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        project = client.post(
            "/api/research/projects", json={"name": "For Research Notes 2"}
        )
        assert project.status_code == 200, project.text
        project_id = project.json()["id"]

        note = client.post(
            "/api/research/notes",
            json={
                "project_id": project_id,
                "note_type": "observation",
                "content": "Observation",
            },
        )
        assert note.status_code == 200, note.text
        note_id = note.json()["id"]

        resp = client.patch(
            f"/api/research/notes/{note_id}",
            json={"content": "updated", "note_type": "finding"},
        )
        assert resp.status_code == 200, resp.text

        assert len(captured) == 2
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "note.updated"


class TestDocumentMutationsEmitChange:
    def test_create_document_emits_created(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.document.documents.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        r = client.post(
            "/api/documents",
            json={"name": "emit-created.txt", "doc_type": "file"},
        )
        assert r.status_code == 201, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "document.created"
        assert call["document_ids"] and r.json()["id"] in call["document_ids"]

    def test_update_document_emits_updated(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        doc = _make_document(db, "doc-emit-update", "before.txt")
        r = client.put(f"/api/documents/{doc.id}", json={"name": "after.txt"})
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "document.updated"
        assert doc.id in call["document_ids"]

    def test_delete_document_emits_deleted(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.document.documents.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        doc = _make_document(db, "doc-emit-delete", "doomed.txt")
        r = client.delete(f"/api/documents/{doc.id}")
        assert r.status_code == 204, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "document.deleted"
        assert doc.id in call["document_ids"]


class TestActionMutationsEmitChange:
    def test_create_action_emits_created(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.system.actions.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        payload = {
            "name": "Observable Action",
            "description": "emits",
            "category": "custom",
            "tags": [],
            "icon": "square",
            "node_template": {},
            "nodes": [],
            "edges": [],
            "author": "qa",
        }
        r = client.post("/api/actions", json=payload)
        assert r.status_code == 200, r.text
        created = r.json()

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "action.created"
        assert created["id"] in call["entity_ids"]

    def test_update_action_emits_updated(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.system.actions.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        created = client.post(
            "/api/actions",
            json={
                "name": "Original",
                "description": "",
                "category": "custom",
                "tags": [],
                "icon": "square",
                "node_template": {},
                "nodes": [],
                "edges": [],
                "author": "",
            },
        ).json()
        r = client.put(f"/api/actions/{created['id']}", json={"name": "Updated"})
        assert r.status_code == 200, r.text

        assert len(captured) >= 1
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "action.updated"
        assert created["id"] in call["entity_ids"]

    def test_delete_action_emits_deleted(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.system.actions.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        created = client.post(
            "/api/actions",
            json={
                "name": "To Delete",
                "description": "",
                "category": "custom",
                "tags": [],
                "icon": "square",
                "node_template": {},
                "nodes": [],
                "edges": [],
                "author": "",
            },
        ).json()
        r = client.delete(f"/api/actions/{created['id']}")
        assert r.status_code == 200, r.text

        assert len(captured) >= 1
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "action.deleted"
        assert created["id"] in call["entity_ids"]


class TestResearchMutationsEmitChange:
    def test_create_project_emits_created(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.research.crud.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        r = client.post("/api/research/projects", json={"name": "Research One"})
        assert r.status_code == 200, r.text
        project = r.json()

        # #4335: the project mirrors into the document tree (workspace node),
        # so the mutation emits BOTH research.created and document.created —
        # the sidebar listens on the document domain.
        assert len(captured) == 2
        assert [c["type"] for c in captured] == ["research.created", "document.created"]
        for call in captured:
            assert call["library_path"] == str(test_package)
            assert project["id"] in call["entity_ids"]

    def test_patch_project_emits_updated(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.research.crud.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )
        project = client.post(
            "/api/research/projects", json={"name": "Research Project"}
        ).json()

        r = client.patch(
            f"/api/research/projects/{project['id']}", json={"name": "Renamed"}
        )
        assert r.status_code == 200, r.text

        # #4335: the workspace mirror means the update pairs with a
        # document.updated event for the same id.
        assert len(captured) >= 2
        assert captured[-2]["type"] == "research.updated"
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "document.updated"
        assert project["id"] in call["entity_ids"]

    def test_delete_project_emits_deleted(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.research.crud.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )
        project = client.post(
            "/api/research/projects", json={"name": "To Delete"}
        ).json()

        r = client.delete(f"/api/research/projects/{project['id']}")
        assert r.status_code == 200, r.text

        # #4335: deleting the project deletes its workspace mirror node, so a
        # document.deleted follows the research.deleted for the same id.
        assert len(captured) >= 2
        assert captured[-2]["type"] == "research.deleted"
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "document.deleted"
        assert project["id"] in call["entity_ids"]


class TestProjectsMutationsEmitChange:
    def test_create_projects_route_emits_created(
        self, client, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.system.projects.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        r = client.post("/api/projects", json={"name": "Workspace One"})
        assert r.status_code == 200, r.text
        project = r.json()

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "research.created"
        assert project["id"] in call["entity_ids"]

    def test_patch_projects_route_emits_updated(
        self, client, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.system.projects.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )
        project = client.post("/api/projects", json={"name": "Workspace Two"}).json()

        r = client.patch(
            f"/api/projects/{project['id']}", json={"name": "Renamed Workspace"}
        )
        assert r.status_code == 200, r.text

        assert len(captured) >= 1
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "research.updated"
        assert project["id"] in call["entity_ids"]

    def test_delete_projects_route_emits_deleted(
        self, client, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.routes.system.projects.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )
        project = client.post("/api/projects", json={"name": "Workspace Three"}).json()

        r = client.delete(f"/api/projects/{project['id']}")
        assert r.status_code == 204, r.text

        assert len(captured) >= 1
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "research.deleted"
        assert project["id"] in call["entity_ids"]


def _make_artifact(
    db,
    doc_id: str,
    artifact_type: str = "transcription",
    content: str = "sample text",
) -> Artifact:
    artifact = Artifact(
        document_id=doc_id,
        artifact_type=artifact_type,
        content=content,
        version=1,
        created_at=datetime.now(),
    )
    db.save(artifact)
    return artifact


def _make_reference(title: str = "A Sample Reference") -> Reference:
    return Reference(
        title=title,
        kind="article",
    )


class TestObservableMutationEmitChange:
    def test_create_artifact_route_emits_artifact_created(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        doc = _make_document(db, "doc-emit-artifact", "artifact.txt")
        r = client.post(
            "/api/artifacts/",
            json={
                "document_id": doc.id,
                "artifact_type": "transcription",
                "content": "sample text",
            },
        )
        assert r.status_code == 200, r.text
        artifact = r.json()

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "artifact.created"
        assert artifact["id"] in call["artifact_ids"]

    def test_create_citation_route_emits_citation_created(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        source = _make_document(db, "citation-source", "source.txt")
        r = client.post(
            "/api/citations/graph",
            json={
                "source_document_id": source.id,
                "target_citation_text": "Smith, 2020",
                "detector": "manual",
            },
        )
        assert r.status_code == 200, r.text
        citation = r.json()

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "citation.created"
        assert citation["id"] in call["citation_ids"]
        assert source.id in call["document_ids"]

    def test_patch_reference_route_emits_reference_updated(
        self, client, db, test_package, monkeypatch
    ):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        reference = _make_reference("A Sample Reference")
        db.save(reference)
        r = client.patch(
            f"/api/references/{reference.id}",
            json={"notes": "Updated in test"},
        )
        assert r.status_code == 200, r.text

        assert len(captured) >= 1
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "reference.updated"
        assert reference.id in call["reference_ids"]


# ---------------------------------------------------------------------------
# Hermeneutics mutation routes emit change events (#2008, part of #2000)
#
# All hermeneutics objects (frameworks, interpretations, patterns, circle
# states) broadcast under the single domain "interpretation" so the
# doc-scoped interpretation store (#2009) can observe one domain and reload
# on any interpretation.* event.
# ---------------------------------------------------------------------------


def _make_framework(db, name: str = "Marxist Materialism") -> InterpretiveFramework:
    framework = InterpretiveFramework(
        name=name,
        framework_type=FrameworkType.historical,
        description="A framework for analyzing labor relations.",
    )
    db.save(framework)
    return framework


def _make_interpretation(db, framework_id: str, claim_id: str) -> Interpretation:
    interpretation = Interpretation(
        framework_id=framework_id,
        claim_id=claim_id,
        interpretation_text="Under this framework, the diary records material conditions.",
        act=InterpretiveActType.contextualizing,
    )
    db.save(interpretation)
    return interpretation


def _make_pattern(db, name: str = "Cyclical history") -> PatternInstance:
    pattern = PatternInstance(
        name=name,
        description="A recurring cyclical motif.",
        pattern_type="temporal",
        status=PatternStatus.tentative,
    )
    db.save(pattern)
    return pattern


def _make_circle_state(db, claim_id: str) -> HermeneuticCircleState:
    state = HermeneuticCircleState(
        claim_id=claim_id,
        current_focus="whole",
        focus_id="focus-whole",
        focus_label="The whole diary",
        direction=CircleNavigationDirection.whole_to_part,
    )
    db.save(state)
    return state


class TestHermeneuticsMutationsEmitChange:
    def _spy(self, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero_server.api.change_stream.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )
        return captured

    # ---- Frameworks ----

    def test_create_framework_emits_created(
        self, client, db, test_package, monkeypatch
    ):
        captured = self._spy(monkeypatch)

        r = client.post(
            "/api/hermeneutics/frameworks",
            json={
                "name": "Phenomenology",
                "framework_type": "methodological",
                "description": "Lived experience as evidence.",
            },
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.created"
        assert r.json()["id"] in call["interpretation_ids"]

    def test_update_framework_emits_updated(
        self, client, db, test_package, monkeypatch
    ):
        captured = self._spy(monkeypatch)

        framework = _make_framework(db)
        r = client.patch(
            f"/api/hermeneutics/frameworks/{framework.id}",
            json={"description": "Revised description."},
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.updated"
        assert framework.id in call["interpretation_ids"]

    def test_delete_framework_emits_deleted(
        self, client, db, test_package, monkeypatch
    ):
        captured = self._spy(monkeypatch)

        framework = _make_framework(db)
        r = client.delete(f"/api/hermeneutics/frameworks/{framework.id}")
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.deleted"
        assert framework.id in call["interpretation_ids"]

    # ---- Interpretations ----

    def test_create_interpretation_emits_created(
        self, client, db, test_package, monkeypatch
    ):
        captured = self._spy(monkeypatch)

        framework = _make_framework(db)
        claim = _make_claim(db)
        r = client.post(
            "/api/hermeneutics/interpretations",
            json={
                "framework_id": framework.id,
                "claim_id": claim.id,
                "interpretation_text": "It means X under the framework.",
                "act": "reading",
            },
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.created"
        assert r.json()["id"] in call["interpretation_ids"]
        assert claim.id in call["claim_ids"]

    def test_update_interpretation_emits_updated(
        self, client, db, test_package, monkeypatch
    ):
        captured = self._spy(monkeypatch)

        framework = _make_framework(db)
        claim = _make_claim(db)
        interpretation = _make_interpretation(db, framework.id, claim.id)
        r = client.patch(
            f"/api/hermeneutics/interpretations/{interpretation.id}",
            json={"interpretation_text": "Revised interpretation."},
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.updated"
        assert interpretation.id in call["interpretation_ids"]

    # ---- Patterns ----

    def test_create_pattern_emits_created(self, client, db, test_package, monkeypatch):
        captured = self._spy(monkeypatch)

        r = client.post(
            "/api/hermeneutics/patterns",
            json={
                "name": "Recurrence",
                "description": "A repeating motif.",
                "pattern_type": "thematic",
            },
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.created"
        assert r.json()["id"] in call["interpretation_ids"]

    def test_update_pattern_emits_updated(self, client, db, test_package, monkeypatch):
        captured = self._spy(monkeypatch)

        pattern = _make_pattern(db)
        r = client.patch(
            f"/api/hermeneutics/patterns/{pattern.id}",
            json={"description": "Updated motif."},
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.updated"
        assert pattern.id in call["interpretation_ids"]

    def test_add_claim_to_pattern_emits_updated(
        self, client, db, test_package, monkeypatch
    ):
        captured = self._spy(monkeypatch)

        pattern = _make_pattern(db)
        claim = _make_claim(db)
        r = client.post(
            f"/api/hermeneutics/patterns/{pattern.id}/claims/{claim.id}",
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.updated"
        assert pattern.id in call["interpretation_ids"]
        assert claim.id in call["claim_ids"]

    # ---- Hermeneutic circle state ----

    def test_create_circle_state_emits_created(
        self, client, db, test_package, monkeypatch
    ):
        captured = self._spy(monkeypatch)

        claim = _make_claim(db)
        r = client.post(
            "/api/hermeneutics/circle-state",
            json={
                "claim_id": claim.id,
                "current_focus": "whole",
                "focus_id": "f-whole",
                "focus_label": "The whole",
                "direction": "whole_to_part",
            },
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.created"
        assert r.json()["id"] in call["interpretation_ids"]
        assert claim.id in call["claim_ids"]

    def test_navigate_circle_emits_updated(self, client, db, test_package, monkeypatch):
        captured = self._spy(monkeypatch)

        claim = _make_claim(db)
        state = _make_circle_state(db, claim.id)
        r = client.post(
            f"/api/hermeneutics/circle-state/{state.id}/navigate",
            json={
                "direction": "whole_to_part",
                "focus_id": "f-part",
                "focus_label": "A part",
            },
        )
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.updated"
        assert state.id in call["interpretation_ids"]

    def test_backtrack_circle_emits_updated(
        self, client, db, test_package, monkeypatch
    ):
        captured = self._spy(monkeypatch)

        claim = _make_claim(db)
        state = _make_circle_state(db, claim.id)
        # backtrack requires a prior_state_id to actually mutate + emit
        state.prior_state_id = state.id
        db.save(state)

        r = client.post(f"/api/hermeneutics/circle-state/{state.id}/backtrack")
        assert r.status_code == 200, r.text

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "interpretation.updated"
        assert state.id in call["interpretation_ids"]


# ---------------------------------------------------------------------------
# library_path key canonicalization (#2518)
#
# The SSE subscriber registers under the RAW X-Fichero-Library-Path header,
# while workflow completion emits under str(db.path.parent) (path-normalized).
# A trailing slash (or other non-canonical form) on one side used to route the
# emit to a dead key with zero subscribers — the live-update never arrived.
# Both seams now funnel through _ChangeHub._canonical_key.
# ---------------------------------------------------------------------------


class TestLibraryPathCanonicalization:
    def test_trailing_slash_subscriber_receives_slashless_emit(self):
        """Subscribe under '/lib/Foo.fichero/' (trailing slash, as a header may
        carry it) and emit under '/lib/Foo.fichero' (as str(Path(...)) yields):
        the event MUST still be delivered. RED before canonicalization, GREEN
        after."""
        hub = _ChangeHub()
        queue = hub.subscribe("/lib/Foo.fichero/")  # raw header form

        event = ChangeEvent(type="document.updated", document_ids=["d1"])
        delivered = hub.emit("/lib/Foo.fichero", event)  # path-derived form

        assert delivered == 1
        assert queue.get_nowait() is event

    def test_same_key_still_delivers(self):
        """Canonicalization must not regress the identical-key path."""
        hub = _ChangeHub()
        queue = hub.subscribe("/lib/Foo.fichero")

        event = ChangeEvent(type="entity.updated", entity_ids=["e1"])
        assert hub.emit("/lib/Foo.fichero", event) == 1
        assert queue.get_nowait() is event

    def test_canonical_subscriber_count_matches_either_form(self):
        hub = _ChangeHub()
        hub.subscribe("/lib/Foo.fichero/")
        # Either spelling resolves to the same canonical key.
        assert hub.subscriber_count("/lib/Foo.fichero") == 1
        assert hub.subscriber_count("/lib/Foo.fichero/") == 1

    def test_unsubscribe_canonicalizes(self):
        hub = _ChangeHub()
        queue = hub.subscribe("/lib/Foo.fichero/")
        hub.unsubscribe("/lib/Foo.fichero", queue)  # slashless form
        assert hub.subscriber_count("/lib/Foo.fichero/") == 0

    def test_emit_to_zero_subscribers_with_other_key_warns(self, caplog):
        """No-silent-fallback: emitting into the void while OTHER libraries have
        live subscribers logs a WARNING naming both keys, so genuine key drift is
        loud, not silent."""
        import logging

        hub = _ChangeHub()
        hub.subscribe("/lib/A.fichero")  # a different, genuinely distinct library

        event = ChangeEvent(type="document.updated", document_ids=["d1"])
        with caplog.at_level(logging.WARNING, logger="fichero_server.api.change_stream"):
            delivered = hub.emit("/lib/B.fichero", event)

        assert delivered == 0
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("0 subscribers" in r.getMessage() for r in warnings)
        msg = warnings[0].getMessage()
        assert "/lib/B.fichero" in msg  # the dead emit key
        assert "/lib/A.fichero" in msg  # the live key it drifted from

    def test_emit_to_zero_subscribers_no_other_keys_is_quiet(self, caplog):
        """An emit to a library nobody is watching (the common idle case) must
        NOT warn — that would be noise, not signal."""
        import logging

        hub = _ChangeHub()
        event = ChangeEvent(type="document.updated", document_ids=["d1"])
        with caplog.at_level(logging.WARNING, logger="fichero_server.api.change_stream"):
            assert hub.emit("/lib/Lonely.fichero", event) == 0

        assert not [r for r in caplog.records if r.levelno == logging.WARNING]


# ---------------------------------------------------------------------------
# Terminal workflow-node emits (#2518) — the core "I can't see results" bug.
#
# A workflow runs to completion server-side but the UI shows nothing live: the
# terminal nodes wrote state (completed status, finalized KG) yet broadcast ONLY
# to the per-run progress stream, never to the library change-stream. These tests
# drive the real terminal functions against a real temp library with a live
# change-stream subscriber and assert the change events now arrive.
# RED before the emits were added, GREEN after.
# ---------------------------------------------------------------------------


class TestTerminalNodeEmits:
    def test_complete_run_documents_emits_document_updated(self, db):
        """Marking a run's docs completed must broadcast document.updated so the
        green-check status appears live (centralised emit covers main + batch)."""
        from pathlib import Path

        from fichero_server.workflows.completion import complete_run_documents

        library_path = str(Path(db.path).parent)
        doc = Document(
            id="doc-term-1",
            name="terminal",
            doc_type=DocType.file,
            file_type=FileType.text,
            status=Status.processing,  # only processing docs advance → emit
            page_content="x",
        )
        db.save(doc)

        queue = change_stream._change_hub.subscribe(library_path)
        try:
            updated = complete_run_documents(db, {"doc-term-1"})
            assert updated == 1
            event = queue.get_nowait()
            assert event.type == "document.updated"
            assert "doc-term-1" in event.document_ids
            assert event.actor == "workflow"
        finally:
            change_stream._change_hub.unsubscribe(library_path, queue)

    def test_complete_run_documents_no_change_no_emit(self, db):
        """An already-completed doc isn't re-saved, so nothing is broadcast —
        no spurious events (and no empty-document_ids noise)."""
        from pathlib import Path

        from fichero_server.workflows.completion import complete_run_documents

        library_path = str(Path(db.path).parent)
        doc = Document(
            id="doc-term-2",
            name="already-done",
            doc_type=DocType.file,
            file_type=FileType.text,
            status=Status.completed,
            page_content="x",
        )
        db.save(doc)

        queue = change_stream._change_hub.subscribe(library_path)
        try:
            assert complete_run_documents(db, {"doc-term-2"}) == 0
            with pytest.raises(asyncio.QueueEmpty):
                queue.get_nowait()
        finally:
            change_stream._change_hub.unsubscribe(library_path, queue)

    def test_kg_persist_finalize_emits_kg_changes(self, db, monkeypatch):
        """Finalize must broadcast entity/claim/document updates so the KG and
        entity/claim views refresh live. The heavy KG machinery (rebuild_kg,
        embeddings, support counts) is stubbed — this isolates the EMIT, which
        is the behaviour #2518 was missing."""
        import asyncio as _asyncio
        from pathlib import Path

        from fichero_server.llm import LLMConfig
        from fichero_server.workflows.tools import kg_persist_finalize as kpf

        library_path = str(Path(db.path).parent)
        doc = Document(
            id="doc-kgf-1",
            name="finalize",
            doc_type=DocType.file,
            file_type=FileType.text,
            status=Status.completed,
            page_content="x",
        )
        db.save(doc)

        monkeypatch.setattr(kpf, "_coerce_documents", lambda raw, _db, _lp: [doc])
        monkeypatch.setattr(kpf, "_descendant_doc_ids", lambda _db, _ids: {"doc-kgf-1"})
        monkeypatch.setattr(kpf, "persist_support_counts", lambda _db: 0)
        monkeypatch.setattr(kpf, "rebuild_kg", lambda *a, **k: {"triples_written": 0})
        monkeypatch.setattr(kpf, "_vector_row_count", lambda *a, **k: 0)

        queue = change_stream._change_hub.subscribe(library_path)
        try:
            _asyncio.run(
                kpf.kg_persist_finalize(
                    inputs={"documents": [doc]},
                    state={"library_path": library_path},
                    llm_config=LLMConfig(provider="", model=""),
                )
            )
            types_seen: set[str] = set()
            while True:
                try:
                    types_seen.add(queue.get_nowait().type)
                except asyncio.QueueEmpty:
                    break
            assert "entity.updated" in types_seen
            assert "claim.updated" in types_seen
            assert "document.updated" in types_seen
        finally:
            change_stream._change_hub.unsubscribe(library_path, queue)
