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
