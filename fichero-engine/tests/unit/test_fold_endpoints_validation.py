"""Validation / boundary tests for node-model fold endpoints.

Scope:
- bookmarks: ``/api/bookmarks`` and ``/api/bookmarks/{id}/resolve``
- saved searches: ``/api/search/saved``
- notes: ``/api/notes``
- milestones: ``POST /api/actions/invoke`` with ``name="milestone.create"``

Goal: malformed input must fail cleanly with a 4xx, not a 500 or a silent
success. Where the current implementation still accepts bad payloads, mark the
test strict xfail so it flips when fixed.
"""

from __future__ import annotations

import pytest

from fichero.knowledge_models import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero.models import DocType, Document, SavedSearch


def test_bookmark_create_rejects_missing_required_target_id(client):
    response = client.post("/api/bookmarks", json={"name": "Missing target"})
    assert response.status_code == 422


def test_bookmark_create_rejects_missing_parent_id_cleanly(client, db):
    target = Document(id="bookmark-target", name="Target", doc_type=DocType.file)
    db.save(target)

    response = client.post(
        "/api/bookmarks",
        json={"target_id": target.id, "parent_id": "missing-parent"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Bookmark parent not found"


@pytest.mark.xfail(
    reason="BookmarkCreate silently ignores unexpected fields instead of rejecting them (#2430 class)",
    strict=True,
)
def test_bookmark_create_rejects_unexpected_fields(client, db):
    target = Document(id="bookmark-target-extra", name="Target", doc_type=DocType.file)
    db.save(target)

    response = client.post(
        "/api/bookmarks",
        json={
            "target_id": target.id,
            "name": "Bookmark",
            "unexpected_field": "should be rejected",
        },
    )

    assert 400 <= response.status_code < 500


def test_bookmark_resolve_missing_id_returns_404(client):
    response = client.get("/api/bookmarks/ghost-bookmark/resolve")
    assert response.status_code == 404
    assert response.json()["detail"] == "Bookmark not found"


def test_saved_search_create_rejects_missing_query(client):
    response = client.post("/api/search/saved", json={"folder_path": "/"})
    assert response.status_code == 422


def test_saved_search_create_rejects_wrong_query_type(client):
    response = client.post("/api/search/saved", json={"query": {"bad": "type"}})
    assert response.status_code == 422


@pytest.mark.xfail(
    reason="SavedSearchCreate currently accepts empty query strings instead of rejecting them",
    strict=True,
)
def test_saved_search_create_rejects_empty_query(client):
    response = client.post("/api/search/saved", json={"query": ""})
    assert 400 <= response.status_code < 500


@pytest.mark.xfail(
    reason="SavedSearchCreate silently ignores unexpected fields instead of rejecting them (#2430 class)",
    strict=True,
)
def test_saved_search_create_rejects_unexpected_fields(client):
    response = client.post(
        "/api/search/saved",
        json={"query": "asprilla", "unexpected_field": "should be rejected"},
    )
    assert 400 <= response.status_code < 500


def test_saved_search_update_missing_id_returns_404(client):
    response = client.put("/api/search/saved/missing-search", json={"query": "updated"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Saved search not found"


def test_saved_search_reorder_missing_member_returns_404(client, db):
    saved = SavedSearch(query="real query")
    db.save(saved)

    response = client.post(
        "/api/search/saved/reorder",
        params={"folder_path": "/"},
        json=[saved.id, "ghost-search"],
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Saved search not found: ghost-search"


def test_note_create_rejects_wrong_tags_type(client):
    response = client.post(
        "/api/notes",
        json={"title": "Bad note", "tags": "not-a-list"},
    )
    assert response.status_code == 422


def test_note_create_rejects_bad_scope_combination(client, db):
    page = Document(id="page-note-validation", name="Page", doc_type=DocType.page)
    folder = Document(id="folder-note-validation", name="Folder", doc_type=DocType.folder)
    db.save(page)
    db.save(folder)

    response = client.post(
        "/api/notes",
        json={
            "title": "Bad scope",
            "page_id": page.id,
            "folder_id": folder.id,
        },
    )

    assert response.status_code == 400
    assert "either a page or a folder, not both" in response.json()["detail"]


def test_note_create_rejects_missing_page_id_cleanly(client):
    response = client.post(
        "/api/notes",
        json={"title": "Missing page", "page_id": "ghost-page"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Page not found: ghost-page"


@pytest.mark.xfail(
    reason="NoteCreateRequest silently ignores unexpected fields instead of rejecting them (#2430 class)",
    strict=True,
)
def test_note_create_rejects_unexpected_fields(client):
    response = client.post(
        "/api/notes",
        json={"title": "Extra", "unexpected_field": "should be rejected"},
    )
    assert 400 <= response.status_code < 500


def test_note_patch_missing_id_returns_404(client):
    response = client.patch("/api/notes/ghost-note", json={"title": "After"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Note not found: ghost-note"


def test_milestone_create_rejects_missing_required_title(client):
    response = client.post(
        "/api/actions/invoke",
        json={
            "name": "milestone.create",
            "params": {"parent_id": "folder-1"},
        },
    )
    assert response.status_code == 422


def test_milestone_create_rejects_missing_parent_cleanly(client):
    response = client.post(
        "/api/actions/invoke",
        json={
            "name": "milestone.create",
            "params": {"title": "Phase 1", "parent_id": "missing-parent"},
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Milestone parent not found"


def test_milestone_create_rejects_non_folder_parent(client, db):
    bad_parent = Document(id="milestone-file-parent", name="File Parent", doc_type=DocType.file)
    db.save(bad_parent)

    response = client.post(
        "/api/actions/invoke",
        json={
            "name": "milestone.create",
            "params": {"title": "Phase 2", "parent_id": bad_parent.id},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Milestone parent must be a folder"


@pytest.mark.xfail(
    reason="Milestone action params currently allow extra fields and silently drop them",
    strict=True,
)
def test_milestone_create_rejects_unexpected_fields(client, db):
    parent = Document(id="milestone-folder-parent", name="Folder Parent", doc_type=DocType.folder)
    db.save(parent)

    response = client.post(
        "/api/actions/invoke",
        json={
            "name": "milestone.create",
            "params": {
                "title": "Phase 3",
                "parent_id": parent.id,
                "unexpected_field": "should be rejected",
            },
        },
    )

    assert 400 <= response.status_code < 500


def test_claim_create_rejects_missing_required_text(client):
    response = client.post("/api/claims", json={})
    assert response.status_code == 422


@pytest.mark.xfail(
    reason="ClaimCreateRequest currently accepts empty text and persists a blank claim",
    strict=True,
)
def test_claim_create_rejects_empty_text(client):
    response = client.post("/api/claims", json={"text": ""})
    assert 400 <= response.status_code < 500


def test_claim_create_rejects_missing_source_document_cleanly(client):
    response = client.post(
        "/api/claims",
        json={"text": "Claim", "source_document_id": "ghost-document"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Source document not found: ghost-document"


@pytest.mark.xfail(
    reason="ClaimCreateRequest silently ignores unexpected fields instead of rejecting them (#2430 class)",
    strict=True,
)
def test_claim_create_rejects_unexpected_fields(client):
    response = client.post(
        "/api/claims",
        json={"text": "Claim", "unexpected_field": "should be rejected"},
    )
    assert 400 <= response.status_code < 500


def test_claim_patch_rejects_missing_related_entity_cleanly(client, db):
    claim = KnowledgeClaim(text="Original claim")
    db.save(claim)

    response = client.patch(
        f"/api/claims/{claim.id}",
        json={"subject_entity_id": "ghost-entity"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown entity for subject_entity_id: ghost-entity"


@pytest.mark.xfail(
    reason="ClaimPatchRequest silently ignores unexpected fields instead of rejecting them (#2430 class)",
    strict=True,
)
def test_claim_patch_rejects_unexpected_fields(client, db):
    claim = KnowledgeClaim(text="Original claim")
    db.save(claim)

    response = client.patch(
        f"/api/claims/{claim.id}",
        json={"unexpected_field": "should be rejected"},
    )

    assert 400 <= response.status_code < 500


def test_entity_create_rejects_missing_required_canonical_name(client):
    response = client.post("/api/entities", json={})
    assert response.status_code == 422


def test_entity_create_rejects_empty_canonical_name(client):
    response = client.post("/api/entities", json={"canonical_name": ""})
    assert response.status_code == 422


def test_entity_create_rejects_missing_explicit_target_id_cleanly(client):
    response = client.post(
        "/api/entities",
        json={"id": "ghost-entity", "canonical_name": "Alice"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "entity 'ghost-entity' not found"


@pytest.mark.xfail(
    reason="EntityUpsertRequest silently ignores unexpected fields instead of rejecting them (#2430 class)",
    strict=True,
)
def test_entity_create_rejects_unexpected_fields(client):
    response = client.post(
        "/api/entities",
        json={"canonical_name": "Alice", "unexpected_field": "should be rejected"},
    )
    assert 400 <= response.status_code < 500


def test_entity_patch_missing_id_returns_404(client):
    response = client.patch("/api/entities/ghost-entity", json={"description": "After"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Entity not found: ghost-entity"


@pytest.mark.xfail(
    reason="EntityPatchRequest silently ignores unexpected fields instead of rejecting them (#2430 class)",
    strict=True,
)
def test_entity_patch_rejects_unexpected_fields(client, db):
    entity = KnowledgeEntity(
        canonical_name="Alice",
        entity_type=EntityType.person,
    )
    db.save(entity)

    response = client.patch(
        f"/api/entities/{entity.id}",
        json={"unexpected_field": "should be rejected"},
    )

    assert 400 <= response.status_code < 500


def test_document_create_rejects_missing_required_name(client):
    response = client.post("/api/documents", json={})
    assert response.status_code == 422


@pytest.mark.xfail(
    reason="DocumentCreate currently accepts empty names instead of rejecting them",
    strict=True,
)
def test_document_create_rejects_empty_name(client):
    response = client.post("/api/documents", json={"name": ""})
    assert 400 <= response.status_code < 500


def test_document_create_rejects_missing_parent_cleanly(client):
    response = client.post(
        "/api/documents",
        json={"name": "Doc", "parent_id": "ghost-parent"},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Parent not found: ghost-parent"


@pytest.mark.xfail(
    reason="DocumentCreate uses extra='allow' and accepts unexpected fields instead of rejecting them (#2430 class)",
    strict=True,
)
def test_document_create_rejects_unexpected_fields(client):
    response = client.post(
        "/api/documents",
        json={"name": "Doc", "unexpected_field": "should be rejected"},
    )
    assert 400 <= response.status_code < 500


def test_document_move_rejects_missing_document_id_cleanly(client):
    response = client.put("/api/documents/ghost-document/move?parent_id=ghost-parent")
    assert response.status_code == 404
    assert response.json()["detail"] == "Document not found: ghost-document"


def test_document_move_rejects_missing_parent_cleanly(client, db):
    doc = Document(id="document-move-target", name="Target", doc_type=DocType.file)
    db.save(doc)

    response = client.put(f"/api/documents/{doc.id}/move?parent_id=ghost-parent")

    assert response.status_code == 400
    assert response.json()["detail"] == "Parent not found: ghost-parent"


@pytest.mark.xfail(
    reason="Document move route ignores unexpected query params instead of rejecting them (#2430 class)",
    strict=True,
)
def test_document_move_rejects_unexpected_query_fields(client, db):
    doc = Document(id="document-move-extra", name="Target", doc_type=DocType.file)
    db.save(doc)

    response = client.put(
        f"/api/documents/{doc.id}/move?parent_id=&unexpected_field=should-be-rejected"
    )

    assert 400 <= response.status_code < 500


def test_room_create_rejects_missing_required_name(client):
    response = client.post("/api/mind-palace/rooms", json={})
    assert response.status_code == 422


@pytest.mark.xfail(
    reason="RoomCreateRequest currently accepts empty names and creates blank rooms",
    strict=True,
)
def test_room_create_rejects_empty_name(client):
    response = client.post("/api/mind-palace/rooms", json={"name": ""})
    assert 400 <= response.status_code < 500


@pytest.mark.xfail(
    reason="RoomCreateRequest silently ignores unexpected fields instead of rejecting them (#2430 class)",
    strict=True,
)
def test_room_create_rejects_unexpected_fields(client):
    response = client.post(
        "/api/mind-palace/rooms",
        json={"name": "Room", "unexpected_field": "should be rejected"},
    )
    assert 400 <= response.status_code < 500


def test_room_update_missing_id_returns_404(client):
    response = client.patch(
        "/api/mind-palace/rooms/ghost-room",
        json={"name": "After"},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Room not found: ghost-room"


@pytest.mark.xfail(
    reason="RoomUpdateRequest silently ignores unexpected fields instead of rejecting them (#2430 class)",
    strict=True,
)
def test_room_update_rejects_unexpected_fields(client, db):
    room = Document(
        id="room-update-extra",
        name="Room",
        node_kind="room",
        prototype_key="room",
        doc_type=DocType.folder,
        attributes={"description": "", "room_type": "research", "owner_id": "user", "metadata": {}},
    )
    db.save(room)

    response = client.patch(
        "/api/mind-palace/rooms/room-update-extra",
        json={"unexpected_field": "should be rejected"},
    )

    assert 400 <= response.status_code < 500
