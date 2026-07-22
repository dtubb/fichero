"""
MCP (Model Context Protocol) Manager

Manages connections to MCP servers and loads tools for use in workflows.
Supports stdio, HTTP, SSE, and WebSocket transports.
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import TYPE_CHECKING, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

# langchain_core / langchain_mcp_adapters / mcp are heavy imports (~250ms of
# cold-import time via langchain_core) and this module is pulled onto the API
# bind path by routes.mcp for OpenAPI schema generation. Every name below is
# used ONLY in annotations here (evaluated lazily thanks to
# `from __future__ import annotations`), so keep them behind TYPE_CHECKING and
# import the runtime helpers (`create_session`, `load_mcp_tools`) locally inside
# the methods that actually call them (startup speedup, #4038).
if TYPE_CHECKING:
    from langchain_core.tools import BaseTool
    from langchain_mcp_adapters.sessions import (
        StdioConnection,
        SSEConnection,
        StreamableHttpConnection,
        WebsocketConnection,
    )
    from mcp.client.session import ClientSession

logger = logging.getLogger(__name__)

_DEFAULT_STDIO_COMMAND_ALLOWLIST = frozenset(
    {
        "python",
        "python3",
        "node",
        "npx",
        "uv",
        "uvx",
        "bun",
        "deno",
    }
)


def _allowed_stdio_commands() -> set[str]:
    configured = os.getenv("FICHERO_MCP_STDIO_ALLOWLIST", "")
    commands = set(_DEFAULT_STDIO_COMMAND_ALLOWLIST)
    commands.update(part.strip() for part in configured.split(",") if part.strip())
    return commands


def _is_stdio_command_allowed(command: str) -> bool:
    basename = Path(command).name
    allowed = _allowed_stdio_commands()
    if command in allowed or basename in allowed:
        return True
    resolved = shutil.which(command)
    return bool(resolved and (resolved in allowed or Path(resolved).name in allowed))


# =============================================================================
# Server Configuration
# =============================================================================


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server connection.

    Supports multiple transport types:
    - stdio: Launch a subprocess (e.g., "npx @modelcontextprotocol/server-time")
    - sse: Server-Sent Events over HTTP
    - http: HTTP/REST API
    - websocket: WebSocket connection
    """

    name: str  # Unique server name
    transport: str  # "stdio", "sse", "http", or "websocket"

    # Transport-specific parameters
    command: str | None = None  # For stdio: command to launch server
    args: list[str] | None = None  # For stdio: command arguments
    env: dict[str, str] | None = None  # For stdio: environment variables
    url: str | None = None  # For http/sse/websocket: server URL
    headers: dict[str, str] | None = None  # For http/sse/websocket: HTTP headers

    # Tool configuration
    tool_name_prefix: bool = True  # Prefix tool names with server name
    enabled: bool = True  # Server enabled/disabled

    def to_connection(
        self,
    ) -> (
        StdioConnection | SSEConnection | StreamableHttpConnection | WebsocketConnection
    ):
        """Convert config to a connection dictionary (TypedDict)."""
        if self.transport == "stdio":
            if not self.command:
                raise ValueError(
                    f"Server {self.name}: command required for stdio transport"
                )
            if not _is_stdio_command_allowed(self.command):
                raise ValueError(
                    f"Server {self.name}: stdio command is not allowlisted: {self.command}"
                )
            return {
                "transport": "stdio",
                "command": self.command,
                "args": self.args or [],
                "env": self.env or {},
            }
        elif self.transport == "sse":
            if not self.url:
                raise ValueError(f"Server {self.name}: url required for SSE transport")
            return {
                "transport": "sse",
                "url": self.url,
                "headers": self.headers or {},
            }
        elif self.transport == "http":
            if not self.url:
                raise ValueError(f"Server {self.name}: url required for HTTP transport")
            return {
                "transport": "http",
                "url": self.url,
                "headers": self.headers or {},
            }
        elif self.transport == "websocket":
            if not self.url:
                raise ValueError(
                    f"Server {self.name}: url required for WebSocket transport"
                )
            return {
                "transport": "websocket",
                "url": self.url,
                "headers": self.headers or {},
            }
        else:
            raise ValueError(
                f"Server {self.name}: unknown transport '{self.transport}'"
            )


# =============================================================================
# MCP Manager
# =============================================================================


