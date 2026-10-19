"""External MCP tools for the in-app chat agent (#5761, ruled 2026-10-18).

A server the owner has switched "available to chat" on (and left enabled) offers the chat agent its read-only tools,
those the server itself marks `readOnlyHint`. Every call goes through the audited action `mcp.call_tool`, so it leaves
an `ActionAudit` row and shows in Activity. A server that is off contributes nothing: the model is never shown its tools.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import BaseModel, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.db.app import get_app_db



def _read_only(tool: Any) -> bool:
    return bool((getattr(tool, "metadata", None) or {}).get("readOnlyHint"))


async def _chat_tools_by_server(unavailable: dict[str, str] | None = None) -> list[tuple[str, Any]]:
    """(server name, LangChain tool) for each read-only tool of each enabled, chat-available server.

    A server that will not start offers nothing and is named in `unavailable` (server -> error type), so the caller can say so.
    """
    servers = [s for s in get_app_db().query_mcp_servers() if s.enabled and s.available_to_chat]
    if not servers:
        return []  # nothing switched on: the MCP client is never even imported (#3950)
    from fichero_server.mcp.manager import get_mcp_manager

    manager = get_mcp_manager()
    found: list[tuple[str, Any]] = []
    for server in servers:
        if manager.get_server(server.name) is None:
            continue
        try:
            tools = await manager.load_server_tools(server.name)
        except Exception as exc:  # a server that will not start offers nothing; the turn goes on
            if unavailable is not None:
                unavailable[server.name] = type(exc).__name__
            continue
        found += [(server.name, tool) for tool in tools if _read_only(tool)]
    return found


async def chat_mcp_tools(unavailable: dict[str, str] | None = None) -> dict[str, tuple[str, Any]]:
    """tool name -> (server name, tool) for what the chat agent may be offered now."""
    return {tool.name: (name, tool) for name, tool in await _chat_tools_by_server(unavailable)}


def tool_definition(tool: Any) -> dict:
    """One OpenAI/LiteLLM function-tool definition for an MCP tool."""
    schema = tool.args_schema
    if not isinstance(schema, dict):
        schema = schema.model_json_schema() if schema is not None else {"type": "object", "properties": {}}
    return {"type": "function", "function": {
        "name": tool.name, "description": (tool.description or tool.name).strip().split("\n\n", 1)[0], "parameters": schema}}


class McpCallParams(BaseModel):
    """Call one read-only tool of an MCP server the owner made available to chat."""

    server: str = Field(description="the MCP server's name")
    tool: str = Field(description="the tool's name as the server's tool list gives it")
    arguments: dict = Field(default_factory=dict)


def _run(coro):
    # ponytail: the action layer is synchronous and the chat loop is already inside an event loop, so the call
    # runs on its own loop in a worker thread; it blocks the turn for the length of the call.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


@action("mcp.call_tool", McpCallParams, domains=["mcp"], read_only=True)
def _mcp_call_tool(_db, params: McpCallParams, _ctx: ActionContext):
    """Call one read-only tool of an MCP server the owner made available to chat."""
    offered = _run(chat_mcp_tools()).get(params.tool)  # a fresh view: a switch turned off a moment ago holds
    if offered is None or offered[0] != params.server:
        raise ValueError(f"'{params.tool}' is not a read-only tool of a server available to chat")
    _, tool = offered
    output = _run(tool.ainvoke(params.arguments))
    return {"output": output if isinstance(output, (str, int, float, bool, list, dict)) else str(output)}, ChangeSpec(
        domains=["mcp"], target_ids=[params.server])
