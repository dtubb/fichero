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
from datetime import datetime

import pytest

from fichero.api import change_stream
from fichero.api.change_stream import (
    ChangeEvent,
    _ChangeHub,
    emit_change,
    format_change_sse,
)
from fichero.knowledge_models import (
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
)
from fichero.models import DocType, Document, FileType, Status


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
            origin_window="win-7",
        )

        assert len(captured) == 1
        lib, event = captured[0]
        assert lib == "/lib/A.fichero"
        assert event.type == "entity.merged"
        assert event.entity_ids == ["e1", "e2"]
        assert event.claim_ids == ["c1"]
        assert event.actor == "ui"
        assert event.origin_window == "win-7"
        assert event.ts  # default timestamp populated

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
    def test_merge_endpoint_calls_emit_change(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []

        def _spy(library_path, **kwargs):
            captured.append({"library_path": library_path, **kwargs})

        # Patch the name as imported into the route module.
        monkeypatch.setattr(
            "fichero.api.routes.kg_entity_curation.emit_change", _spy
        )

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


class TestClaimMutationsEmitChange:
    def test_patch_claim_calls_emit_change(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero.api.routes.claims.emit_change",
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

    def test_create_claim_link_emits_linked(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero.api.routes.claim_links.emit_change",
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


class TestDocumentMutationsEmitChange:
    def test_update_document_emits_updated(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero.api.routes.documents.emit_change",
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
            "fichero.api.routes.documents.emit_change",
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
            "fichero.api.routes.actions.emit_change",
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
            "fichero.api.routes.actions.emit_change",
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
            "fichero.api.routes.actions.emit_change",
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
            "fichero.api.routes.research_crud.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )

        r = client.post("/api/research/projects", json={"name": "Research One"})
        assert r.status_code == 200, r.text
        project = r.json()

        assert len(captured) == 1
        call = captured[0]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "research.created"
        assert project["id"] in call["entity_ids"]

    def test_patch_project_emits_updated(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero.api.routes.research_crud.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )
        project = client.post("/api/research/projects", json={"name": "Research Project"}).json()

        r = client.patch(f"/api/research/projects/{project['id']}", json={"name": "Renamed"})
        assert r.status_code == 200, r.text

        assert len(captured) >= 1
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "research.updated"
        assert project["id"] in call["entity_ids"]

    def test_delete_project_emits_deleted(self, client, db, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero.api.routes.research_crud.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )
        project = client.post("/api/research/projects", json={"name": "To Delete"}).json()

        r = client.delete(f"/api/research/projects/{project['id']}")
        assert r.status_code == 200, r.text

        assert len(captured) >= 1
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "research.deleted"
        assert project["id"] in call["entity_ids"]


class TestProjectsMutationsEmitChange:
    def test_create_projects_route_emits_created(self, client, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero.api.routes.projects.emit_change",
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

    def test_patch_projects_route_emits_updated(self, client, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero.api.routes.projects.emit_change",
            lambda library_path, **kwargs: captured.append(
                {"library_path": library_path, **kwargs}
            ),
        )
        project = client.post("/api/projects", json={"name": "Workspace Two"}).json()

        r = client.patch(f"/api/projects/{project['id']}", json={"name": "Renamed Workspace"})
        assert r.status_code == 200, r.text

        assert len(captured) >= 1
        call = captured[-1]
        assert call["library_path"] == str(test_package)
        assert call["type"] == "research.updated"
        assert project["id"] in call["entity_ids"]

    def test_delete_projects_route_emits_deleted(self, client, test_package, monkeypatch):
        captured: list[dict] = []
        monkeypatch.setattr(
            "fichero.api.routes.projects.emit_change",
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
