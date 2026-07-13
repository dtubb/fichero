from __future__ import annotations

from fichero.models import Conversation, DocType, Document


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


def test_list_workspaces_returns_only_workspace_docs(client, db):
    """GET /api/documents/workspaces lists is_workspace docs and ignores the
    literal path being mistaken for a document id (#1617)."""
    ws_a = Document(id="ws-a", name="Workspace A", doc_type=DocType.folder, is_workspace=True)
    ws_b = Document(id="ws-b", name="Workspace B", doc_type=DocType.folder, is_workspace=True)
    plain = Document(id="folder-x", name="Plain Folder", doc_type=DocType.folder)
    db.save(ws_a)
    db.save(ws_b)
    db.save(plain)

    response = client.get("/api/documents/workspaces")
    assert response.status_code == 200
    payload = response.json()
    ids = {item["id"] for item in payload["items"]}
    assert ids == {"ws-a", "ws-b"}
    assert payload["count"] == 2


def test_document_and_agent_workspaces_have_distinct_endpoints(client, db):
    document_workspace = Document(
        id="document-workspace",
        name="Document workspace",
        doc_type=DocType.folder,
        is_workspace=True,
    )
    conversation = Conversation(
        id="agent-workspace-conversation",
        title="Agent workspace",
        messages=[{"role": "user", "content": "Investigate this."}],
    )
    db.save(document_workspace)
    db.save(conversation)

    saved_agent_workspace = client.post(
        f"/api/chat/conversations/{conversation.id}/workspace", json={}
    )
    assert saved_agent_workspace.status_code == 200
    agent_workspace_id = saved_agent_workspace.json()["id"]

    document_response = client.get("/api/documents/workspaces")
    agent_response = client.get("/api/chat/workspaces")

    assert document_response.status_code == 200
    assert [item["id"] for item in document_response.json()["items"]] == [
        document_workspace.id
    ]
    assert agent_response.status_code == 200
    assert [item["id"] for item in agent_response.json()["items"]] == [agent_workspace_id]
