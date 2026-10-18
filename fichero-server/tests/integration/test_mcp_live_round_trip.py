"""`openapi.mcp.live-round-trip` (#4465): the real `fichero-mcp` over stdio against a seeded, running engine.

WHY: the MCP tests were in-process only, so nothing proved the installed launcher's server lists its tools and
answers a call over the wire against a real engine. The server is started as a child process, as a client would, and a
`ClientSession` lists the tools and calls `fichero_health`. The engine is the shared live one
(`_cli_live.cli_live_engine`: ephemeral port, its own HOME, auth off)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tests.integration._cli_live import cli_live_engine  # noqa: F401  (fixture)

mcp_client = pytest.importorskip("mcp.client.stdio")


@pytest.mark.asyncio
async def test_the_mcp_server_lists_its_tools_and_answers_health_from_a_live_engine(cli_live_engine):  # noqa: F811
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    repo = Path(__file__).resolve().parents[3]
    source = os.pathsep.join(str(repo / pkg / "src") for pkg in ("fichero-mcp", "fichero-cli", "fichero-server"))
    env = {**os.environ, "FICHERO_API_URL": cli_live_engine["base_url"], "FICHERO_UDS": "0",
           "PYTHONPATH": source + os.pathsep + os.environ.get("PYTHONPATH", "")}
    params = StdioServerParameters(command=sys.executable, args=["-m", "fichero_mcp.server"], env=env)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert "fichero_health" in names and len(names) > 50, sorted(names)[:10]
            answer = await session.call_tool("fichero_health", {})
            assert not answer.isError, answer
            assert "healthy" in str(answer.content).lower() or "status" in str(answer.content).lower(), answer.content
