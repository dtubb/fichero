"""Tests for mind palace routes.

Mind palace is a 3D spatial workspace for organizing research materials into
rooms, nodes, and connections. Routes live at /api/mind-palace/...
(router has no prefix, mounted at "/api/mind-palace").
"""

import pytest

from fichero.spatial_models import (
    NodeType,
    ConnectionType,
    RoomType,
    SpatialRoom,
    SpatialNode,
)
from fichero.models import ActionAudit, Document


BASE = "/api/mind-palace"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_room(room_id: str = "room-1", name: str = "Research Room") -> SpatialRoom:
    return SpatialRoom(id=room_id, name=name)


def _legacy_room(db, room_id: str) -> SpatialRoom | None:
    for room in db._legacy_all_spatial_room_rows():
        if room.id == room_id:
            return room
    return None


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
        legacy = _legacy_room(db, room_id)
        assert legacy is not None
        assert legacy.name == "Node Backed Room"
        assert legacy.room_type == RoomType.research

    def test_create_room_dual_writes_empty_payload_defaults(self, client, db):
        response = client.post(f"{BASE}/rooms", json={"name": "Sparse Room"})

        assert response.status_code == 200
        room_id = response.json()["id"]
        assert response.json()["description"] == ""
        assert response.json()["room_type"] == "research"
        assert response.json()["owner_id"] == "user"
        assert response.json()["metadata"] == {}

        mirrored = db.get(Document, room_id)
        legacy = _legacy_room(db, room_id)
        assert mirrored is not None
        assert mirrored.attributes["description"] == ""
        assert mirrored.attributes["room_type"] == "research"
        assert mirrored.attributes["owner_id"] == "user"
        assert mirrored.attributes["metadata"] == {}
        assert legacy is not None
        assert legacy.description == ""
        assert legacy.room_type == RoomType.research
        assert legacy.owner_id == "user"
        assert legacy.metadata == {}


# ---------------------------------------------------------------------------
# GET /api/mind-palace/rooms
# ---------------------------------------------------------------------------


