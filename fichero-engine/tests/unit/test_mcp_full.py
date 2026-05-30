from __future__ import annotations

import asyncio

from fichero import mcp_full


def _tool_names() -> set[str]:
    return {tool.name for tool in asyncio.run(mcp_full.mcp.list_tools())}


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
        raise AssertionError(f"unexpected request: {method} {path}")

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
        return {"id": node_id, "position_x": position_x, "position_y": position_y, "position_z": position_z}


def test_full_tools_include_scene_render():
    names = _tool_names()
    assert "scene_render" in names
    assert "mp_move_node" in names
    assert "run_workflow" in names


def test_scripted_render_move_rerender(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(mcp_full, "_client", lambda: fake)

    first = mcp_full.scene_render(mcp_full.SceneRenderInput(room_id="room-1"))
    moved = mcp_full.mp_move_node(
        mcp_full.MoveNodeInput(node_id="node-1", position_x=1.0, position_y=2.0, position_z=0.0)
    )
    second = mcp_full.scene_render(mcp_full.SceneRenderInput(room_id="room-1"))

    assert first.metadata["frame"] == 1
    assert moved["id"] == "node-1"
    assert second.metadata["frame"] == 2
    assert fake.calls[0][0] == "move"
