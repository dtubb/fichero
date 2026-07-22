"""Tests for generic library item links (#2590 backend slice).

LibraryItemLink connects any two library items (document, note, entity,
claim) via source_id/target_id and reuses the typed ClaimRelationType
vocabulary from KnowledgeClaimLink. These tests cover the canonical
/api/library/links CRUD plus the legacy /api/links alias.
"""

import asyncio
from types import SimpleNamespace

from datetime import datetime

import fichero.api.routes.actions_registry  # noqa: F401
from fichero.actions.registry import ActionContext
from fichero.api.routes.actions_registry import undo_action
from fichero.models.knowledge import (
    ClaimRelationType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
    LibraryItemLink,
    LibraryItemType,
)
from fichero.models import ActionAudit, Document, DocType, Note


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_document(db, name: str = "Source") -> Document:
    doc = Document(name=name, doc_type=DocType.file)
    db.save(doc)
    return doc


def _make_note(db, target: Document) -> Note:
    note = Note(target_type="Document", target_id=target.id, content="annotation")
    db.save(note)
    return note


def _make_entity(db, canonical_name: str = "Entity") -> KnowledgeEntity:
    entity = KnowledgeEntity(canonical_name=canonical_name)
    db.save(entity)
    return entity


def _make_claim(db, doc: Document, text: str = "A claim") -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text=text,
        source_document_id=doc.id,
        entity_ids=[],
        confidence=0.7,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db.save(claim)
    return claim


def _request(base_url="https://engine.local:8765/"):
    return SimpleNamespace(state=SimpleNamespace(user=None), base_url=base_url)


def _undo(db, audit_id: str, library_path: str):
    return asyncio.run(
        undo_action(
            audit_id,
            request=_request(),
            db=db,
            ctx=ActionContext(actor="tester", library_path=library_path),
            x_fichero_library_path=library_path,
            x_fichero_origin_window=None,
        )
    )


# ---------------------------------------------------------------------------
# POST /api/library/links
# ---------------------------------------------------------------------------


