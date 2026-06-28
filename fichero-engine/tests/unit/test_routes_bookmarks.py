"""Tests for bookmark node routes (node-model fold F4, #2591)."""

from __future__ import annotations

from fichero.models import DocType, Document
from fichero.node_aliases import ALIAS_NODE_KIND


def test_create_bookmark_creates_alias_document(client, db):
    target = Document(id="target-1", name="Target", doc_type=DocType.file)
    db.save(target)

    response = client.post(
        "/api/bookmarks",
        json={"target_id": target.id, "name": "Pinned Target"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["node_kind"] == ALIAS_NODE_KIND
    assert payload["prototype_key"] == "bookmark"
    assert payload["alias_target_id"] == target.id
    assert payload["name"] == "Pinned Target"


def test_list_bookmarks_returns_only_bookmark_nodes(client, db):
    target = Document(id="target-2", name="Real Doc", doc_type=DocType.file)
    bookmark = Document(
        id="bookmark-1",
        name="Bookmark",
        doc_type=DocType.file,
        node_kind=ALIAS_NODE_KIND,
        prototype_key="bookmark",
        alias_target_id=target.id,
        sort_order=2,
    )
    plain_alias = Document(
        id="alias-1",
        name="Alias But Not Bookmark",
        doc_type=DocType.file,
        node_kind=ALIAS_NODE_KIND,
        alias_target_id=target.id,
        sort_order=0,
    )
    plain_doc = Document(id="doc-plain", name="Plain Doc", doc_type=DocType.file)
    db.save(target)
    db.save(bookmark)
    db.save(plain_alias)
    db.save(plain_doc)

    response = client.get("/api/bookmarks")

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert [item["id"] for item in payload["items"]] == ["bookmark-1"]


def test_resolve_bookmark_returns_live_target(client, db):
    target = Document(id="target-3", name="Target 3", doc_type=DocType.folder)
    bookmark = Document(
        id="bookmark-2",
        name="Bookmark 2",
        doc_type=DocType.folder,
        node_kind=ALIAS_NODE_KIND,
        prototype_key="bookmark",
        alias_target_id=target.id,
    )
    db.save(target)
    db.save(bookmark)

    response = client.get(f"/api/bookmarks/{bookmark.id}/resolve")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == target.id
    assert payload["name"] == "Target 3"


def test_resolve_dangling_bookmark_raises_404(client, db):
    target = Document(id="target-4", name="Target 4", doc_type=DocType.file)
    bookmark = Document(
        id="bookmark-3",
        name="Bookmark 3",
        doc_type=DocType.file,
        node_kind=ALIAS_NODE_KIND,
        prototype_key="bookmark",
        alias_target_id=target.id,
    )
    db.save(target)
    db.save(bookmark)
    db.delete(target)

    response = client.get(f"/api/bookmarks/{bookmark.id}/resolve")

    assert response.status_code == 404
    assert response.json()["detail"] == f"Alias {bookmark.id} references missing node {target.id}"


def test_bookmark_full_route_cycle_create_list_resolve_delete(client, db):
    folder = Document(id="bookmark-folder", name="Bookmarks", doc_type=DocType.folder)
    target = Document(id="target-cycle", name="Cycle Target", doc_type=DocType.file)
    db.save(folder)
    db.save(target)

    created = client.post(
        "/api/bookmarks",
        json={
            "target_id": target.id,
            "parent_id": folder.id,
            "name": "Pinned Cycle Target",
        },
    )

    assert created.status_code == 201
    bookmark_id = created.json()["id"]
    assert created.json()["prototype_key"] == "bookmark"
    assert created.json()["alias_target_id"] == target.id
    assert created.json()["parent_id"] == folder.id

    listing = client.get(f"/api/bookmarks?parent_id={folder.id}")
    assert listing.status_code == 200
    assert listing.json()["count"] == 1
    assert listing.json()["items"][0]["id"] == bookmark_id

    resolved = client.get(f"/api/bookmarks/{bookmark_id}/resolve")
    assert resolved.status_code == 200
    assert resolved.json()["id"] == target.id
    assert resolved.json()["name"] == "Cycle Target"

    deleted = client.delete(f"/api/documents/{bookmark_id}")
    assert deleted.status_code == 204
    assert db.get(Document, bookmark_id).deleted_at is not None

    purged = client.delete(f"/api/documents/{bookmark_id}/purge")
    assert purged.status_code == 204

    after_delete = client.get(f"/api/bookmarks?parent_id={folder.id}")
    assert after_delete.status_code == 200
    assert after_delete.json()["count"] == 0

    resolve_deleted = client.get(f"/api/bookmarks/{bookmark_id}/resolve")
    assert resolve_deleted.status_code == 404
    assert resolve_deleted.json()["detail"] == "Bookmark not found"


def test_create_bookmark_missing_target_returns_404(client):
    response = client.post(
        "/api/bookmarks",
        json={"target_id": "missing-target", "name": "Broken Bookmark"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Bookmark target not found"
