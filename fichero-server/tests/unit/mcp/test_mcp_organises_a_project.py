"""An agent organises a project through the MCP, as a historian does in the app (#5568;
specs/harness/surfaces-from-openapi.md, openapi.mcp.organise-a-project).

WHY: organising Istmina Full's loose sentencias, the MCP offered one document's x/y and nothing
else; the agent dropped to the CLI. Here an agent uses only the DEFAULT tool surface, through the
MCP protocol, against the real routes: it groups pages into a document in its order, gives the
document a prototype and attribute values, lays the board out with a label, LOOKS at it (an image),
and ungroups. Nothing is mocked but the transport (the in-process app answers).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json

import httpx
import pytest
from mcp import types
from PIL import Image

from fichero_cli import FicheroClient
from fichero_mcp import server as mcp_server
from fichero_server.models import DocType, Document


@pytest.fixture
def agent(client, test_package, monkeypatch):
    def forward(request: httpx.Request) -> httpx.Response:
        answered = client.request(request.method, request.url.path, params=dict(request.url.params),
                                  content=request.content or None,
                                  headers={"content-type": request.headers.get("content-type", "application/json")})
        return httpx.Response(answered.status_code, content=answered.content,
                              headers={"content-type": answered.headers.get("content-type", "application/json")})

    def build() -> FicheroClient:
        return FicheroClient(base_url="http://test", library_path=str(test_package), token="t",
                             transport=httpx.MockTransport(forward))

    monkeypatch.setattr(mcp_server, "_client", build)
    monkeypatch.setattr(mcp_server, "_mutating_client", build)
    return mcp_server.mcp


def _call(server, name: str, arguments: dict) -> types.CallToolResult:
    handler = server._mcp_server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call", params=types.CallToolRequestParams(name=name, arguments=arguments),
    )
    result = asyncio.run(handler(request)).root
    assert result.isError is False, (name, result.content)
    return result


def _json(result: types.CallToolResult):
    return json.loads(result.content[0].text)


def test_the_default_surface_offers_what_organising_needs():
    names = {tool.name for tool in asyncio.run(mcp_server.mcp.list_tools())}
    assert {
        "fichero_documents_create_group", "fichero_documents_ungroup", "fichero_documents_reorder",
        "fichero_documents_move", "fichero_documents_assign_prototype", "fichero_documents_update",
        "fichero_documents_get_effective_attributes",
        "fichero_classifications_list_values", "fichero_classifications_create_value",
        "fichero_canvas_get_folder_layout", "fichero_canvas_save_folder_layout",
        "fichero_canvas_arrange_folder_layout", "fichero_canvas_create_folder_item",
        "fichero_canvas_update_folder_item", "fichero_canvas_delete_folder_item",
        "fichero_canvas_list_folder_items", "fichero_canvas_get_folder_picture",
    } <= names


def test_an_agent_groups_types_lays_out_looks_and_ungroups(agent, db):
    db.save(Document(id="sentencias", name="1948 Sentencias", doc_type=DocType.folder))
    for index in range(4):
        db.save(Document(id=f"p{index}", name=f"page {index}", parent_id="sentencias",
                         doc_type=DocType.file, sort_order=index))

    # Pages 2, 0, 1 are one case, in THAT order.
    group = _json(_call(agent, "fichero_documents_create_group", {"name": "Case 1", "child_ids": ["p2", "p0", "p1"]}))
    _call(agent, "fichero_documents_reorder", {"body": ["p2", "p0", "p1"]})
    members = sorted(db.query(Document, parent_id=group["id"]), key=lambda d: d.sort_order)
    assert [m.id for m in members] == ["p2", "p0", "p1"]

    # A prototype with attributes, given to the document, then its own values.
    _call(agent, "fichero_classifications_create_value", {
        "dimension": "document_prototype", "key": "sentencia", "label": "Sentencia",
        "attributes": {"court": "", "year": None},
    })
    keys = [v["key"] for v in _json(_call(agent, "fichero_classifications_list_values", {"dimension": "document_prototype"}))["items"]]
    assert "sentencia" in keys
    _call(agent, "fichero_documents_assign_prototype", {"doc_id": group["id"], "prototype_key": "sentencia"})
    _call(agent, "fichero_documents_update", {"doc_id": group["id"], "attributes": {"court": "Istmina", "year": 1948}})
    saved = db.get(Document, group["id"])
    assert saved.prototype_key == "sentencia"
    assert saved.attributes["court"] == "Istmina" and saved.attributes["year"] == 1948

    # The board: the case on the left, the loose page on the right, a label above the case.
    label = _json(_call(agent, "fichero_canvas_create_folder_item",
                        {"folder_id": "sentencias", "kind": "text", "text": "Case 1: Istmina 1948"}))
    _call(agent, "fichero_canvas_save_folder_layout", {"folder_id": "sentencias", "items": [
        {"item_id": group["id"], "x": 0, "y": 0},
        {"item_id": "p3", "x": 400, "y": 0},
        {"item_id": label["id"], "x": 0, "y": -200, "w": 240, "h": 60},
    ]})
    layout = {row["item_id"] for row in _json(_call(agent, "fichero_canvas_get_folder_layout", {"folder_id": "sentencias"}))["items"]}
    assert {group["id"], "p3", label["id"]} <= layout

    # LOOK: the answer is an image the agent can see.
    look = _call(agent, "fichero_canvas_get_folder_picture", {"folder_id": "sentencias", "max_size": 800})
    (block,) = look.content
    assert block.type == "image" and block.mimeType == "image/png"
    picture = Image.open(io.BytesIO(base64.b64decode(block.data)))
    assert max(picture.size) <= 800 and picture.size[0] > picture.size[1], "a wide board, as laid out"

    # And undo the grouping: the pages go back where they were.
    _call(agent, "fichero_documents_ungroup", {"group_id": group["id"]})
    assert {d.id for d in db.query(Document, parent_id="sentencias")} >= {"p0", "p1", "p2", "p3"}