class TestCreateLibraryLink:
    def test_create_document_to_entity_link(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        r = client.post("/api/library/links", json={
            "source_id": doc.id,
            "source_type": "document",
            "target_id": entity.id,
            "target_type": "entity",
            "relation_type": "related_to",
        })
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["source_id"] == doc.id
        assert data["source_type"] == "document"
        assert data["target_id"] == entity.id
        assert data["target_type"] == "entity"
        assert data["relation_type"] == "related_to"

    def test_missing_source_returns_404(self, client, db):
        entity = _make_entity(db)
        r = client.post("/api/library/links", json={
            "source_id": "missing-id",
            "source_type": "document",
            "target_id": entity.id,
            "target_type": "entity",
            "relation_type": "related_to",
        })
        assert r.status_code == 404

    def test_missing_target_returns_404(self, client, db):
        doc = _make_document(db)
        r = client.post("/api/library/links", json={
            "source_id": doc.id,
            "source_type": "document",
            "target_id": "missing-id",
            "target_type": "entity",
            "relation_type": "related_to",
        })
        assert r.status_code == 404

    def test_invalid_item_type_returns_400(self, client, db):
        doc = _make_document(db)
        r = client.post("/api/library/links", json={
            "source_id": doc.id,
            "source_type": "not-a-type",
            "target_id": doc.id,
            "target_type": "document",
            "relation_type": "related_to",
        })
        assert r.status_code == 422

    def test_legacy_alias_still_works(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        r = client.post("/api/links", json={
            "source_id": doc.id,
            "source_type": "document",
            "target_id": entity.id,
            "target_type": "entity",
            "relation_type": "related_to",
        })
        assert r.status_code == 200, r.text

    def test_create_writes_audit_and_undo_deletes_link(self, client, db, monkeypatch):
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )
        doc = _make_document(db)
        entity = _make_entity(db)

        r = client.post("/api/library/links", json={
            "source_id": doc.id,
            "source_type": "document",
            "target_id": entity.id,
            "target_type": "entity",
            "relation_type": "related_to",
        })

        assert r.status_code == 200, r.text
        link_id = r.json()["id"]
        audit = db.all(ActionAudit)[-1]
        assert audit.action_name == "library-link.create"
        assert audit.after == {"link_id": link_id}
        assert calls[-1][1]["type"] == "library.link.created"

        inverse = _undo(db, audit.id, str(db.path.parent))

        assert db.get(LibraryItemLink, link_id) is None
        inverse_audit = db.get(ActionAudit, inverse.audit_id)
        assert inverse_audit is not None
        assert inverse_audit.action_name == "library-link.delete"
        assert inverse_audit.inverse_of == audit.id
        assert calls[-1][1]["type"] == "library.link.deleted"


# ---------------------------------------------------------------------------
# GET /api/library/links
# ---------------------------------------------------------------------------


class TestListLibraryLinks:
    def test_lists_links_for_source(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        link = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=entity.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.cites,
        )
        db.save(link)
        r = client.get(f"/api/library/links?source_id={doc.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["id"] == link.id

    def test_filters_by_relation_type(self, client, db):
        doc = _make_document(db)
        e1 = _make_entity(db, canonical_name="one")
        e2 = _make_entity(db, canonical_name="two")
        l1 = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=e1.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.supports,
        )
        l2 = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=e2.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.contradicts,
        )
        db.save(l1)
        db.save(l2)
        r = client.get(f"/api/library/links?source_id={doc.id}&relation_type=contradicts")
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert l2.id in ids
        assert l1.id not in ids

    def test_backfilled_claim_link_appears_in_generic_list(self, client, db):
        doc = _make_document(db)
        first = _make_claim(db, doc, text="First")
        second = _make_claim(db, doc, text="Second")
        db.save(KnowledgeClaimLink(
            id="claim-link-1",
            claim_id=first.id,
            related_claim_id=second.id,
            relation_type=ClaimRelationType.supports,
        ))
        db._backfill_claim_links_to_library_links()

        r = client.get(f"/api/library/links?source_id={first.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["items"][0]["id"] == "claim-link-1"
        assert data["items"][0]["source_type"] == "claim"
        assert data["items"][0]["target_type"] == "claim"


# ---------------------------------------------------------------------------
# GET /api/library/links/{link_id}
# ---------------------------------------------------------------------------


class TestGetLibraryLink:
    def test_get_existing_link(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        link = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=entity.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.related_to,
        )
        db.save(link)
        r = client.get(f"/api/library/links/{link.id}")
        assert r.status_code == 200
        assert r.json()["id"] == link.id

    def test_get_missing_link_returns_404(self, client):
        r = client.get("/api/library/links/missing-link")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/library/links/{link_id}
# ---------------------------------------------------------------------------


class TestUpdateLibraryLink:
    def test_patch_relation_type(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        link = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=entity.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.supports,
        )
        db.save(link)
        r = client.patch(f"/api/library/links/{link.id}", json={"relation_type": "cites"})
        assert r.status_code == 200, r.text
        assert r.json()["relation_type"] == "cites"
        assert r.json()["updated_at"] is not None

    def test_patch_missing_returns_404(self, client):
        r = client.patch("/api/library/links/missing-link", json={"link_quality": 0.9})
        assert r.status_code == 404

    def test_patch_writes_audit_and_undo_restores_previous_values(
        self, client, db, monkeypatch
    ):
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )
        doc = _make_document(db)
        entity = _make_entity(db)
        link = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=entity.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.supports,
            evidence="before",
        )
        db.save(link)

        r = client.patch(
            f"/api/library/links/{link.id}",
            json={"relation_type": "cites", "evidence": "after"},
        )

        assert r.status_code == 200, r.text
        audit = db.all(ActionAudit)[-1]
        assert audit.action_name == "library-link.update"
        assert audit.before["relation_type"] == "supports"
        assert audit.before["evidence"] == "before"
        assert calls[-1][1]["type"] == "library.link.updated"

        inverse = _undo(db, audit.id, str(db.path.parent))

        restored = db.get(LibraryItemLink, link.id)
        assert restored is not None
        assert restored.relation_type == ClaimRelationType.supports
        assert restored.evidence == "before"
        inverse_audit = db.get(ActionAudit, inverse.audit_id)
        assert inverse_audit is not None
        assert inverse_audit.action_name == "library-link.restore"
        assert inverse_audit.inverse_of == audit.id


