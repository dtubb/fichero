"""MCP tools generated from the OpenAPI contract (#5453, `docs/contributor_manual/specs/harness/surfaces-from-openapi.md`).

Pins behaviours A1–A6 of that spec without an engine: the generator's naming and exclusions,
toolsets by tag, the drift guard, one route one tool, mutations through the agent client, and
typed errors. The engine half (a generated tool calling the real route) is in
`fichero-server/tests/unit/mcp/test_generated_mcp_tools_reach_the_engine.py`.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import httpx
import pytest
from mcp import types
from mcp.server.fastmcp import FastMCP

from fichero_cli import FicheroClient
from fichero_mcp import openapi_runtime
from fichero_mcp import openapi_tools_generated as generated
from fichero_mcp import server as mcp_server

REPO = Path(__file__).resolve().parents[2]
GUARD = REPO / "scripts" / "check_mcp_generated_current.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


generator = _load("generate_openapi_mcp", REPO / "fichero-server" / "scripts" / "generate_openapi_mcp.py")
operations_module = sys.modules["openapi_operations"]
CONTRACT = json.loads((REPO / "fichero-server" / "tests" / "contracts" / "openapi.json").read_text())


def _contract_operations() -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in CONTRACT["paths"].items()
        for method in item
        if method in operations_module.HTTP_METHODS
    }


def _names(server: FastMCP) -> set[str]:
    return {tool.name for tool in asyncio.run(server.list_tools())}


# -- A1: one tool per operation ------------------------------------------------
def test_every_operation_outside_the_exclusions_has_exactly_one_tool():
    """WHY (openapi.mcp.one-tool-per-operation): adding a route must add its tool, and no route
    may get two. The only routes without a tool are the shared exclusion list (the CLI's) and the
    event streams a tool call cannot hold open."""
    tooled = [(tool.method, tool.path) for tool in generated.TOOLS]
    assert len(tooled) == len(set(tooled)), "a route has two generated tools"
    excluded = {
        (m, p) for m, p in _contract_operations()
        if p in operations_module.INTENTIONALLY_UNWIRED_PATHS or (m == "GET" and re.search(r"/stream(/|$)", p))
    }
    assert set(tooled) == _contract_operations() - excluded
    assert ("GET", "/api/health") in excluded and ("GET", "/api/changes/stream") in excluded


def test_a_tool_is_named_from_its_tag_and_its_handler():
    """WHY: the name is what an agent picks a tool by, so it must be predictable from the contract:
    `fichero_<tag>_<handler>`, without repeating the tag's own words, and unique."""
    ops = {(op.method, op.path): op for op in generator.operations()}
    seen: set[str] = set()
    assert generator.tool_name(ops[("GET", "/api/hpc/clusters")], seen) == "fichero_hpc_list_clusters"
    assert generator.tool_name(ops[("POST", "/api/training/kraken")], seen) == "fichero_training_start_kraken"
    # local-models' `list_local_models` drops the tag's words, leaving the verb.
    assert generator.tool_name(ops[("GET", "/api/local-models")], seen) == "fichero_local_models_list"
    # A second operation reaching the same name is told apart by its method, never dropped.
    again = generator.tool_name(ops[("GET", "/api/hpc/clusters")], seen)
    assert again == "fichero_hpc_list_clusters_get"
    names = [tool.name for tool in generated.TOOLS]
    assert len(names) == len(set(names))
    assert all(re.fullmatch(r"fichero_[a-z0-9_]+", n) and len(n) <= 64 for n in names)


def test_each_generated_tool_is_one_engine_call_and_nothing_else():
    """WHY: a generated tool that held logic would be a second implementation beside the route,
    exactly what the generator exists to prevent. Every body is a docstring and one
    `_rt.call(...)`, or `_rt.image(...)` for a GET that answers a picture (#5568)."""
    tree = ast.parse(Path(generated.__file__).read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]
    assert len(functions) == len(generated.TOOLS)
    images = generator.image_routes()
    by_name = {tool.name: tool for tool in generated.TOOLS}
    for fn in functions:
        doc, ret = fn.body
        assert isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant), fn.name
        tool = by_name[fn.name]
        expected = "_rt.image" if (tool.method, tool.path) in images else "_rt.call"
        assert isinstance(ret, ast.Return) and ast.unparse(ret.value.func) == expected, fn.name
    assert ("GET", "/api/canvas/folders/{folder_id}/canvas-picture") in images


