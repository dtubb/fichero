"""`openapi.mcp.answers-fit-an-agent` (docs/contributor_manual/specs/harness/surfaces-from-openapi.md).

WHY (2026-10-11, the hands-on pass over every read-only MCP tool): four tools answered hundreds of KB on a ten-page
project (the workflow tools grouped 850 KB, the tools 750 KB, the action registry 680 KB, the workflows 516 KB), more
than an agent can hold. Each route takes a lean `summary` (an agent's tool asks for it by default, through the
contract's `x-fichero-agent-defaults`; the app, calling with no parameters, keeps the whole answer), a filter and
paging, and one item is one GET away whole. A guard calls every generated read tool on a small project through the
MCP protocol and holds each answer under 64 KB unless its route is marked bulk (`x-fichero-bulk`).
"""
from __future__ import annotations

import asyncio
import inspect
import json
import re
from pathlib import Path

import pytest
from mcp import types

from fichero_mcp import server as mcp_server
from fichero_mcp.openapi_tools_generated import TOOLS
from tests.unit.mcp.test_generated_mcp_tools_reach_the_engine import mcp_on_the_real_app  # noqa: F401 (fixture)

LIMIT = 64 * 1024
CONTRACT = json.loads((Path(__file__).resolve().parents[2] / "contracts" / "openapi.json").read_text())
#: Reads that reach the network, download, or stream: not called here.
NETWORK = re.compile(r"(huggingface|/hf/|online|enrich|external|authorit|wikidata|geonames|remote|download|"
                     r"/stream|/events|/browse|/discover|/fetch|/integrations/)", re.I)


def _call(name: str, arguments: dict) -> types.CallToolResult:
    handler = mcp_server.mcp._mcp_server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(method="tools/call",
                                    params=types.CallToolRequestParams(name=name, arguments=arguments))
    return asyncio.run(handler(request)).root


def _text(result: types.CallToolResult) -> str:
    return "".join(getattr(block, "text", "") or "" for block in result.content)


@pytest.fixture
def every_tool(mcp_on_the_real_app):  # noqa: F811
    mcp_server.select_toolsets(mcp_server.parse_toolsets("all"))
    yield mcp_on_the_real_app
    mcp_server.select_toolsets(mcp_server.DEFAULT_TOOLSETS)


@pytest.mark.parametrize("tool", ["fichero_workflows_list_tools", "fichero_workflows_list_tools_grouped",
                                  "fichero_actions_list_registered", "fichero_workflows_list"])
def test_the_four_large_lists_answer_an_agent_a_lean_summary(every_tool, client, tool):
    result = _call(tool, {})
    assert result.isError is False, _text(result)
    text = _text(result)
    assert len(text) < LIMIT, (tool, len(text))
    assert '"config_schema": {' not in text.replace('"config_schema": {}', ""), "no tool schema in a summary"


def test_the_app_still_gets_the_whole_answer(client):
    tools = client.get("/api/workflows/tools").json()
    assert any(t["input_ports"] or t["output_ports"] for t in tools["items"]), "the editor's ports"
    assert tools["conversions"], "the editor's conversion table"
    actions = client.get("/api/actions/registry").json()
    assert any(a["params_schema"] for a in actions["items"])


def test_a_list_filters_pages_and_one_item_is_whole(client):
    every = client.get("/api/workflows/tools", params={"summary": True}).json()
    page = client.get("/api/workflows/tools", params={"summary": True, "limit": 2, "offset": 1}).json()
    assert [t["name"] for t in page["items"]] == [t["name"] for t in every["items"]][1:3]
    assert page["total"] == len(every["items"])
    name = every["items"][0]["name"]
    found = client.get("/api/workflows/tools", params={"summary": True, "q": name}).json()
    assert name in [t["name"] for t in found["items"]]
    assert client.get(f"/api/workflows/tools/{name}").json()["name"] == name

    registry = client.get("/api/actions/registry", params={"summary": True, "q": "document."}).json()
    assert registry["items"] and all(a["params_schema"] == {} for a in registry["items"])
    one = client.get(f"/api/actions/registry/{registry['items'][0]['name']}").json()
    assert one["params_schema"], "one action, whole"
    assert client.get("/api/actions/registry/no.such.action").status_code == 404


def _args(tool, ids: dict) -> dict:
    out = {}
    for name, param in inspect.signature(tool.fn).parameters.items():
        if param.default is inspect.Parameter.empty:
            out[name] = ids.get(name, "probe-none")
    return out


def test_every_generated_read_answers_an_agent_under_64_kb(every_tool, client, db, test_package):
    """The guard: no read tool hands an agent more than 64 KB on a small project, unless its route is bulk."""
    from fichero_server.models import DocType, Document
    from fichero_server.workflows.default_workflows import seed_default_workflows

    seed_default_workflows(db)
    folder = Document(name="Box 1", doc_type=DocType.folder)
    db.save(folder)
    pages = [Document(name=f"f. {i}r", parent_id=folder.id, page_content="Yten dixo el testigo " * 20)
             for i in range(10)]
    for page in pages:
        db.save(page)
    ids = {"doc_id": pages[0].id, "document_id": pages[0].id, "folder_id": folder.id, "page_id": pages[0].id}

    too_big = []
    for tool in TOOLS:
        if tool.method != "GET" or NETWORK.search(tool.path):
            continue
        if CONTRACT["paths"].get(tool.path, {}).get("get", {}).get("x-fichero-bulk"):
            continue
        result = _call(tool.name, _args(tool, ids))
        size = len(_text(result))
        if size > LIMIT:
            too_big.append(f"{tool.name} ({tool.path}): {size // 1024} KB")
    assert too_big == [], too_big
