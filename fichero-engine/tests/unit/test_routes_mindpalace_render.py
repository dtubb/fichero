from __future__ import annotations

from fichero.spatial_models import SpatialRoom, RoomType


def test_scene_render_returns_placeholder_payload(client, db):
    room = SpatialRoom(name="R1", room_type=RoomType.research, owner_id="user")
    db.save(room)

    r = client.post("/api/mindpalace/render", json={"room_id": room.id, "include_video": True})
    assert r.status_code == 200
    data = r.json()
    assert data["room_id"] == room.id
    assert data["png_base64"]
    assert data["mp4_base64"]
    assert data["metadata"]["placeholder"] is True


def test_scene_render_404_for_missing_room(client):
    r = client.post("/api/mindpalace/render", json={"room_id": "nope"})
    assert r.status_code == 404