def test_a_picture_route_answers_the_agent_with_an_image(monkeypatch):
    """WHY (openapi.mcp.pictures-are-images, #5568): an agent organising a board must SEE it. A route answering image/png reaches the
    agent as MCP image content, not as a count of bytes; a refusal is still a typed error."""
    import base64
    import io

    from PIL import Image as PILImage

    buffer = io.BytesIO()
    PILImage.new("RGB", (4, 3), (200, 0, 0)).save(buffer, format="PNG")
    png = buffer.getvalue()
    seen: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/missing/canvas-picture"):
            return httpx.Response(404, json={"detail": "no such folder"})
        return httpx.Response(200, content=png, headers={"content-type": "image/png"})

    monkeypatch.setattr(mcp_server, "_client", _transport_client(answer))
    server = FastMCP("probe")
    server.add_tool(generated.fichero_canvas_get_folder_picture, name="fichero_canvas_get_folder_picture")
    result = asyncio.run(server.call_tool("fichero_canvas_get_folder_picture", {"folder_id": "f1", "max_size": 800}))
    (block,) = result[0] if isinstance(result, tuple) else result
    assert block.type == "image" and block.mimeType == "image/png"
    assert base64.b64decode(block.data) == png
    assert seen[0].url.path == "/api/canvas/folders/f1/canvas-picture"
    assert seen[0].url.params["max_size"] == "800"
    with pytest.raises(Exception, match="no such folder"):
        asyncio.run(server.call_tool("fichero_canvas_get_folder_picture", {"folder_id": "missing"}))


def test_description_and_parameter_docs_come_from_the_route():
    """WHY: the route's own summary, description and schema are the only documentation an agent
    gets; a tool that dropped them would be a name and a bag of arguments."""
    op = CONTRACT["paths"]["/api/training/kraken"]["post"]
    doc = generated.fichero_training_start_kraken.__doc__
    assert op["summary"] in doc and op["description"].split("\n")[0] in doc
    assert "POST /api/training/kraken" in doc and "toolset `training`" in doc
    server = FastMCP("probe")
    server.add_tool(generated.fichero_ingest_folder, name="fichero_ingest_folder")
    (tool,) = asyncio.run(server.list_tools())
    mode = tool.inputSchema["properties"]["mode"]
    assert "link" in mode["description"] and "move" in mode["description"], mode
    assert tool.inputSchema["required"] == ["path"]


def test_every_generated_tool_has_a_usable_schema():
    """WHY: a malformed inputSchema is not a crash; a client just silently refuses to call the tool.
    All of them are registered once here, as `--toolsets all` would."""
    server = FastMCP("all")
    names = mcp_server.select_toolsets(mcp_server.parse_toolsets("all"), server)
    tools = asyncio.run(server.list_tools())
    assert len(tools) == len(set(names))
    for tool in tools:
        assert (tool.description or "").strip(), tool.name
        schema = tool.inputSchema
        assert schema["type"] == "object" and isinstance(schema.get("properties", {}), dict), tool.name
        assert set(schema.get("required", [])) <= set(schema.get("properties", {})), tool.name


# -- A2: toolsets by tag ---------------------------------------------------------
def test_toolsets_list_only_the_chosen_tags_tools():
    """WHY (openapi.mcp.toolsets-by-tag): an agent must see the tools for its job, not all of them;
    a toolset that leaked another tag's tools would defeat the point."""
    server = FastMCP("probe")
    names = set(mcp_server.select_toolsets(["hpc"], server))
    hpc = {tool.name for tool in generated.TOOLS if tool.tag == "hpc"}
    assert hpc and hpc <= names
    generated_names = {tool.name for tool in generated.TOOLS}
    aliases = set(mcp_server.OPERATOR_ALIASES)
    assert (names & generated_names) - aliases == hpc - aliases, "only the hpc tag's generated tools"
    assert names - generated_names <= set(mcp_server.OPERATOR_ALIASES), "anything else is an alias"
    assert _names(server) == names


def test_the_default_is_the_recipe_golden_path_and_all_is_every_tag():
    """WHY: with no flag the server is the recipe golden path the spec names; `all` is every tag."""
    assert mcp_server.DEFAULT_TOOLSETS == (
        "recipes", "training", "check", "segments", "documents", "activity", "local-models", "hpc",
        "canvas", "classifications", "find-documents",
    )
    assert set(mcp_server.DEFAULT_TOOLSETS) <= set(generated.TAGS), "a default toolset is not a real tag"
    assert mcp_server.parse_toolsets("all") == (*generated.TAGS, "ui"), "every tag, and the app's UI verbs"
    names = _names(mcp_server.mcp)
    for tool in generated.TOOLS:
        assert (tool.name in names) == (tool.tag in mcp_server.DEFAULT_TOOLSETS) or tool.name in mcp_server.OPERATOR_ALIASES


def test_an_unknown_toolset_is_refused_naming_the_known_ones():
    """WHY: a typo in --toolsets must not start a server that silently lists nothing for it."""
    with pytest.raises(ValueError, match="unknown toolsets \\['trainng'\\].*training"):
        mcp_server.parse_toolsets("recipes,trainng")


