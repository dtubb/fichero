from __future__ import annotations

import asyncio

from fichero import mcp_full


def _tool_names() -> set[str]:
    return {tool.name for tool in asyncio.run(mcp_full.mcp.list_tools())}


EXPECTED_FULL_TOOLS = {
    "health",
    "import_document",
    "list_documents",
    "get_document",
    "document_inspector",
    "document_knowledge_graph",
    "list_workflows",
    "run_workflow",
    "workflow_status",
    "workflow_pause",
    "workflow_resume",
    "list_artifacts",
    "get_artifact",
    "query_kg_entities",
    "query_kg_claims",
    "create_claim",
    "update_claim",
    "delete_claim",
    "kg_search",
    "kg_neighborhood",
    "kg_sparql",
    "citations_at_document",
    "create_note",
    "list_notes",
    "get_note",
    "search",
    "mp_list_rooms",
    "mp_create_room",
    "mp_place_node",
    "mp_move_node",
    "mp_create_note",
    "mp_list_notes",
    "mp_get_note",
    "mp_update_note",
    "mp_delete_note",
    "scene_render",
}


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._render_counter = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def request(self, method: str, path: str, json=None):
        if method == "POST" and path == "/api/mindpalace/render":
            self._render_counter += 1
            return {
                "room_id": json["room_id"],
                "rendered_at": f"t{self._render_counter}",
                "png_base64": "png",
                "mp4_base64": "mp4",
                "metadata": {"frame": self._render_counter},
            }
        if method == "POST" and path.endswith("/pause"):
            return {
                "thread_id": path.split("/")[-2],
                "status": "pause_requested",
                "message": "Pause requested.",
            }
        if method == "POST" and path.endswith("/resume"):
            return {
                "thread_id": path.split("/")[-2],
                "workflow_id": "wf-1",
                "workflow_name": "Test",
                "status": "running",
            }
        raise AssertionError(f"unexpected request: {method} {path}")

    def create_claim(self, text: str, **kwargs):
        self.calls.append(("create_claim", {"text": text, **kwargs}))
        return {"id": "claim-1", "text": text}

    def update_claim(self, claim_id: str, **fields):
        self.calls.append(("update_claim", {"claim_id": claim_id, **fields}))
        return {"id": claim_id, **fields}

    def delete_claim(self, claim_id: str):
        self.calls.append(("delete_claim", {"claim_id": claim_id}))
        return None

    def mp_move_node(self, node_id: str, *, position_x: float, position_y: float, position_z: float):
        self.calls.append(
            (
                "move",
                {
                    "node_id": node_id,
                    "x": position_x,
                    "y": position_y,
                    "z": position_z,
                },
            )
        )
        return {
            "id": node_id,
            "room_id": "room-1",
            "node_type": "note",
            "position_x": position_x,
            "position_y": position_y,
            "position_z": position_z,
        }

    def mp_list_rooms(self, *, room_type=None):
        self.calls.append(("list_rooms", {"room_type": room_type}))
        return [{"id": "room-1", "name": "Room", "room_type": "research"}]

    def mp_create_room(self, *, name: str, room_type: str, description: str):
        self.calls.append(("create_room", {"name": name, "room_type": room_type, "description": description}))
        return {"id": "room-2", "name": name, "room_type": room_type, "description": description}

    def mp_place_node(self, *, room_id: str, node_type: str, source_id=None, label: str = ""):
        self.calls.append(
            (
                "place_node",
                {
                    "room_id": room_id,
                    "node_type": node_type,
                    "source_id": source_id,
                    "label": label,
                },
            )
        )
        return {"id": "node-7", "room_id": room_id, "node_type": node_type, "label": label}

    def mp_create_note(self, **payload):
        self.calls.append(("mp_create_note", payload))
        return {
            "id": "note-1",
            "content": payload["content"],
            "note_type": "user",
            "author_type": "user",
            "status": "draft",
        }

    def mp_list_notes(self, *, room_id=None, note_type=None):
        self.calls.append(("mp_list_notes", {"room_id": room_id, "note_type": note_type}))
        return [{"id": "note-1", "content": "A", "note_type": "user", "author_type": "user", "status": "draft"}]

    def mp_get_note(self, note_id: str):
        self.calls.append(("mp_get_note", {"note_id": note_id}))
        return {"id": note_id, "content": "A", "note_type": "user", "author_type": "user", "status": "draft"}

    def mp_update_note(self, note_id: str, **payload):
        self.calls.append(("mp_update_note", {"note_id": note_id, **payload}))
        return {
            "id": note_id,
            "content": payload.get("content", "A"),
            "note_type": "user",
            "author_type": "user",
            "status": "draft",
        }

    def mp_delete_note(self, note_id: str):
        self.calls.append(("mp_delete_note", {"note_id": note_id}))
        return {"status": "deleted"}