# ---------------------------------------------------------------------------
# DELETE /api/library/links/{link_id}
# ---------------------------------------------------------------------------


class TestDeleteLibraryLink:
    def test_delete_removes_link(self, client, db):
        doc = _make_document(db)
        note = _make_note(db, doc)
        link = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=note.id,
            target_type=LibraryItemType.note,
            relation_type=ClaimRelationType.cites,
        )
        db.save(link)
        r = client.delete(f"/api/library/links/{link.id}")
        assert r.status_code == 200
        assert r.json()["link_id"] == link.id
        r2 = client.get(f"/api/library/links/{link.id}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/library/links/missing-link")
        assert r.status_code == 404

    def test_delete_writes_audit_and_undo_restores_link(self, client, db, monkeypatch):
        calls: list[tuple] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )
        doc = _make_document(db)
        note = _make_note(db, doc)
        link = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=note.id,
            target_type=LibraryItemType.note,
            relation_type=ClaimRelationType.cites,
        )
        db.save(link)

        r = client.delete(f"/api/library/links/{link.id}")

        assert r.status_code == 200
        audit = db.all(ActionAudit)[-1]
        assert audit.action_name == "library-link.delete"
        assert audit.before["id"] == link.id
        assert calls[-1][1]["type"] == "library.link.deleted"

        inverse = _undo(db, audit.id, str(db.path.parent))

        restored = db.get(LibraryItemLink, link.id)
        assert restored is not None
        assert restored.relation_type == ClaimRelationType.cites
        inverse_audit = db.get(ActionAudit, inverse.audit_id)
        assert inverse_audit is not None
        assert inverse_audit.action_name == "library-link.restore"
        assert inverse_audit.inverse_of == audit.id
        assert calls[-1][1]["type"] == "library.link.updated"


# ---------------------------------------------------------------------------
# GET /api/library-items/{item_id}/links
# ---------------------------------------------------------------------------


class TestListLinksForItem:
    def test_includes_outgoing_and_incoming(self, client, db):
        doc = _make_document(db)
        entity = _make_entity(db)
        claim = _make_claim(db, doc)
        l1 = LibraryItemLink(
            source_id=doc.id,
            source_type=LibraryItemType.document,
            target_id=entity.id,
            target_type=LibraryItemType.entity,
            relation_type=ClaimRelationType.related_to,
        )
        l2 = LibraryItemLink(
            source_id=claim.id,
            source_type=LibraryItemType.claim,
            target_id=doc.id,
            target_type=LibraryItemType.document,
            relation_type=ClaimRelationType.cites,
        )
        db.save(l1)
        db.save(l2)
        r = client.get(f"/api/library-items/{doc.id}/links")
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()["items"]}
        assert l1.id in ids
        assert l2.id in ids
        assert r.json()["count"] == 2


# ---------------------------------------------------------------------------
# Read authz — library-path header enforcement (#2590)
# ---------------------------------------------------------------------------


class TestReadLibraryLinksRequireLibraryPath:
    """The three read endpoints must require the X-Fichero-Library-Path header."""

    def test_list_links_requires_library_path(self, client):
        r = client.get("/api/library/links", headers={"X-Fichero-Library-Path": ""})
        assert r.status_code == 400
        assert "library" in r.json()["detail"].lower()

    def test_get_link_requires_library_path(self, client):
        r = client.get("/api/library/links/some-link-id", headers={"X-Fichero-Library-Path": ""})
        assert r.status_code == 400
        assert "library" in r.json()["detail"].lower()

    def test_list_links_for_item_requires_library_path(self, client):
        r = client.get(
            "/api/library-items/some-item-id/links",
            headers={"X-Fichero-Library-Path": ""},
        )
        assert r.status_code == 400
        assert "library" in r.json()["detail"].lower()
