"""Coverage for knowledge-graph MCP tool declarations."""

from fichero_server.mcp.kg_tools import TOOLS


def test_kg_mcp_tools_require_identifiers_for_mutations():
    by_name = {tool.name: tool for tool in TOOLS}
    assert by_name["fichero_kg_create_claim"].inputSchema["required"] == ["text"]
    assert by_name["fichero_kg_patch_claim"].inputSchema["required"] == ["claim_id"]
    assert by_name["fichero_kg_upsert_entity"].inputSchema["required"] == ["canonical_name"]


def test_kg_mcp_tool_names_are_unique_and_descriptions_present():
    names = [tool.name for tool in TOOLS]
    assert len(names) == len(set(names))
    assert all(tool.description for tool in TOOLS)
    assert all(name.startswith("fichero_") for name in names)
