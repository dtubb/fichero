"""Tests for mind palace routes.

Mind palace is a 3D spatial workspace for organizing research materials into
rooms, nodes, and connections. Routes live at /api/mind-palace/...
(router has no prefix, mounted at "/api/mind-palace").
"""

import pytest

from fichero.spatial_models import (
    NodeType,
    ConnectionType,
    SpatialRoom,
    SpatialNode,
)
from fichero.models import Document


BASE = "/api/mind-palace"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_room(room_id: str = "room-1", name: str = "Research Room") -> SpatialRoom:
    return SpatialRoom(id=room_id, name=name)


def _make_node(
    node_id: str = "node-1",
    room_id: str = "room-1",
) -> SpatialNode:
    return SpatialNode(
        id=node_id,
        room_id=room_id,
        node_type=NodeType.note,
        label="My Note",
    )


# ---------------------------------------------------------------------------
# POST /api/mind-palace/rooms
# ---------------------------------------------------------------------------


class TestCreateRoom:
    def test_create_room(self, client):
        r = client.post(f"{BASE}/rooms", json={
            "name": "Archive Room",
            "room_type": "research",
            "description": "A room for archive materials.",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Archive Room"
        assert "id" in data

    def test_create_room_creates_backing_room_document(self, client, db):
        response = client.post(
            f"{BASE}/rooms",
            json={"name": "Node Backed Room", "room_type": "research"},
        )
        assert response.status_code == 200

        room_id = response.json()["id"]
        mirrored = db.get(Document, room_id)
        assert mirrored is not None
        assert mirrored.node_kind == "room"
        assert mirrored.prototype_key == "room"
        assert mirrored.doc_type == "folder"


# ---------------------------------------------------------------------------
# GET /api/mind-palace/rooms
# ---------------------------------------------------------------------------


class TestListRooms:
    def test_empty_list(self, client):
        r = client.get(f"{BASE}/rooms")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_returns_rooms(self, client, db):
        db.save(_make_room("r-1", "Room A"))
        db.save(_make_room("r-2", "Room B"))

        r = client.get(f"{BASE}/rooms")
        assert r.status_code == 200
        assert len(r.json()["items"]["items"]) == 2


# ---------------------------------------------------------------------------
# GET /api/mind-palace/rooms/{id}
# ---------------------------------------------------------------------------


class TestGetRoom:
    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_get_existing_room(self, client, db):
        db.save(_make_room("r-get", "My Room"))

        r = client.get(f"{BASE}/rooms/r-get")
        assert r.status_code == 200
        assert r.json()["items"]["name"] == "My Room"

    def test_get_missing_room_returns_404(self, client):
        r = client.get(f"{BASE}/rooms/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/mind-palace/rooms/{id}
# ---------------------------------------------------------------------------


class TestUpdateRoom:
    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_update_room_name(self, client, db):
        db.save(_make_room("r-upd", "Old Name"))

        r = client.patch(f"{BASE}/rooms/r-upd", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["items"]["name"] == "New Name"

    def test_update_missing_room_returns_404(self, client):
        r = client.patch(f"{BASE}/rooms/no-such", json={"name": "X"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/mind-palace/rooms/{id}
# ---------------------------------------------------------------------------


class TestDeleteRoom:
    def test_delete_room(self, client, db):
        db.save(_make_room("r-del", "To Delete"))

        r = client.delete(f"{BASE}/rooms/r-del")
        assert r.status_code == 200

    def test_delete_missing_room_returns_404(self, client):
        r = client.delete(f"{BASE}/rooms/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/mind-palace/nodes
# ---------------------------------------------------------------------------


class TestCreateNode:
    def test_create_node(self, client, db):
        db.save(_make_room("r-node"))

        r = client.post(f"{BASE}/nodes", json={
            "room_id": "r-node",
            "node_type": "note",
            "label": "Important note",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["room_id"] == "r-node"
        assert data["label"] == "Important note"

    def test_create_node_missing_room_returns_404(self, client):
        r = client.post(f"{BASE}/nodes", json={
            "room_id": "no-such-room",
            "node_type": "note",
            "label": "Orphan",
        })
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/mind-palace/nodes
# ---------------------------------------------------------------------------


class TestListNodes:
    def test_empty_list(self, client, db):
        db.save(_make_room("r-empty"))
        r = client.get(f"{BASE}/nodes?room_id=r-empty")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_returns_nodes_for_room(self, client, db):
        db.save(_make_room("r-ln"))
        db.save(_make_node("n-1", "r-ln"))
        db.save(_make_node("n-2", "r-ln"))

        r = client.get(f"{BASE}/nodes?room_id=r-ln")
        assert r.status_code == 200
        assert len(r.json()["items"]["items"]) == 2

    @pytest.mark.xfail(reason="dev-tier feature gated; re-enable tracked in #1151", strict=False)
    def test_filters_by_room(self, client, db):
        db.save(_make_room("r-a"))
        db.save(_make_room("r-b"))
        db.save(_make_node("n-a1", "r-a"))
        db.save(_make_node("n-b1", "r-b"))

        r = client.get(f"{BASE}/nodes?room_id=r-a")
        assert r.status_code == 200
        assert len(r.json()["items"]["items"]) == 1
        assert r.json()["items"]["items"][0]["room_id"] == "r-a"


# ---------------------------------------------------------------------------
# Connections + viewport routes used by Spatial Library
# ---------------------------------------------------------------------------


class TestConnections:
    def test_create_and_list_connections(self, client, db):
        db.save(_make_room("r-conn"))
        db.save(_make_node("n-src", "r-conn"))
        db.save(_make_node("n-dst", "r-conn"))

        create = client.post(
            f"{BASE}/connections",
            json={
                "room_id": "r-conn",
                "source_node_id": "n-src",
                "target_node_id": "n-dst",
                "connection_type": ConnectionType.semantic.value,
            },
        )
        assert create.status_code == 200
        conn_id = create.json()["id"]

        listing = client.get(f"{BASE}/connections?room_id=r-conn")
        assert listing.status_code == 200
        body = listing.json()
        assert body["count"] == 1
        assert body["items"][0]["id"] == conn_id
        assert body["items"][0]["source_node_id"] == "n-src"
        assert body["items"][0]["target_node_id"] == "n-dst"


class TestViewport:
    def test_save_then_get_viewport_roundtrip(self, client, db):
        db.save(_make_room("r-view"))

        save = client.post(
            f"{BASE}/rooms/r-view/viewport/user-1",
            json={
                "camera_x": 3.0,
                "camera_y": 2.0,
                "camera_z": 11.0,
                "zoom_level": 1.25,
                "bookmark_name": "working-shot",
                "metadata": {"mode": "threeD"},
            },
        )
        assert save.status_code == 200
        saved = save.json()
        assert saved["room_id"] == "r-view"
        assert saved["user_id"] == "user-1"
        assert saved["zoom_level"] == 1.25

        get_resp = client.get(f"{BASE}/rooms/r-view/viewport/user-1")
        assert get_resp.status_code == 200
        loaded = get_resp.json()
        assert loaded["camera_x"] == 3.0
        assert loaded["camera_y"] == 2.0
        assert loaded["camera_z"] == 11.0
        assert loaded["bookmark_name"] == "working-shot"
        assert loaded["metadata"]["mode"] == "threeD"

    def test_focus_node_sets_viewport_focus(self, client, db):
        db.save(_make_room("r-focus"))
        db.save(_make_node("n-focus", "r-focus"))

        r = client.post(f"{BASE}/rooms/r-focus/focus?user_id=user-2&node_id=n-focus")
        assert r.status_code == 200
        assert r.json()["focus_node_id"] == "n-focus"
