"""`mcp.client.tools-survive-a-restart` (#5760): an enabled server's tools are loaded into the workflow tool registry
by the engine, when it starts and whenever a server is saved or deleted, with no button. WHY (2026-10-17 review):
only `POST /api/mcp-servers/tools/load-into-workflow-registry` loaded them and nothing called it, so every restart
lost the tools and the button that called it was mounted nowhere."""
from __future__ import annotations

import inspect
import time

import pytest

SERVER = {"name": "echoer", "transport": "stdio", "command": "python", "args": ["-m", "nothing"], "enabled": True}


@pytest.fixture
def loads(monkeypatch):
    """Counts the registry loads; no server is really started."""
    from fichero_server.workflows.tools import mcp

    calls: list[int] = []

    async def reload() -> int:
        calls.append(1)
        return 0

    monkeypatch.setattr(mcp, "reload_mcp_tools", reload)
    return calls


def _wait_for(calls, n, seconds=5.0):
    deadline = time.monotonic() + seconds
    while len(calls) < n and time.monotonic() < deadline:
        time.sleep(0.05)
    return len(calls)


def test_the_engine_loads_the_enabled_servers_tools_at_start(client, loads):
    from fichero_server.api.routes.mcp.servers import sync_mcp_tools
    from fichero_server.db.app import get_app_db
    from fichero_server.mcp.manager import get_mcp_manager
    from fichero_server.models import MCPServer

    get_app_db().save_mcp_server(MCPServer(name="startup-one", transport="stdio", command="python", args=[], enabled=True))
    get_app_db().save_mcp_server(MCPServer(name="startup-off", transport="stdio", command="python", args=[], enabled=False))
    import asyncio

    asyncio.run(sync_mcp_tools())
    names = {s.name for s in get_mcp_manager().list_servers()}
    assert "startup-one" in names and "startup-off" not in names
    assert loads, "the registry was never loaded"


def test_the_start_up_warm_calls_it():
    """The engine's own start (after it is ready, so a slow server never slows the launch) runs the sync."""
    from fichero_server.api import main

    source = inspect.getsource(main.lifespan)
    assert "sync_mcp_tools" in source


def test_saving_and_deleting_a_server_reloads_the_tools(client, loads):
    made = client.post("/api/mcp-servers", json=SERVER)
    assert made.status_code == 200, made.text
    assert _wait_for(loads, 1) >= 1, "creating a server did not reload the tools"
    server_id = made.json()["id"]
    before = len(loads)
    assert client.put(f"/api/mcp-servers/{server_id}", json={"enabled": False}).status_code == 200
    assert _wait_for(loads, before + 1) > before, "saving a server did not reload the tools"
    before = len(loads)
    assert client.delete(f"/api/mcp-servers/{server_id}").status_code == 200
    assert _wait_for(loads, before + 1) > before, "deleting a server did not reload the tools"
