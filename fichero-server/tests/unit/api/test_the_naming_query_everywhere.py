"""The place query answers the same through MCP as through the route (maps D3 follow-up;
`source.geo.gazetteer-query`, "the same from the app, MCP and the command line").

WHY: one question, one code path: the MCP tool is generated from (#5453) and calls only `GET /api/links/naming`, so
an agent asking "which segments name Pleiades place ..." gets exactly the app's answer, never a
second implementation that drifts. The command line's `links naming` is generated from the same
route by the contract sync. If this regresses, the agent and the app disagree about a place.
"""

from __future__ import annotations

import httpx

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_cli import FicheroClient
from fichero_mcp import openapi_tools_generated as generated
from fichero_mcp import server as mcp_server
from tests.unit.api.test_gazetteer_links_and_query import Q90, test_every_segment_naming_the_place_by_any_spelling_of_its_uri


def test_the_mcp_tool_is_the_route(db, client, monkeypatch):
    test_every_segment_naming_the_place_by_any_spelling_of_its_uri(db, client)   # two labels, one withdrawn
    by_route = client.get("/api/links/naming", params={"uri": Q90}).json()

    def forward(request: httpx.Request) -> httpx.Response:
        answered = client.request(request.method, request.url.path, params=dict(request.url.params))
        return httpx.Response(answered.status_code, json=answered.json())

    monkeypatch.setattr(mcp_server, "_client", lambda: FicheroClient(
        base_url="http://test", library_path="/tmp/Lib.fichero", token="t", transport=httpx.MockTransport(forward)))
    by_tool = generated.fichero_links_segments_naming_place(uri="https://www.wikidata.org/wiki/Q90")
    assert by_tool == by_route and len(by_tool["segments"]) == 1
