"""Generated MCP tools call the real engine routes, through the MCP protocol (#5453).

`specs/harness/surfaces-from-openapi.md` A1, A5, A6: a tool generated from the contract makes one
request to its route and returns that route's answer, a write lands in the library, and a refusal
reaches the agent as a typed error. Driven through `fichero_mcp.server.mcp` exactly as an MCP
client drives it (tools/call), its requests answered by the in-process app over the test library
(the `client` fixture), so neither the route nor the tool is mocked.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from mcp import types

from fichero_cli import FicheroClient
from fichero_mcp import server as mcp_server
from fichero_server.models import Document


@pytest.fixture
def mcp_on_the_real_app(client, test_package, monkeypatch):
    """The MCP server's clients, their requests answered by the in-process app."""
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
    return asyncio.run(handler(request)).root


def _payload(result: types.CallToolResult):
    text = result.content[0].text
    return json.loads(text[text.index("{"):]) if result.isError else json.loads(text)


def test_a_generated_write_lands_and_a_generated_read_answers_what_the_route_answers(
    mcp_on_the_real_app, client, db,
):
    """WHY: a generated tool that built the wrong request would still look fine against a mock.
    The write must create the folder in the library, and the read must return exactly the route's
    own answer for it (one route, one answer, whatever the surface)."""
    created = _call(mcp_on_the_real_app, "fichero_documents_create",
                    {"name": "SM_NPQ_C09", "doc_type": "folder"})
    assert created.isError is False, created.content
    doc_id = _payload(created)["id"]
    assert [d.name for d in db.query(Document) if d.id == doc_id] == ["SM_NPQ_C09"]

    read = _call(mcp_on_the_real_app, "fichero_documents_get", {"doc_id": doc_id})
    assert read.isError is False, read.content
    assert _payload(read) == client.get(f"/api/documents/{doc_id}").json()


def test_a_refusal_from_the_route_reaches_the_agent_typed(mcp_on_the_real_app):
    """WHY: an agent given an empty result for a missing document would report there is nothing
    there. The engine's 404 and its detail must arrive as an error result."""
    result = _call(mcp_on_the_real_app, "fichero_documents_get", {"doc_id": "no-such-document"})
    assert result.isError is True
    error = _payload(result)
    assert error["status"] == 404 and error["route"] == "GET /api/documents/no-such-document"
    assert error["detail"], "the engine's sentence, not an empty detail"
