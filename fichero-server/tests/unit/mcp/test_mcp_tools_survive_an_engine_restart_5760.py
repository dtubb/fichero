"""`mcp.client.tools-survive-a-restart` (#5760, owner 2026-10-26: fix the vanish-at-restart bug underneath, the palette flag stays
off): a saved, enabled external MCP server's tools are in the workflow registry after the engine starts again, with no button, and
its tool runs. The restart is real here: the registry and the MCP manager are emptied as a new process has them, the app's lifespan
runs, and the tools must come back from the saved server alone.
WHY: the load at start ran on a background task nothing waited for or checked; a test that never started the engine could not see it fail."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

ECHO = Path(__file__).with_name("_echo_mcp_server.py")


def _forget_everything_a_new_process_forgets():
    from fichero_server.mcp.manager import get_mcp_manager
    from fichero_server.workflows.registry import TOOL_DEFS, TOOLS

    for name in [n for n, d in TOOL_DEFS.items() if d.category.startswith("mcp")]:
        TOOL_DEFS.pop(name, None)
        TOOLS.pop(name, None)
    manager = get_mcp_manager()
    for server in list(manager.list_servers()):
        manager.remove_server(server.name)
    manager.clear_cache()


@pytest.fixture(autouse=True)
def _clean():
    _forget_everything_a_new_process_forgets()
    yield
    _forget_everything_a_new_process_forgets()


@pytest.mark.asyncio
async def test_a_saved_servers_tools_are_back_after_the_engine_starts_again(client, monkeypatch):
    monkeypatch.setenv("FICHERO_MCP_STDIO_ALLOWLIST", Path(sys.executable).name)
    made = client.post("/api/mcp-servers", json={"name": "echoer", "transport": "stdio", "command": sys.executable,
                                                  "args": [str(ECHO)], "enabled": True})
    assert made.status_code == 200, made.text
    _forget_everything_a_new_process_forgets()  # the engine stopped and started again: only the saved server is left

    from fastapi.testclient import TestClient

    from fichero_server.api.main import app
    from fichero_server.workflows.registry import TOOL_DEFS, TOOLS

    with TestClient(app):  # the lifespan runs: the engine starts
        deadline = time.monotonic() + 30
        while not any(d.category.startswith("mcp") for d in TOOL_DEFS.values()) and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
        name = next((n for n, d in TOOL_DEFS.items() if n.endswith("echo") and d.category.startswith("mcp")), None)
        assert name is not None, "the saved server's tools did not come back after the engine started"
        result = await TOOLS[name]({"input": {"text": "again"}}, {})
        assert "echo: again" in str(result.get("output")), result