def test_full_tools_include_scene_render():
    names = _tool_names()
    assert names == EXPECTED_FULL_TOOLS


def test_scripted_render_move_rerender(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(mcp_full, "_client", lambda: fake)

    first = mcp_full.scene_render(mcp_full.SceneRenderInput(room_id="room-1"))
    moved = mcp_full.mp_move_node(
        mcp_full.MoveNodeInput(node_id="node-1", position_x=1.0, position_y=2.0, position_z=0.0)
    )
    second = mcp_full.scene_render(mcp_full.SceneRenderInput(room_id="room-1"))

    assert first.metadata["frame"] == 1
    assert moved.id == "node-1"
    assert second.metadata["frame"] == 2
    assert fake.calls[0][0] == "move"


def test_claim_mutation_tools_passthrough(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(mcp_full, "_client", lambda: fake)

    created = mcp_full.create_claim(
        mcp_full.CreateClaimInput(
            text="A links to B",
            source_document_id="doc-1",
            entity_ids=["e1", "e2"],
        )
    )
    updated = mcp_full.update_claim(
        mcp_full.UpdateClaimInput(
            claim_id="claim-1",
            text="A strongly links to B",
            confidence=0.9,
        )
    )
    deleted = mcp_full.delete_claim("claim-1")

    assert created["id"] == "claim-1"
    assert updated["id"] == "claim-1"
    assert deleted is None
    assert fake.calls[0][0] == "create_claim"
    assert fake.calls[1][0] == "update_claim"
    assert fake.calls[2][0] == "delete_claim"


def test_workflow_pause_resume_tools(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(mcp_full, "_client", lambda: fake)

    paused = mcp_full.workflow_pause("thread-123")
    resumed = mcp_full.workflow_resume("thread-123")

    assert paused["status"] == "pause_requested"
    assert paused["thread_id"] == "thread-123"
    assert resumed["status"] == "running"
    assert resumed["thread_id"] == "thread-123"


def test_mind_palace_tools_are_typed(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(mcp_full, "_client", lambda: fake)

    rooms = mcp_full.mp_list_rooms()
    room = mcp_full.mp_create_room("Room B")
    placed = mcp_full.mp_place_node(room_id="room-1", node_type="note", label="N")
    note = mcp_full.mp_create_note(mcp_full.MPCreateNoteInput(content="hello"))
    notes = mcp_full.mp_list_notes(mcp_full.MPListNotesInput(room_id="room-1"))
    got = mcp_full.mp_get_note("note-1")
    updated = mcp_full.mp_update_note(mcp_full.MPUpdateNoteInput(note_id="note-1", content="updated"))
    deleted = mcp_full.mp_delete_note("note-1")

    assert rooms[0].id == "room-1"
    assert room.id == "room-2"
    assert placed.id == "node-7"
    assert note.id == "note-1"
    assert notes[0].id == "note-1"
    assert got.id == "note-1"
    assert updated.id == "note-1"
    assert deleted.status == "deleted"