class MCPManager:
    """Manages MCP server connections and tool loading.

    Usage:
        # Create manager
        manager = MCPManager()

        # Add server configuration
        manager.add_server(MCPServerConfig(
            name="time",
            transport="stdio",
            command="python",
            args=["-m", "mcp_server_time"],
        ))

        # Load tools from all servers
        tools = await manager.load_all_tools()

        # Use tools in workflow
        for tool in tools:
            print(f"Tool: {tool.name}")
    """

    def __init__(self):
        """Initialize MCP manager."""
        self.servers: dict[str, MCPServerConfig] = {}
        self._tool_cache: dict[str, list[BaseTool]] = {}

    def add_server(self, config: MCPServerConfig) -> None:
        """Add or update a server configuration.

        Args:
            config: Server configuration
        """
        self.servers[config.name] = config
        # Clear cache for this server
        if config.name in self._tool_cache:
            del self._tool_cache[config.name]
        logger.info(f"Added MCP server: {config.name} (transport: {config.transport})")

    def remove_server(self, name: str) -> None:
        """Remove a server configuration.

        Args:
            name: Server name
        """
        if name in self.servers:
            del self.servers[name]
            if name in self._tool_cache:
                del self._tool_cache[name]
            logger.info(f"Removed MCP server: {name}")

    def get_server(self, name: str) -> MCPServerConfig | None:
        """Get server configuration by name.

        Args:
            name: Server name

        Returns:
            Server configuration or None if not found
        """
        return self.servers.get(name)

    def list_servers(self) -> list[MCPServerConfig]:
        """List all configured servers.

        Returns:
            List of server configurations
        """
        return list(self.servers.values())

    @asynccontextmanager
    async def _connect_server(
        self, config: MCPServerConfig
    ) -> AsyncIterator[ClientSession]:
        """Connect to an MCP server.

        Args:
            config: Server configuration

        Yields:
            Client session
        """
        from langchain_mcp_adapters.sessions import create_session  # noqa: PLC0415

        logger.info(f"Connecting to MCP server: {config.name}")
        connection = config.to_connection()

        async with create_session(connection) as session:
            logger.info(f"Connected to MCP server: {config.name}")
            yield session

    async def load_server_tools(
        self, server_name: str, force_reload: bool = False
    ) -> list[BaseTool]:
        """Load tools from a specific server.

        Args:
            server_name: Name of the server
            force_reload: Force reload tools even if cached

        Returns:
            List of LangChain tools

        Raises:
            ValueError: If server not found
        """
        config = self.servers.get(server_name)
        if not config:
            raise ValueError(f"Server not found: {server_name}")

        if not config.enabled:
            logger.info(f"Server {server_name} is disabled, skipping")
            return []

        # Check cache
        if not force_reload and server_name in self._tool_cache:
            logger.info(f"Using cached tools for server: {server_name}")
            return self._tool_cache[server_name]

        from langchain_mcp_adapters.tools import load_mcp_tools  # noqa: PLC0415

        # Connect and load tools
        async with self._connect_server(config) as session:
            tools = await load_mcp_tools(
                session=session,
                server_name=config.name,
                tool_name_prefix=config.tool_name_prefix,
            )

            logger.info(f"Loaded {len(tools)} tools from server: {server_name}")

            # Cache tools
            self._tool_cache[server_name] = tools

            return tools

    async def load_all_tools(self, force_reload: bool = False) -> list[BaseTool]:
        """Load tools from all enabled servers.

        Args:
            force_reload: Force reload tools even if cached

        Returns:
            List of all LangChain tools from all servers
        """
        all_tools = []

        for server_name in self.servers:
            try:
                tools = await self.load_server_tools(
                    server_name, force_reload=force_reload
                )
                all_tools.extend(tools)
            except Exception as e:
                logger.error(f"Failed to load tools from server {server_name}: {e}")

        logger.info(
            f"Loaded total {len(all_tools)} tools from {len(self.servers)} servers"
        )
        return all_tools

    def clear_cache(self, server_name: str | None = None) -> None:
        """Clear tool cache.

        Args:
            server_name: Server name to clear cache for, or None to clear all
        """
        if server_name:
            if server_name in self._tool_cache:
                del self._tool_cache[server_name]
                logger.info(f"Cleared cache for server: {server_name}")
        else:
            self._tool_cache.clear()
            logger.info("Cleared all tool caches")

    def get_tool_names(self) -> list[str]:
        """Get names of all cached tools.

        Returns:
            List of tool names
        """
        tool_names = []
        for tools in self._tool_cache.values():
            tool_names.extend([tool.name for tool in tools])
        return tool_names

    def get_tools_by_server(self, server_name: str) -> list[BaseTool]:
        """Get cached tools from a specific server.

        Args:
            server_name: Server name

        Returns:
            List of tools or empty list if not cached
        """
        return self._tool_cache.get(server_name, [])


# =============================================================================
# Default MCP Servers
# =============================================================================

DEFAULT_MCP_SERVERS = [
    MCPServerConfig(
        name="time",
        transport="stdio",
        command="python",
        args=["-m", "mcp_server_time"],
        tool_name_prefix=True,
        enabled=False,  # Disabled by default - user can enable
    ),
    # Add more default servers here as needed
]


# =============================================================================
# Singleton Instance
# =============================================================================

# Global MCP manager instance
_mcp_manager: MCPManager | None = None


def get_mcp_manager() -> MCPManager:
    """Get or create the global MCP manager instance.

    Returns:
        Global MCPManager instance
    """
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
        # Add default servers
        for server_config in DEFAULT_MCP_SERVERS:
            _mcp_manager.add_server(server_config)
    return _mcp_manager