class TestListRooms:
    def test_empty_list(self, client):
        r = client.get(f"{BASE}/rooms")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_returns_document_backed_rooms_with_filters(self, client, db):
        db.save(
            Document(
                id="room-doc-a",
                name="Room A",
                node_kind="room",
                prototype_key="room",
                doc_type="folder",
                attributes={
                    "description": "First room",
                    "room_type": "research",
                    "owner_id": "user",
                    "metadata": {},
                },
            )
        )
        db.save(
            Document(
                id="room-doc-b",
                name="Room B",
                node_kind="room",
                prototype_key="room",
                doc_type="folder",
                attributes={
                    "description": "Second room",
                    "room_type": "presentation",
                    "owner_id": "human",
                    "metadata": {"theme": "gold"},
                },
            )
        )

        listing = client.get(f"{BASE}/rooms")
        assert listing.status_code == 200
        assert listing.json()["count"] == 2
        assert {item["id"] for item in listing.json()["items"]} == {"room-doc-a", "room-doc-b"}

        filtered = client.get(f"{BASE}/rooms?room_type=presentation&owner_id=human")
        assert filtered.status_code == 200
        assert filtered.json()["count"] == 1
        assert filtered.json()["items"][0]["id"] == "room-doc-b"

    def test_list_room_shape_matches_get_shape(self, client):
        created = client.post(
            f"{BASE}/rooms",
            json={"name": "Parity Room", "room_type": "research", "description": "shape"},
        )
        assert created.status_code == 200

        room_id = created.json()["id"]
        listed = client.get(f"{BASE}/rooms")
        fetched = client.get(f"{BASE}/rooms/{room_id}")

        assert listed.status_code == 200
        assert fetched.status_code == 200
        listed_item = next(item for item in listed.json()["items"] if item["id"] == room_id)
        assert listed_item == fetched.json()

    def test_list_prefers_node_backed_room_values_over_legacy_row(self, client, db):
        room = SpatialRoom(
            id="room-diverged-list",
            name="Node Name",
            description="Node Description",
            room_type=RoomType.research,
            owner_id="user",
            metadata={"theme": "blue"},
        )
        db.save(room)
        db._execute(
            """
            UPDATE spatialrooms
            SET name = $name, description = $description, metadata = $metadata
            WHERE id = $id
            """,
            {
                "id": room.id,
                "name": "Legacy Name",
                "description": "Legacy Description",
                "metadata": '{"theme":"legacy"}',
            },
        )

        response = client.get(f"{BASE}/rooms")

        assert response.status_code == 200
        item = next(item for item in response.json()["items"] if item["id"] == room.id)
        assert item["name"] == "Node Name"
        assert item["description"] == "Node Description"
        assert item["metadata"] == {"theme": "blue"}

    def test_list_room_defaults_shape_for_empty_node_attributes(self, client, db):
        db.save(
            Document(
                id="room-empty-list",
                name="Sparse Node Room",
                node_kind="room",
                prototype_key="room",
                doc_type="folder",
                attributes={},
            )
        )

        response = client.get(f"{BASE}/rooms")

        assert response.status_code == 200
        item = next(item for item in response.json()["items"] if item["id"] == "room-empty-list")
        assert item["description"] == ""
        assert item["room_type"] == "research"
        assert item["owner_id"] == "user"
        assert item["metadata"] == {}

    def test_list_rooms_raises_when_legacy_room_lost_its_node(self, client, db):
        room = SpatialRoom(id="room-list-missing-node", name="Legacy Only")
        db.save(room)
        db._execute("DELETE FROM documents WHERE id = $id", {"id": room.id})

        response = client.get(f"{BASE}/rooms")

        assert response.status_code == 404
        assert response.json()["detail"] == f"Room node not found: {room.id}"

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
    def test_get_document_backed_room(self, client, db):
        db.save(
            Document(
                id="room-doc-get",
                name="Node-Owned Room",
                node_kind="room",
                prototype_key="room",
                doc_type="folder",
                attributes={
                    "description": "Folded room",
                    "room_type": "presentation",
                    "owner_id": "human",
                    "metadata": {"theme": "amber"},
                },
            )
        )

        r = client.get(f"{BASE}/rooms/room-doc-get")
        assert r.status_code == 200
        assert r.json()["id"] == "room-doc-get"
        assert r.json()["name"] == "Node-Owned Room"
        assert r.json()["room_type"] == "presentation"
        assert r.json()["metadata"] == {"theme": "amber"}

    def test_get_prefers_node_backed_room_values_over_legacy_row(self, client, db):
        room = SpatialRoom(
            id="room-diverged-get",
            name="Node Truth",
            description="From node",
            room_type=RoomType.presentation,
            owner_id="human",
            metadata={"theme": "amber"},
        )
        db.save(room)
        db._execute(
            """
            UPDATE spatialrooms
            SET name = $name, description = $description
            WHERE id = $id
            """,
            {"id": room.id, "name": "Legacy Drift", "description": "From legacy"},
        )

        response = client.get(f"{BASE}/rooms/{room.id}")

        assert response.status_code == 200
        assert response.json()["name"] == "Node Truth"
        assert response.json()["description"] == "From node"

    def test_get_room_defaults_shape_for_empty_node_attributes(self, client, db):
        db.save(
            Document(
                id="room-empty-get",
                name="Sparse Node Room",
                node_kind="room",
                prototype_key="room",
                doc_type="folder",
                attributes={},
            )
        )

        response = client.get(f"{BASE}/rooms/room-empty-get")

        assert response.status_code == 200
        assert response.json()["description"] == ""
        assert response.json()["room_type"] == "research"
        assert response.json()["owner_id"] == "user"
        assert response.json()["metadata"] == {}

    def test_get_room_raises_when_legacy_room_lost_its_node(self, client, db):
        room = SpatialRoom(id="room-missing-node", name="Legacy Only")
        db.save(room)
        db._execute("DELETE FROM documents WHERE id = $id", {"id": room.id})

        response = client.get(f"{BASE}/rooms/{room.id}")

        assert response.status_code == 404
        assert response.json()["detail"] == f"Room node not found: {room.id}"

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
    def test_update_document_backed_room_preserves_parent_edge(self, client, db):
        db.save(
            Document(
                id="room-doc-upd",
                parent_id="workspace-root",
                name="Old Room",
                node_kind="room",
                prototype_key="room",
                doc_type="folder",
                attributes={
                    "description": "Before update",
                    "room_type": "research",
                    "owner_id": "user",
                    "metadata": {"theme": "blue"},
                },
            )
        )

        r = client.patch(
            f"{BASE}/rooms/room-doc-upd",
            json={
                "name": "Renamed Room",
                "description": "After update",
                "room_type": "presentation",
                "metadata": {"theme": "gold"},
            },
        )
        assert r.status_code == 200
        assert r.json()["name"] == "Renamed Room"
        assert r.json()["description"] == "After update"
        assert r.json()["room_type"] == "presentation"
        assert r.json()["metadata"] == {"theme": "gold"}

        mirrored = db.get(Document, "room-doc-upd")
        assert mirrored is not None
        assert mirrored.parent_id == "workspace-root"
        assert mirrored.prototype_key == "room"
        assert mirrored.name == "Renamed Room"
        assert mirrored.attributes["description"] == "After update"
        assert mirrored.attributes["room_type"] == "presentation"
        assert mirrored.attributes["metadata"] == {"theme": "gold"}

    def test_update_room_writes_through_node_and_legacy_storage(self, client, db):
        room = SpatialRoom(
            id="room-write-through",
            name="Before",
            description="Before update",
            room_type=RoomType.research,
            owner_id="user",
            metadata={"theme": "blue"},
        )
        db.save(room)

        response = client.patch(
            f"{BASE}/rooms/{room.id}",
            json={
                "name": "After",
                "description": "After update",
                "room_type": "presentation",
                "metadata": {"theme": "gold"},
            },
        )

        assert response.status_code == 200
        mirrored = db.get(Document, room.id)
        legacy = _legacy_room(db, room.id)
        assert mirrored is not None
        assert mirrored.name == "After"
        assert mirrored.attributes["description"] == "After update"
        assert mirrored.attributes["room_type"] == "presentation"
        assert legacy is not None
        assert legacy.name == "After"
        assert legacy.description == "After update"
        assert legacy.room_type == RoomType.presentation
        assert legacy.metadata == {"theme": "gold"}

    def test_update_document_backed_room_preserves_child_containment(self, client, db):
        db.save(
            Document(
                id="room-child-parent",
                parent_id="workspace-root",
                name="Contained Room",
                node_kind="room",
                prototype_key="room",
                doc_type="folder",
                attributes={"room_type": "research"},
            )
        )
        db.save(
            Document(
                id="room-child-doc",
                parent_id="room-child-parent",
                name="Child Note",
                doc_type="file",
            )
        )

        response = client.patch(
            f"{BASE}/rooms/room-child-parent",
            json={"name": "Renamed Contained Room", "description": "Still contains children"},
        )

        assert response.status_code == 200
        mirrored = db.get(Document, "room-child-parent")
        child = db.get(Document, "room-child-doc")
        assert mirrored is not None
        assert mirrored.parent_id == "workspace-root"
        assert child is not None
        assert child.parent_id == "room-child-parent"

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
        assert db.get(Document, "r-del") is None
        assert _legacy_room(db, "r-del") is None

    def test_delete_missing_room_returns_404(self, client):
        r = client.delete(f"{BASE}/rooms/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Room write invariants — audit + change stream
# ---------------------------------------------------------------------------


def _room_audits(db, room_id: str) -> list[ActionAudit]:
    return [
        audit for audit in db.all(ActionAudit)
        if room_id in (audit.target_ids or [])
    ]


def _assert_room_mutation_audited(db, room_id: str) -> ActionAudit:
    audits = _room_audits(db, room_id)
    assert audits, f"expected ActionAudit for room mutation target {room_id}"
    audit = audits[-1]
    assert audit.actor, "expected ActionAudit.actor to be populated"
    assert audit.action_name, "expected ActionAudit.action_name to be populated"
    assert room_id in (audit.target_ids or [])
    return audit


class TestRoomWriteMutationInvariants:
    def test_create_room_writes_audit_and_emits_change(self, client, db, monkeypatch):
        emit_calls: list[tuple[tuple, dict]] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: emit_calls.append((a, k)),
        )

        response = client.post(
            f"{BASE}/rooms",
            json={
                "name": "Audited Room",
                "room_type": "research",
                "description": "must write audit and emit",
            },
        )

        assert response.status_code == 200
        room_id = response.json()["id"]
        audit = _assert_room_mutation_audited(db, room_id)
        assert audit.params is not None
        assert emit_calls, "expected emit_change call for room create"
        assert emit_calls[-1][1]["actor"] == audit.actor
        assert room_id in (emit_calls[-1][1].get("document_ids") or [])

    def test_update_room_writes_audit_and_emits_change(self, client, db, monkeypatch):
        emit_calls: list[tuple[tuple, dict]] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: emit_calls.append((a, k)),
        )

        room = SpatialRoom(
            id="room-audit-update",
            name="Before",
            description="Before update",
            room_type=RoomType.research,
        )
        db.save(room)

        response = client.patch(
            f"{BASE}/rooms/{room.id}",
            json={"name": "After", "description": "After update"},
        )

        assert response.status_code == 200
        audit = _assert_room_mutation_audited(db, room.id)
        assert audit.params is not None
        assert emit_calls, "expected emit_change call for room update"
        assert emit_calls[-1][1]["actor"] == audit.actor
        assert room.id in (emit_calls[-1][1].get("document_ids") or [])

    def test_delete_room_writes_audit_and_emits_change(self, client, db, monkeypatch):
        emit_calls: list[tuple[tuple, dict]] = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: emit_calls.append((a, k)),
        )

        room = SpatialRoom(id="room-audit-delete", name="Delete Me")
        db.save(room)

        response = client.delete(f"{BASE}/rooms/{room.id}")

        assert response.status_code == 200
        audit = _assert_room_mutation_audited(db, room.id)
        assert emit_calls, "expected emit_change call for room delete"
        assert emit_calls[-1][1]["actor"] == audit.actor
        assert room.id in (emit_calls[-1][1].get("document_ids") or [])


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
