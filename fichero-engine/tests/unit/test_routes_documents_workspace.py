from __future__ import annotations

from fichero.models import DocType, Document


def test_workspace_patch_add_remove_reorder_items(client, db):
    workspace = Document(id="ws-1", name="Workspace", doc_type=DocType.folder, is_workspace=True)
    db.save(workspace)

    add_first = client.patch(
        f"/api/documents/{workspace.id}/workspace",
        json={
            "add": [
                {"id": "item-a", "target_type": "document", "target_id": "doc-a", "role": "source"},
                {"id": "item-b", "target_type": "document", "target_id": "doc-b", "role": "source"},
            ]
        },
    )
    assert add_first.status_code == 200
    assert [item["id"] for item in add_first.json()["items"]] == ["item-a", "item-b"]

    mutate = client.patch(
        f"/api/documents/{workspace.id}/workspace",
        json={
            "remove_ids": ["item-a"],
            "add": [{"id": "item-c", "target_type": "document", "target_id": "doc-c"}],
            "reorder_ids": ["item-c", "item-b"],
        },
    )
    assert mutate.status_code == 200
    payload = mutate.json()
    assert payload["count"] == 2
    assert [item["id"] for item in payload["items"]] == ["item-c", "item-b"]


def test_workspace_items_resolve_document_alias_targets(client, db):
    workspace = Document(
        id="ws-2",
        name="Workspace 2",
        doc_type=DocType.folder,
        is_workspace=True,
        curated_items=[
            {"id": "item-doc", "target_type": "document", "target_id": "doc-1", "role": "source"}
        ],
    )
    target_doc = Document(id="doc-1", name="Source Doc", doc_type=DocType.file)
    db.save(workspace)
    db.save(target_doc)

    response = client.get(f"/api/documents/{workspace.id}/workspace/items")
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    item = payload["items"][0]
    assert item["id"] == "item-doc"
    assert item["target"]["id"] == "doc-1"
    assert item["target"]["name"] == "Source Doc"
