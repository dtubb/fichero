"""Tool registration and schema well-formedness for every MCP surface (#4227).

`fichero-mcp` ships three FastMCP surfaces plus three static `types.Tool`
catalogues:

* `fichero_mcp.server` — the full `fichero-mcp` entry point
* `fichero_mcp.simple` — the small stable outside-agent contract
* `fichero_mcp.full`  — the wide surface
* `document_tools.TOOLS` / `kg_tools.TOOLS` / `research_tools.TOOLS` — declared
  tool schemas an MCP client sees verbatim

A malformed `inputSchema` is not a crash; an MCP client just silently refuses
to call the tool, or calls it with arguments the server cannot use. These tests
walk every registered tool on every surface and assert the schema is a usable
JSON-Schema object, that names are unique per surface, and that descriptions
exist (they are the only thing a model has to choose a tool by).
"""

from __future__ import annotations

import asyncio

import pytest

from fichero_mcp import document_tools, full as mcp_full, kg_tools
from fichero_mcp import research_tools, server as mcp_server, simple as mcp_simple

FASTMCP_SURFACES = {
    "server": mcp_server,
    "simple": mcp_simple,
    "full": mcp_full,
}
# The two surfaces with a console entry point in pyproject.toml (`fichero-mcp`
# and `fichero-mcp-simple`) — the ones an MCP client can actually launch.
# `fichero_mcp.full` has no entry point and, today, no tool descriptions at all
# (see agent-work/status/cli-mcp-test-wiring.md); holding it to the description
# contract would just be a red gate for a surface nothing launches.
SHIPPED_SURFACES = ("server", "simple")
STATIC_CATALOGUES = {
    "document_tools": document_tools,
    "kg_tools": kg_tools,
    "research_tools": research_tools,
}


def _tools(module) -> list:
    return asyncio.run(module.mcp.list_tools())


def _assert_schema_is_usable(schema, label: str) -> None:
    assert isinstance(schema, dict), f"{label}: inputSchema must be an object"
    assert schema.get("type") == "object", f"{label}: top-level type must be 'object'"
    properties = schema.get("properties")
    assert isinstance(properties, dict), f"{label}: properties must be an object"
    required = schema.get("required", [])
    assert isinstance(required, list), f"{label}: required must be a list"
    # A required name that is not declared in properties can never be satisfied
    # by a well-behaved client.
    missing = [name for name in required if name not in properties]
    assert not missing, f"{label}: required names not in properties: {missing}"
    for prop_name, prop_schema in properties.items():
        assert isinstance(
            prop_schema, dict
        ), f"{label}.{prop_name}: property schema must be an object"


@pytest.mark.parametrize("surface", sorted(FASTMCP_SURFACES))
def test_surface_registers_tools(surface):
    tools = _tools(FASTMCP_SURFACES[surface])

    assert tools, f"{surface} registered no tools"


@pytest.mark.parametrize("surface", sorted(FASTMCP_SURFACES))
def test_surface_tool_names_are_unique(surface):
    names = [tool.name for tool in _tools(FASTMCP_SURFACES[surface])]

    duplicates = {name for name in names if names.count(name) > 1}
    assert not duplicates, f"{surface} has duplicate tool names: {duplicates}"


@pytest.mark.parametrize("surface", SHIPPED_SURFACES)
def test_shipped_surface_tools_have_descriptions(surface):
    """A description is the only thing a model picks a tool by."""
    undescribed = [
        tool.name
        for tool in _tools(FASTMCP_SURFACES[surface])
        if not (tool.description or "").strip()
    ]

    assert not undescribed, f"{surface} tools without a description: {undescribed}"


@pytest.mark.parametrize("surface", sorted(FASTMCP_SURFACES))
def test_surface_tool_schemas_are_well_formed(surface):
    for tool in _tools(FASTMCP_SURFACES[surface]):
        _assert_schema_is_usable(tool.inputSchema, f"{surface}:{tool.name}")


@pytest.mark.parametrize("catalogue", sorted(STATIC_CATALOGUES))
def test_static_catalogue_schemas_are_well_formed(catalogue):
    tools = STATIC_CATALOGUES[catalogue].TOOLS

    assert tools, f"{catalogue}.TOOLS is empty"
    for tool in tools:
        assert tool.name.startswith("fichero_"), f"{catalogue}: {tool.name} unprefixed"
        assert (tool.description or "").strip(), f"{catalogue}: {tool.name} undescribed"
        _assert_schema_is_usable(tool.inputSchema, f"{catalogue}:{tool.name}")


@pytest.mark.parametrize("catalogue", sorted(STATIC_CATALOGUES))
def test_static_catalogue_names_are_unique(catalogue):
    names = [tool.name for tool in STATIC_CATALOGUES[catalogue].TOOLS]

    assert len(names) == len(set(names))


def test_server_surface_covers_the_documented_families():
    """The read + write families #1269 promises an agent, by name."""
    names = {tool.name for tool in _tools(mcp_server)}

    for expected in (
        "fichero_health",
        "fichero_docs_list",
        "fichero_docs_get",
        "fichero_search",
        "fichero_kg_search",
        "fichero_artifacts",
        "fichero_create_note",
    ):
        assert expected in names, f"{expected} missing from the fichero-mcp surface"


def test_simple_surface_stays_small_and_stable():
    """`fichero-mcp-simple` is a *contract*: a small, unprefixed tool set."""
    names = {tool.name for tool in _tools(mcp_simple)}

    assert names == {
        "health",
        "list_documents",
        "get_document",
        "run_workflow",
        "workflow_status",
        "list_artifacts",
        "kg_search",
        "kg_claims",
        "create_note",
        "list_notes",
    }


def test_server_tool_names_are_namespaced():
    """The full surface is loaded next to other MCP servers in one client."""
    unprefixed = [
        tool.name for tool in _tools(mcp_server) if not tool.name.startswith("fichero_")
    ]

    assert not unprefixed, f"unnamespaced tools on the fichero-mcp surface: {unprefixed}"
