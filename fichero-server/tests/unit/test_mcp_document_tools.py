"""Coverage for document/workflow MCP tool declarations."""

from fichero_server.mcp.document_tools import TOOLS


def test_document_mcp_tools_expose_required_inputs():
    by_name = {tool.name: tool for tool in TOOLS}
    assert by_name["fichero_search_documents"].inputSchema["required"] == ["query"]
    assert by_name["fichero_get_document"].inputSchema["required"] == ["document_id"]
    assert by_name["fichero_create_batch"].inputSchema["required"] == [
        "workflow_id", "file_paths"
    ]
    assert by_name["fichero_health"].inputSchema["properties"] == {}


def test_mcp_tool_names_are_unique_and_descriptive():
    names = [tool.name for tool in TOOLS]
    assert len(names) == len(set(names))
    assert all(name.startswith("fichero_") for name in names)
