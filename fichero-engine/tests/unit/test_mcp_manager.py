"""
Unit tests for MCP Manager.

Tests the MCPServerConfig and MCPManager classes without requiring actual MCP servers.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from contextlib import asynccontextmanager

from langchain_core.tools import BaseTool

from fichero.mcp.manager import (
    MCPServerConfig,
    MCPManager,
    get_mcp_manager,
)


# =============================================================================
# Test Data
# =============================================================================

def create_mock_tool(name: str, description: str = "") -> BaseTool:
    """Create a mock LangChain tool."""
    tool = Mock(spec=BaseTool)
    tool.name = name
    tool.description = description
    return tool


# =============================================================================
# MCPServerConfig Tests
# =============================================================================

class TestMCPServerConfig:
    """Test MCPServerConfig dataclass and connection conversion."""

    def test_stdio_config(self):
        """Test stdio transport configuration."""
        config = MCPServerConfig(
            name="test-server",
            transport="stdio",
            command="python",
            args=["-m", "mcp_server_time"],
            env={"KEY": "value"},
        )

        assert config.name == "test-server"
        assert config.transport == "stdio"
        assert config.command == "python"
        assert config.args == ["-m", "mcp_server_time"]
        assert config.env == {"KEY": "value"}
        assert config.tool_name_prefix is True
        assert config.enabled is True

    def test_sse_config(self):
        """Test SSE transport configuration."""
        config = MCPServerConfig(
            name="sse-server",
            transport="sse",
            url="http://localhost:8080/sse",
            headers={"Authorization": "Bearer token"},
        )

        assert config.name == "sse-server"
        assert config.transport == "sse"
        assert config.url == "http://localhost:8080/sse"
        assert config.headers == {"Authorization": "Bearer token"}

    def test_http_config(self):
        """Test HTTP transport configuration."""
        config = MCPServerConfig(
            name="http-server",
            transport="http",
            url="http://localhost:8080/api",
        )

        assert config.name == "http-server"
        assert config.transport == "http"
        assert config.url == "http://localhost:8080/api"

    def test_websocket_config(self):
        """Test WebSocket transport configuration."""
        config = MCPServerConfig(
            name="ws-server",
            transport="websocket",
            url="ws://localhost:8080/ws",
        )

        assert config.name == "ws-server"
        assert config.transport == "websocket"
        assert config.url == "ws://localhost:8080/ws"

    def test_to_connection_stdio(self):
        """Test stdio connection dictionary conversion."""
        config = MCPServerConfig(
            name="test",
            transport="stdio",
            command="python",
            args=["-m", "server"],
            env={"KEY": "value"},
        )

        conn = config.to_connection()
        assert conn["transport"] == "stdio"
        assert conn["command"] == "python"
        assert conn["args"] == ["-m", "server"]
        assert conn["env"] == {"KEY": "value"}

    def test_to_connection_sse(self):
        """Test SSE connection dictionary conversion."""
        config = MCPServerConfig(
            name="test",
            transport="sse",
            url="http://localhost:8080/sse",
            headers={"Auth": "token"},
        )

        conn = config.to_connection()
        assert conn["transport"] == "sse"
        assert conn["url"] == "http://localhost:8080/sse"
        assert conn["headers"] == {"Auth": "token"}

    def test_to_connection_http(self):
        """Test HTTP connection dictionary conversion."""
        config = MCPServerConfig(
            name="test",
            transport="http",
            url="http://localhost:8080",
        )

        conn = config.to_connection()
        assert conn["transport"] == "http"
        assert conn["url"] == "http://localhost:8080"
        assert conn["headers"] == {}

    def test_to_connection_websocket(self):
        """Test WebSocket connection dictionary conversion."""
        config = MCPServerConfig(
            name="test",
            transport="websocket",
            url="ws://localhost:8080",
        )

        conn = config.to_connection()
        assert conn["transport"] == "websocket"
        assert conn["url"] == "ws://localhost:8080"
        assert conn["headers"] == {}

    def test_to_connection_missing_command(self):
        """Test error when stdio transport missing command."""
        config = MCPServerConfig(
            name="test",
            transport="stdio",
        )

        with pytest.raises(ValueError, match="command required for stdio"):
            config.to_connection()

    def test_to_connection_rejects_disallowed_stdio_command(self):
        config = MCPServerConfig(
            name="shell",
            transport="stdio",
            command="/bin/sh",
            args=["-c", "echo exploited"],
        )

        with pytest.raises(ValueError, match="stdio command is not allowlisted"):
            config.to_connection()

    def test_to_connection_missing_url(self):
        """Test error when http transport missing url."""
        config = MCPServerConfig(
            name="test",
            transport="http",
        )

        with pytest.raises(ValueError, match="url required for HTTP"):
            config.to_connection()

    def test_to_connection_invalid_transport(self):
        """Test error for invalid transport type."""
        config = MCPServerConfig(
            name="test",
            transport="invalid",
        )

        with pytest.raises(ValueError, match="unknown transport"):
            config.to_connection()


# =============================================================================
# MCPManager Tests
# =============================================================================

class TestMCPManager:
    """Test MCPManager server management and tool loading."""

    def test_init(self):
        """Test manager initialization."""
        manager = MCPManager()
        assert manager.servers == {}
        assert manager._tool_cache == {}

    def test_add_server(self):
        """Test adding a server configuration."""
        manager = MCPManager()
        config = MCPServerConfig(
            name="test-server",
            transport="stdio",
            command="python",
        )

        manager.add_server(config)
        assert "test-server" in manager.servers
        assert manager.servers["test-server"] == config

    def test_add_server_clears_cache(self):
        """Test that adding a server clears its cache."""
        manager = MCPManager()
        config = MCPServerConfig(
            name="test-server",
            transport="stdio",
            command="python",
        )

        # Add server and populate cache
        manager.add_server(config)
        manager._tool_cache["test-server"] = [create_mock_tool("tool1")]

        # Re-add server should clear cache
        manager.add_server(config)
        assert "test-server" not in manager._tool_cache

    def test_remove_server(self):
        """Test removing a server configuration."""
        manager = MCPManager()
        config = MCPServerConfig(
            name="test-server",
            transport="stdio",
            command="python",
        )

        manager.add_server(config)
        manager._tool_cache["test-server"] = [create_mock_tool("tool1")]

        manager.remove_server("test-server")
        assert "test-server" not in manager.servers
        assert "test-server" not in manager._tool_cache

    def test_remove_nonexistent_server(self):
        """Test removing a server that doesn't exist."""
        manager = MCPManager()
        # Should not raise error
        manager.remove_server("nonexistent")

    def test_get_server(self):
        """Test getting a server configuration."""
        manager = MCPManager()
        config = MCPServerConfig(
            name="test-server",
            transport="stdio",
            command="python",
        )

        manager.add_server(config)
        result = manager.get_server("test-server")
        assert result == config

    def test_get_nonexistent_server(self):
        """Test getting a server that doesn't exist."""
        manager = MCPManager()
        result = manager.get_server("nonexistent")
        assert result is None

    def test_list_servers(self):
        """Test listing all servers."""
        manager = MCPManager()
        config1 = MCPServerConfig(name="server1", transport="stdio", command="python")
        config2 = MCPServerConfig(name="server2", transport="http", url="http://localhost")

        manager.add_server(config1)
        manager.add_server(config2)

        servers = manager.list_servers()
        assert len(servers) == 2
        assert config1 in servers
        assert config2 in servers

    def test_clear_cache_single_server(self):
        """Test clearing cache for a single server."""
        manager = MCPManager()
        manager._tool_cache["server1"] = [create_mock_tool("tool1")]
        manager._tool_cache["server2"] = [create_mock_tool("tool2")]

        manager.clear_cache("server1")
        assert "server1" not in manager._tool_cache
        assert "server2" in manager._tool_cache

    def test_clear_cache_all_servers(self):
        """Test clearing cache for all servers."""
        manager = MCPManager()
        manager._tool_cache["server1"] = [create_mock_tool("tool1")]
        manager._tool_cache["server2"] = [create_mock_tool("tool2")]

        manager.clear_cache()
        assert manager._tool_cache == {}

    def test_get_tool_names(self):
        """Test getting all cached tool names."""
        manager = MCPManager()
        manager._tool_cache["server1"] = [
            create_mock_tool("tool1"),
            create_mock_tool("tool2"),
        ]
        manager._tool_cache["server2"] = [
            create_mock_tool("tool3"),
        ]

        names = manager.get_tool_names()
        assert set(names) == {"tool1", "tool2", "tool3"}

    def test_get_tools_by_server(self):
        """Test getting tools for a specific server."""
        manager = MCPManager()
        tools = [create_mock_tool("tool1"), create_mock_tool("tool2")]
        manager._tool_cache["server1"] = tools

        result = manager.get_tools_by_server("server1")
        assert result == tools

    def test_get_tools_by_nonexistent_server(self):
        """Test getting tools for server with no cache."""
        manager = MCPManager()
        result = manager.get_tools_by_server("nonexistent")
        assert result == []

    @pytest.mark.asyncio
    async def test_load_server_tools(self):
        """Test loading tools from a server."""
        manager = MCPManager()
        config = MCPServerConfig(
            name="test-server",
            transport="stdio",
            command="python",
        )
        manager.add_server(config)

        # Mock create_session and load_mcp_tools
        mock_session = AsyncMock()
        mock_tools = [
            create_mock_tool("tool1", "Description 1"),
            create_mock_tool("tool2", "Description 2"),
        ]

        @asynccontextmanager
        async def mock_create_session(connection):
            yield mock_session

        with patch("fichero.mcp.manager.create_session", mock_create_session):
            with patch("fichero.mcp.manager.load_mcp_tools", return_value=mock_tools) as mock_load:
                tools = await manager.load_server_tools("test-server")

                # Verify tools returned
                assert len(tools) == 2
                assert tools[0].name == "tool1"
                assert tools[1].name == "tool2"

                # Verify load_mcp_tools called correctly
                mock_load.assert_called_once()
                call_kwargs = mock_load.call_args[1]
                assert call_kwargs["session"] == mock_session
                assert call_kwargs["server_name"] == "test-server"
                assert call_kwargs["tool_name_prefix"] is True

                # Verify cache populated
                assert "test-server" in manager._tool_cache
                assert manager._tool_cache["test-server"] == tools

    @pytest.mark.asyncio
    async def test_load_server_tools_cached(self):
        """Test loading tools from cache."""
        manager = MCPManager()
        config = MCPServerConfig(
            name="test-server",
            transport="stdio",
            command="python",
        )
        manager.add_server(config)

        # Pre-populate cache
        cached_tools = [create_mock_tool("cached_tool")]
        manager._tool_cache["test-server"] = cached_tools

        # Should return cached tools without calling MCP
        with patch("fichero.mcp.manager.create_session") as mock_create:
            tools = await manager.load_server_tools("test-server")

            assert tools == cached_tools
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_server_tools_force_reload(self):
        """Test force reloading tools bypasses cache."""
        manager = MCPManager()
        config = MCPServerConfig(
            name="test-server",
            transport="stdio",
            command="python",
        )
        manager.add_server(config)

        # Pre-populate cache
        cached_tools = [create_mock_tool("cached_tool")]
        manager._tool_cache["test-server"] = cached_tools

        # Mock new tools
        mock_session = AsyncMock()
        new_tools = [create_mock_tool("new_tool")]

        @asynccontextmanager
        async def mock_create_session(connection):
            yield mock_session

        with patch("fichero.mcp.manager.create_session", mock_create_session):
            with patch("fichero.mcp.manager.load_mcp_tools", return_value=new_tools):
                tools = await manager.load_server_tools("test-server", force_reload=True)

                # Should get new tools, not cached
                assert tools == new_tools
                assert manager._tool_cache["test-server"] == new_tools

    @pytest.mark.asyncio
    async def test_load_server_tools_disabled(self):
        """Test loading tools from disabled server returns empty."""
        manager = MCPManager()
        config = MCPServerConfig(
            name="test-server",
            transport="stdio",
            command="python",
            enabled=False,
        )
        manager.add_server(config)

        tools = await manager.load_server_tools("test-server")
        assert tools == []

    @pytest.mark.asyncio
    async def test_load_server_tools_not_found(self):
        """Test loading tools from nonexistent server raises error."""
        manager = MCPManager()

        with pytest.raises(ValueError, match="Server not found"):
            await manager.load_server_tools("nonexistent")

    @pytest.mark.asyncio
    async def test_load_all_tools(self):
        """Test loading tools from all enabled servers."""
        manager = MCPManager()

        # Add two enabled servers
        config1 = MCPServerConfig(name="server1", transport="stdio", command="python")
        config2 = MCPServerConfig(name="server2", transport="stdio", command="python")
        manager.add_server(config1)
        manager.add_server(config2)

        # Add one disabled server
        config3 = MCPServerConfig(name="server3", transport="stdio", command="python", enabled=False)
        manager.add_server(config3)

        # Mock tools
        mock_session = AsyncMock()
        tools1 = [create_mock_tool("tool1")]
        tools2 = [create_mock_tool("tool2")]

        @asynccontextmanager
        async def mock_create_session(connection):
            yield mock_session

        async def mock_load_mcp_tools(session, server_name, tool_name_prefix):
            if server_name == "server1":
                return tools1
            elif server_name == "server2":
                return tools2
            return []

        with patch("fichero.mcp.manager.create_session", mock_create_session):
            with patch("fichero.mcp.manager.load_mcp_tools", side_effect=mock_load_mcp_tools):
                all_tools = await manager.load_all_tools()

                # Should have tools from both enabled servers
                assert len(all_tools) == 2
                assert tools1[0] in all_tools
                assert tools2[0] in all_tools

    @pytest.mark.asyncio
    async def test_load_all_tools_error_handling(self):
        """Test that errors loading from one server don't stop others."""
        manager = MCPManager()

        config1 = MCPServerConfig(name="server1", transport="stdio", command="python")
        config2 = MCPServerConfig(name="server2", transport="stdio", command="python")
        manager.add_server(config1)
        manager.add_server(config2)

        # Mock tools
        mock_session = AsyncMock()
        tools2 = [create_mock_tool("tool2")]

        @asynccontextmanager
        async def mock_create_session(connection):
            yield mock_session

        async def mock_load_mcp_tools(session, server_name, tool_name_prefix):
            if server_name == "server1":
                raise Exception("Server 1 failed")
            elif server_name == "server2":
                return tools2
            return []

        with patch("fichero.mcp.manager.create_session", mock_create_session):
            with patch("fichero.mcp.manager.load_mcp_tools", side_effect=mock_load_mcp_tools):
                all_tools = await manager.load_all_tools()

                # Should still get tools from server2
                assert len(all_tools) == 1
                assert tools2[0] in all_tools


# =============================================================================
# Singleton Tests
# =============================================================================

class TestSingleton:
    """Test the singleton get_mcp_manager() function."""

    def test_get_mcp_manager_returns_same_instance(self):
        """Test that get_mcp_manager() returns the same instance."""
        # Clear global instance first
        import fichero.mcp.manager
        fichero.mcp.manager._mcp_manager = None

        manager1 = get_mcp_manager()
        manager2 = get_mcp_manager()

        assert manager1 is manager2

    def test_get_mcp_manager_loads_defaults(self):
        """Test that get_mcp_manager() loads default servers."""
        # Clear global instance first
        import fichero.mcp.manager
        fichero.mcp.manager._mcp_manager = None

        manager = get_mcp_manager()

        # Should have default servers loaded
        # DEFAULT_MCP_SERVERS has at least the time server
        servers = manager.list_servers()
        assert len(servers) > 0

        # Find the time server
        time_server = manager.get_server("time")
        assert time_server is not None
        assert time_server.transport == "stdio"
        assert time_server.command == "python"
        assert time_server.args == ["-m", "mcp_server_time"]
        assert time_server.enabled is False  # Disabled by default
