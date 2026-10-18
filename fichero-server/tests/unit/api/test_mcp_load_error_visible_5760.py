"""A failed load of the saved MCP servers' tools is visible on GET /api/mcp-servers, not only a log line (#5760).

The engine keeps starting and a save keeps succeeding; the error is stored and shown on every enabled server
until a later load works.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fichero_server.api.routes.mcp import servers
from fichero_server.models import MCPServer
from fichero_server.workflows.tools import mcp as mcp_tools


def _server(enabled: bool) -> MCPServer:
    now = datetime.now(UTC)
    return MCPServer(id="s1", name="bad", description="", transport="stdio", command="nope", args=[], env={},
                     url=None, headers={}, tool_name_prefix=False, enabled=enabled, created_at=now, updated_at=now)


@pytest.fixture(autouse=True)
def _clean():
    mcp_tools.note_load_result(None)
    yield
    mcp_tools.note_load_result(None)


async def test_a_bad_server_error_shows_on_the_list(monkeypatch):
    async def boom(_db=None):
        raise RuntimeError("server 'bad' would not start")

    monkeypatch.setattr(mcp_tools, "sync_mcp_tools_from_db", boom)
    monkeypatch.setattr(servers, "get_app_db", lambda: object())

    await servers._resync_registry()  # the save that asked still succeeds: nothing raises

    assert servers._server_to_response(_server(True)).last_load_error == "RuntimeError: server 'bad' would not start"
    assert servers._server_to_response(_server(False)).last_load_error is None


async def test_a_load_that_works_clears_the_error(monkeypatch):
    mcp_tools.note_load_result(RuntimeError("old"))

    async def ok(_db=None):
        return 0

    monkeypatch.setattr(mcp_tools, "sync_mcp_tools_from_db", ok)
    monkeypatch.setattr(servers, "get_app_db", lambda: object())

    await servers._resync_registry()

    assert servers._server_to_response(_server(True)).last_load_error is None
