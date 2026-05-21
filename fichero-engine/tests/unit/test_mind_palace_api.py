"""Unit tests for Mind Palace API routes."""

import pytest


def test_room_crud(client, db):
    """Create, read, update, delete rooms."""
    # Create
    resp = client.post(
        "/api/mind-palace/rooms",
        json={
            "name": "Gold Mining Research",
            "description": "Research on Colombian gold mining operations",
            "room_type": "research",
        },
    )
    assert resp.status_code == 200
    room = resp.json()
    assert room["name"] == "Gold Mining Research"
    assert room["room_type"] == "research"

    # List
    list_resp = client.get("/api/mind-palace/rooms")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Get
    get_resp = client.get(f"/api/mind-palace/rooms/{room['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == room["id"]

    # Update
    patch_resp = client.patch(
        f"/api/mind-palace/rooms/{room['id']}",
        json={"description": "Updated description."},
    )
    assert patch_resp.status_code == 200
    assert "Updated description" in patch_resp.json()["description"]

    # Delete
    del_resp = client.delete(f"/api/mind-palace/rooms/{room['id']}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deleted"

    # Verify deleted
    get_after = client.get(f"/api/mind-palace/rooms/{room['id']}")
    assert get_after.status_code == 404


def test_room_not_found(client):
    """404 for missing room."""
    resp = client.get("/api/mind-palace/rooms/nonexistent-id")
    assert resp.status_code == 404


def test_node_crud(client, db):
    """Place, move, and remove nodes in a room."""
    # Create room
    room_resp = client.post(
        "/api/mind-palace/rooms",
        json={"name": "Synthesis Room", "room_type": "synthesis"},
    )
    room = room_resp.json()

    # Place node
    node_resp = client.post(
        "/api/mind-palace/nodes",
        json={
            "room_id": room["id"],
            "node_type": "claim",
            "source_id": "claim-123",
            "label": "Central thesis",
            "position_x": 1.0,
            "position_y": 2.0,
            "position_z": 0.5,
        },
    )
    assert node_resp.status_code == 200
    node = node_resp.json()
    assert node["node_type"] == "claim"
    assert node["position_x"] == 1.0
    assert node["position_y"] == 2.0

    # List nodes
    list_resp = client.get(f"/api/mind-palace/nodes?room_id={room['id']}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Move node
    move_resp = client.patch(
        f"/api/mind-palace/nodes/{node['id']}",
        json={"position_x": 5.0, "position_y": 6.0, "position_z": 1.0},
    )
    assert move_resp.status_code == 200
    assert move_resp.json()["position_x"] == 5.0

    # Remove node
    del_resp = client.delete(f"/api/mind-palace/nodes/{node['id']}")
    assert del_resp.status_code == 200

    # Verify removed
    get_resp = client.get(f"/api/mind-palace/nodes/{node['id']}")
    assert get_resp.status_code == 404


def test_node_requires_room(client):
    """Node placement requires existing room."""
    resp = client.post(
        "/api/mind-palace/nodes",
        json={
            "room_id": "nonexistent-room",
            "node_type": "source",
            "source_id": "doc-1",
        },
    )
    assert resp.status_code == 404
    assert "Room not found" in resp.json()["detail"]


def test_connection_crud(client, db):
    """Create and delete connections between nodes."""
    # Create room and two nodes
    room_resp = client.post(
        "/api/mind-palace/rooms",
        json={"name": "Connection Test Room"},
    )
    room = room_resp.json()

    node1_resp = client.post(
        "/api/mind-palace/nodes",
        json={"room_id": room["id"], "node_type": "claim", "source_id": "claim-1"},
    )
    node1 = node1_resp.json()

    node2_resp = client.post(
        "/api/mind-palace/nodes",
        json={"room_id": room["id"], "node_type": "source", "source_id": "doc-1"},
    )
    node2 = node2_resp.json()

    # Create connection
    conn_resp = client.post(
        "/api/mind-palace/connections",
        json={
            "room_id": room["id"],
            "source_node_id": node1["id"],
            "target_node_id": node2["id"],
            "connection_type": "evidentiary",
            "link_subtype": "supports",
        },
    )
    assert conn_resp.status_code == 200
    conn = conn_resp.json()
    assert conn["connection_type"] == "evidentiary"
    assert conn["link_subtype"] == "supports"

    # List connections
    list_resp = client.get(f"/api/mind-palace/connections?room_id={room['id']}")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

    # Delete connection
    del_resp = client.delete(f"/api/mind-palace/connections/{conn['id']}")
    assert del_resp.status_code == 200


def test_stack_crud(client, db):
    """Create stacks and add/remove nodes."""
    # Create room and node
    room_resp = client.post(
        "/api/mind-palace/rooms",
        json={"name": "Stack Test Room"},
    )
    room = room_resp.json()

    node_resp = client.post(
        "/api/mind-palace/nodes",
        json={"room_id": room["id"], "node_type": "note", "source_id": "note-1"},
    )
    node = node_resp.json()

    # Create stack
    stack_resp = client.post(
        "/api/mind-palace/stacks",
        json={
            "room_id": room["id"],
            "name": "Key Evidence Stack",
            "node_ids": [],
        },
    )
    assert stack_resp.status_code == 200
    stack = stack_resp.json()
    assert stack["name"] == "Key Evidence Stack"

    # Add node to stack
    add_resp = client.post(
        f"/api/mind-palace/stacks/{stack['id']}/nodes/{node['id']}"
    )
    assert add_resp.status_code == 200
    assert node["id"] in add_resp.json()["node_ids"]

    # Remove node from stack
    remove_resp = client.delete(
        f"/api/mind-palace/stacks/{stack['id']}/nodes/{node['id']}"
    )
    assert remove_resp.status_code == 200
    assert node["id"] not in remove_resp.json()["node_ids"]


@pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
def test_note_crud(client, db):
    """Create, update, and delete notes."""
    # Create note
    resp = client.post(
        "/api/mind-palace/notes",
        json={
            "content": "This claim supports the central thesis about mining practices.",
            "note_type": "ai_workspace",
            "author_id": "ai",
            "linked_claim_ids": ["claim-1"],
        },
    )
    assert resp.status_code == 200
    note = resp.json()
    assert note["content"].startswith("This claim")
    assert note["note_type"] == "ai_workspace"
    assert note["author_id"] == "ai"

    # List notes
    list_resp = client.get("/api/mind-palace/notes")
    assert list_resp.status_code == 200

    # Filter by note_type
    filter_resp = client.get("/api/mind-palace/notes?note_type=ai_workspace")
    assert filter_resp.status_code == 200
    assert all(n["note_type"] == "ai_workspace" for n in filter_resp.json())

    # Update note
    patch_resp = client.patch(
        f"/api/mind-palace/notes/{note['id']}",
        json={"content": "Updated content.", "status": "surfaced"},
    )
    assert patch_resp.status_code == 200
    assert "Updated content" in patch_resp.json()["content"]
    assert patch_resp.json()["status"] == "surfaced"

    # Delete note
    del_resp = client.delete(f"/api/mind-palace/notes/{note['id']}")
    assert del_resp.status_code == 200


def test_viewport_get_and_save(client, db):
    """Get and save viewport camera state."""
    # Create room
    room_resp = client.post(
        "/api/mind-palace/rooms",
        json={"name": "Viewport Test Room"},
    )
    room = room_resp.json()

    # Get default viewport (no prior state)
    get_resp = client.get(
        f"/api/mind-palace/rooms/{room['id']}/viewport/user-1"
    )
    assert get_resp.status_code == 200
    viewport = get_resp.json()
    assert viewport["room_id"] == room["id"]
    assert viewport["zoom_level"] == 1.0

    # Save viewport
    save_resp = client.post(
        f"/api/mind-palace/rooms/{room['id']}/viewport/user-1",
        json={
            "camera_x": 10.0,
            "camera_y": 5.0,
            "camera_z": 20.0,
            "zoom_level": 1.5,
            "focus_node_id": None,
        },
    )
    assert save_resp.status_code == 200
    assert save_resp.json()["zoom_level"] == 1.5


def test_focus_node(client, db):
    """Focus on a specific node in a room."""
    # Create room and node
    room_resp = client.post(
        "/api/mind-palace/rooms",
        json={"name": "Focus Test Room"},
    )
    room = room_resp.json()

    node_resp = client.post(
        "/api/mind-palace/nodes",
        json={"room_id": room["id"], "node_type": "claim", "source_id": "focus-test"},
    )
    node = node_resp.json()

    # Focus on node
    focus_resp = client.post(
        f"/api/mind-palace/rooms/{room['id']}/focus",
        params={"node_id": node["id"]},
    )
    assert focus_resp.status_code == 200
    assert focus_resp.json()["focus_node_id"] == node["id"]


def test_scene_summary(client, db):
    """Get scene summary for a room."""
    # Create room
    room_resp = client.post(
        "/api/mind-palace/rooms",
        json={"name": "Scene Summary Test"},
    )
    room = room_resp.json()

    # Add nodes
    client.post(
        "/api/mind-palace/nodes",
        json={"room_id": room["id"], "node_type": "claim", "source_id": "c1"},
    )
    client.post(
        "/api/mind-palace/nodes",
        json={"room_id": room["id"], "node_type": "source", "source_id": "d1"},
    )

    # Get summary
    summary_resp = client.get(f"/api/mind-palace/rooms/{room['id']}/scene")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    assert summary["room_id"] == room["id"]
    assert summary["node_count"] >= 2
    assert "claim" in summary["node_types"]
    assert "source" in summary["node_types"]


@pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
def test_suggest_arrangement(client, db):
    """AI arrangement suggestion returns circular layout."""
    # Create room and nodes
    room_resp = client.post(
        "/api/mind-palace/rooms",
        json={"name": "Arrange Test Room"},
    )
    room = room_resp.json()

    node1_resp = client.post(
        "/api/mind-palace/nodes",
        json={"room_id": room["id"], "node_type": "claim", "source_id": "a1"},
    )
    node1 = node1_resp.json()

    node2_resp = client.post(
        "/api/mind-palace/nodes",
        json={"room_id": room["id"], "node_type": "claim", "source_id": "a2"},
    )
    node2 = node2_resp.json()

    # Get arrangement suggestion
    arrange_resp = client.post(
        f"/api/mind-palace/rooms/{room['id']}/suggest-arrangement",
        json={
            "node_ids": [node1["id"], node2["id"]],
            "arrangement_type": "semantic",
        },
    )
    assert arrange_resp.status_code == 200
    arranged = arrange_resp.json()
    assert len(arranged) == 2
    # Nodes should have different positions (circular layout)
    positions = [(n["position_x"], n["position_y"]) for n in arranged]
    assert positions[0] != positions[1]


def test_capture_placeholder(client, db):
    """Capture returns placeholder when RealityKit not implemented."""
    room_resp = client.post(
        "/api/mind-palace/rooms",
        json={"name": "Capture Test Room"},
    )
    room = room_resp.json()

    cap_resp = client.post(
        f"/api/mind-palace/rooms/{room['id']}/capture",
        json={"region": "full"},
    )
    assert cap_resp.status_code == 200
    assert cap_resp.json()["status"] == "placeholder"


def test_tinderbox_export_placeholder(client, db):
    """Tinderbox export returns placeholder."""
    room_resp = client.post(
        "/api/mind-palace/rooms",
        json={"name": "Tinderbox Test Room"},
    )
    room = room_resp.json()

    exp_resp = client.post(
        f"/api/mind-palace/export/tinderbox",
        params={"room_id": room["id"]},
    )
    assert exp_resp.status_code == 200
    assert exp_resp.json()["status"] == "placeholder"
