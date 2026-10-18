"""`mcp.client.round-trip-pinned` (#5760): a test connects to a REAL MCP server. WHY: `test_mcp_manager.py` only shapes
configs and `test_routes_mcp_servers.py` accepts a 500, so nothing proved that an external server's tools reach a
workflow and run. An in-process FastMCP server (one `echo` tool) is saved through `/api/mcp-servers`, its tools are
loaded into the workflow registry, and the tool runs through the registry's own wrapper."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ECHO = Path(__file__).with_name("_echo_mcp_server.py")


@pytest.fixture(autouse=True)
def _clean_registry():
    """The registry and the MCP manager are process-wide: leave neither holding this test's server."""
    from fichero_server.mcp.manager import get_mcp_manager
    from fichero_server.workflows.registry import TOOL_DEFS, TOOLS

    yield
    for name in [n for n, d in TOOL_DEFS.items() if d.category.startswith("mcp")]:
        TOOL_DEFS.pop(name, None)
        TOOLS.pop(name, None)
    manager = get_mcp_manager()
    for server in list(manager.list_servers()):
        manager.remove_server(server.name)
    manager.clear_cache()


@pytest.mark.asyncio
async def test_a_saved_stdio_server_reaches_the_registry_and_its_tool_runs(client, monkeypatch):
    monkeypatch.setenv("FICHERO_MCP_STDIO_ALLOWLIST", Path(sys.executable).name)
    made = client.post("/api/mcp-servers", json={"name": "echoer", "transport": "stdio", "command": sys.executable,
                                                  "args": [str(ECHO)], "enabled": True})
    assert made.status_code == 200, made.text

    loaded = client.post("/api/mcp-servers/tools/load-into-workflow-registry")
    assert loaded.status_code == 200, loaded.text

    from fichero_server.workflows.registry import TOOL_DEFS, TOOLS

    name = next((n for n in TOOL_DEFS if n.endswith("echo") and TOOL_DEFS[n].category.startswith("mcp")), None)
    assert name is not None, sorted(TOOL_DEFS)[-10:]
    result = await TOOLS[name]({"input": {"text": "hello"}}, {})
    assert "error" not in result, result
    assert "echo: hello" in str(result["output"])
