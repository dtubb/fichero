"""Phase 1 node-class dimension + workspace-item node_class (#1570).

Workspace-items only. Proves the Tinderbox-style prototype/class axis rides
on the existing generic classification registry and that a curated item
round-trips its ``node_class`` through patch -> get, while old items without
the field still load (backward compatible).
"""

from __future__ import annotations

from fichero_server.models import DocType, Document


def test_node_class_value_create_and_list(client):
    """A node_class ClassificationValue is created + listed via the generic route."""
    created = client.post(
        "/api/classifications",
        json={
            "dimension": "node_class",
            "key": "chapter",
            "label": "Chapter",
            "color": "#0A84FF",
        },
    )
    # 201/200 on create, or 409 if the built-in seed already claimed the key.
    assert created.status_code in (200, 201, 409)

    listed = client.get("/api/classifications", params={"dimension": "node_class"})
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert items, "expected at least one node_class value"
    assert all(v["dimension"] == "node_class" for v in items)
    assert any(v["key"] == "chapter" for v in items)


def test_node_class_custom_value_roundtrips(client):
    """A user-defined node_class value persists and is retrievable."""
    created = client.post(
        "/api/classifications",
        json={
            "dimension": "node_class",
            "key": "fieldnote",
            "label": "Field Note",
            "color": "#FF2D55",
        },
    )
    assert created.status_code in (200, 201)
    body = created.json()
    assert body["dimension"] == "node_class"
    assert body["key"] == "fieldnote"
    assert body["is_builtin"] is False

    listed = client.get("/api/classifications", params={"dimension": "node_class"})
    keys = {v["key"] for v in listed.json()["items"]}
    assert "fieldnote" in keys


def test_workspace_item_node_class_roundtrips(client, db):
    """A curated item persists + returns its node_class through patch -> get."""
    workspace = Document(
        id="ws-nc-1", name="Workspace", doc_type=DocType.folder, is_workspace=True
    )
    db.save(workspace)

    patched = client.patch(
        f"/api/documents/{workspace.id}/workspace",
        json={
            "add": [
                {
                    "id": "item-a",
                    "target_type": "document",
                    "target_id": "doc-a",
                    "role": "source",
                    "node_class": "chapter",
                }
            ]
        },
    )
    assert patched.status_code == 200
    assert patched.json()["items"][0]["node_class"] == "chapter"

    fetched = client.get(f"/api/documents/{workspace.id}/workspace/items")
    assert fetched.status_code == 200
    item = fetched.json()["items"][0]
    assert item["id"] == "item-a"
    assert item["node_class"] == "chapter"


def test_workspace_item_without_node_class_still_loads(client, db):
    """Old curated items lacking node_class load (backward compatible)."""
    workspace = Document(
        id="ws-nc-2",
        name="Legacy Workspace",
        doc_type=DocType.folder,
        is_workspace=True,
        curated_items=[
            # Persisted before node_class existed — no such key.
            {"id": "legacy", "target_type": "document", "target_id": "doc-1"}
        ],
    )
    db.save(workspace)

    fetched = client.get(f"/api/documents/{workspace.id}/workspace/items")
    assert fetched.status_code == 200
    item = fetched.json()["items"][0]
    assert item["id"] == "legacy"
    assert item["node_class"] is None
