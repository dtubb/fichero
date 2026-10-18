"""Tool registration and schema well-formedness for every MCP surface (#4227).

`fichero-mcp` ships ONE FastMCP surface, `fichero_mcp.server`, whose tools are generated from the contract
(`research.mcp-three-servers-not-collapsed`, #2896; the hand-kept `full`, `simple` and static catalogues are gone).

A malformed `inputSchema` is not a crash; an MCP client just silently refuses
to call the tool, or calls it with arguments the server cannot use. These tests
walk every registered tool on every surface and assert the schema is a usable
JSON-Schema object, that names are unique per surface, and that descriptions
exist (they are the only thing a model has to choose a tool by).
"""

from __future__ import annotations

import asyncio

import pytest

from fichero_mcp import server as mcp_server

FASTMCP_SURFACES = {"server": mcp_server}
SHIPPED_SURFACES = ("server",)


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


def test_server_tool_names_are_namespaced():
    """The full surface is loaded next to other MCP servers in one client."""
    unprefixed = [
        tool.name for tool in _tools(mcp_server) if not tool.name.startswith("fichero_")
    ]

    assert not unprefixed, f"unnamespaced tools on the fichero-mcp surface: {unprefixed}"