def test_main_narrows_the_toolsets(monkeypatch):
    """WHY: `--toolsets` is read by the console entry point, and narrowing must REMOVE the default
    tools, not add to them."""
    monkeypatch.setattr(mcp_server.mcp, "run", lambda *a, **k: None)
    monkeypatch.setattr("sys.argv", ["fichero-mcp", "--toolsets", "hpc"])
    try:
        mcp_server.main()
        names = _names(mcp_server.mcp)
        assert "fichero_hpc_list_clusters" in names
        assert "fichero_recipes_get_start_plan" not in names
    finally:
        mcp_server.select_toolsets(mcp_server.DEFAULT_TOOLSETS)
    assert "fichero_recipes_get_start_plan" in _names(mcp_server.mcp)


# -- A3: the drift guard -----------------------------------------------------------
def test_the_drift_guard_passes_on_the_committed_module_and_fails_on_a_stale_one(tmp_path):
    """WHY (openapi.mcp.current-with-the-contract): a route added without regenerating must fail
    the gate. Both halves are run: a guard never seen to fail could be unable to."""
    run = lambda *args: subprocess.run(  # noqa: E731
        [sys.executable, str(GUARD), *args], cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    assert run().returncode == 0
    stale = tmp_path / "openapi_tools_generated.py"
    stale.write_text(Path(generated.__file__).read_text().replace("fichero_hpc_list_clusters", "fichero_hpc_gone"))
    result = run(str(stale))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "generate_openapi_mcp.py" in result.stderr
    assert run(str(tmp_path / "missing.py")).returncode == 2, "an unreadable module is BLIND, not a pass"


# -- A4: one route, one tool -----------------------------------------------------------
def test_one_route_one_tool():
    """WHY (openapi.mcp.one-route-one-tool): a hand-written tool beside a generated one for the same
    route is two implementations that drift. Each hand-written tool left must name its routes,
    and one whose single route a generated tool covers must say why it stays."""
    generated_names = {tool.name for tool in generated.TOOLS}
    hand_written = _names(mcp_server.mcp) - generated_names - set(mcp_server.OPERATOR_ALIASES)
    routes = {(tool.method, tool.path) for tool in generated.TOOLS}
    assert hand_written, "the check would be vacuous"
    for name in hand_written:
        doc = getattr(mcp_server, name).__doc__ or ""
        named = re.findall(r"\b(GET|POST|PUT|PATCH|DELETE) (/api/\S+?)[\s.,)]", doc.split("Routes:", 1)[-1])
        assert "Routes:" in doc and named, f"{name} does not name its routes"
        covered = [r for r in named if r in routes]
        if len(named) == 1 and covered:
            assert name in mcp_server.KEPT_SINGLE_ROUTE, f"{name} duplicates {covered[0]}: retire it"
    assert set(mcp_server.KEPT_SINGLE_ROUTE) <= hand_written


def test_every_operator_alias_points_at_a_generated_tool():
    """WHY: an alias keeps an existing agent's tool name working; one pointing at no route would
    break that agent on the first call instead of at startup."""
    routes = {(tool.method, tool.path) for tool in generated.TOOLS}
    for alias, route in mcp_server.OPERATOR_ALIASES.items():
        assert route in routes, f"{alias} -> {route} has no generated tool"
    assert set(mcp_server.OPERATOR_ALIASES) <= _names(mcp_server.mcp)


# -- A5 and A6: who calls, and what a refusal looks like -----------------------------------
def _transport_client(handler):
    def build() -> FicheroClient:
        return FicheroClient(base_url="http://test", library_path="/tmp/L.fichero", token="t",
                             transport=httpx.MockTransport(handler))
    return build


def test_a_refused_call_is_a_typed_tool_error_never_an_empty_result(monkeypatch):
    """WHY (openapi.mcp.errors-reach-the-agent): an agent told nothing when the engine said 422
    reports success. The refusal must reach it through the MCP protocol as an error result
    carrying the engine's status and detail."""
    def refuse(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "nothing to run: the recipe fails its check"})

    monkeypatch.setattr(mcp_server, "_mutating_client", _transport_client(refuse))
    handler = mcp_server.mcp._mcp_server.request_handlers[types.CallToolRequest]
    request = types.CallToolRequest(
        method="tools/call",
        params=types.CallToolRequestParams(name="fichero_recipes_start_project", arguments={}),
    )
    result = asyncio.run(handler(request)).root
    assert result.isError is True
    text = result.content[0].text
    payload = json.loads(text[text.index("{"):])
    assert payload == {
        "status": 422,
        "detail": "nothing to run: the recipe fails its check",
        "route": "POST /api/recipes/project/start",
    }


def test_an_unreachable_engine_is_a_typed_error_too(monkeypatch):
    """WHY: a connection failure has no status, and must still be an error, not None."""
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(mcp_server, "_client", _transport_client(refuse))
    with pytest.raises(openapi_runtime.EngineError) as excinfo:
        generated.fichero_hpc_list_clusters()
    assert excinfo.value.status is None and "Is the engine running" in str(excinfo.value.detail)
