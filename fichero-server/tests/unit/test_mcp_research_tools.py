"""Coverage for research-agent MCP tool declarations."""

from fichero_server.mcp.research_tools import TOOLS


def test_research_mcp_create_tools_declare_parent_requirements():
    by_name = {tool.name: tool for tool in TOOLS}
    assert by_name["fichero_research_create_project"].inputSchema["required"] == ["name"]
    assert by_name["fichero_research_create_plan"].inputSchema["required"] == [
        "project_id", "name"
    ]
    assert by_name["fichero_research_create_task"].inputSchema["required"] == [
        "plan_id", "name"
    ]
    assert by_name["fichero_research_create_step"].inputSchema["required"] == [
        "task_id", "tool", "label"
    ]


def test_research_mcp_tool_names_and_descriptions_are_unique():
    names = [tool.name for tool in TOOLS]
    assert len(names) == len(set(names))
    assert all(name.startswith("fichero_research_") for name in names)
    assert all(tool.description for tool in TOOLS)
