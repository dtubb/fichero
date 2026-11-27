"""`mcp.client.tools-survive-a-restart` (#5760): an enabled server's tools reach the workflow registry
when the engine starts and whenever a server is saved or deleted, by the engine, with no button."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from fichero_server.mcp.manager import get_mcp_manager
from fichero_server.models import MCPServer


@pytest.fixture
def sync_spy(monkeypatch):
    from fichero_server.workflows.tools import mcp as tools_mcp

    spy = AsyncMock(return_value=0)
    monkeypatch.setattr(tools_mcp, "reload_mcp_tools", spy)
    return spy


@pytest.fixture(autouse=True)
def clean_manager():
    manager = get_mcp_manager()
    before = list(manager.list_servers())
    yield manager
    for config in list(manager.list_servers()):
        manager.remove_server(config.name)
    for config in before:
        manager.add_server(config)


def _save(app_db, name, enabled=True):
    server = MCPServer(name=name, transport="stdio", command="python", args=["-m", "x"], enabled=enabled)
    app_db.save_mcp_server(server)
    return server


@pytest.mark.asyncio
async def test_start_loads_every_enabled_server_and_only_those(app_db, sync_spy, clean_manager):
    from fichero_server.workflows.tools.mcp import sync_mcp_tools_from_db

    _save(app_db, "on")
    _save(app_db, "off", enabled=False)
    await sync_mcp_tools_from_db(app_db)

    assert [c.name for c in clean_manager.list_servers()] == ["on"]
    sync_spy.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_deleted_server_leaves_the_manager(app_db, sync_spy, clean_manager):
    from fichero_server.workflows.tools.mcp import sync_mcp_tools_from_db

    server = _save(app_db, "gone")
    await sync_mcp_tools_from_db(app_db)
    app_db.delete_mcp_server(server.id)
    await sync_mcp_tools_from_db(app_db)

    assert clean_manager.list_servers() == []
    assert sync_spy.await_count == 2


def test_saving_and_deleting_through_the_routes_reload(client, app_db, monkeypatch, sync_spy):
    monkeypatch.setattr("fichero_server.api.routes.mcp.servers.get_app_db", lambda: app_db)
    made = client.post("/api/mcp-servers", json={"name": "s", "transport": "stdio", "command": "python", "args": []})
    assert made.status_code == 200
    assert sync_spy.await_count == 1
    client.put(f"/api/mcp-servers/{made.json()['id']}", json={"enabled": False})
    assert sync_spy.await_count == 2
    client.delete(f"/api/mcp-servers/{made.json()['id']}")
    assert sync_spy.await_count == 3


def test_the_lifespan_starts_the_sync():
    source = (Path(__file__).parents[3] / "src/fichero_server/api/main.py").read_text()
    assert "sync_mcp_tools_from_db" in source


@pytest.mark.asyncio
async def test_the_start_sync_waits_for_ready_and_idle_and_for_the_warm_up(monkeypatch, caplog):
    """#7105: started as the lifespan yielded, the sync imported the tools package on the event loop and connected to
    every server while the app was launching. It runs after the readiness signal, the idle wait and the warm-up."""
    import asyncio
    import logging

    from fichero_server.api import main as api_main
    from fichero_server.workflows.tools import mcp as tools_mcp

    warmed_when_synced: list[bool] = []

    async def sync(app_db=None):
        warmed_when_synced.append(any("workflow tool stack warm-up complete" in r.message for r in caplog.records))
        return 0

    monkeypatch.setattr(tools_mcp, "sync_mcp_tools_from_db", sync)
    monkeypatch.setattr(api_main, "_WARM_IDLE_SECONDS", 0.01)
    caplog.set_level(logging.INFO, logger="fichero_server.api.main")

    async with api_main.lifespan(api_main.app):
        await asyncio.sleep(0.3)
        assert warmed_when_synced == [], "the MCP tools were loaded before the app was ready"
        api_main._mark_first_registry_200(api_main.app)
        for _ in range(1500):  # up to 30 s: the warm-up imports the tool stack first
            if warmed_when_synced:
                break
            await asyncio.sleep(0.02)

    assert warmed_when_synced == [True]
