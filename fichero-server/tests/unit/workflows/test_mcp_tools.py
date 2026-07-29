"""
Unit tests for MCP tools integration with workflow registry.

Tests loading MCP tools and registering them in the workflow registry.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.tools import BaseTool

from fichero_server.workflows.tools.mcp import (
    load_mcp_tools_into_registry,
    _register_mcp_tool,
    get_mcp_tool_names,
    get_mcp_tools_by_server,
    reload_mcp_tools,
)
from fichero_server.workflows.registry import TOOL_DEFS, TOOLS
from fichero_server.workflows.types import State


# =============================================================================
# Test Helpers
# =============================================================================

def create_mock_mcp_tool(name: str, description: str = "", server_prefix: str = "test") -> BaseTool:
    """Create a mock MCP tool."""
    tool = Mock(spec=BaseTool)
    tool.name = f"{server_prefix}__{name}" if server_prefix else name
    tool.description = description or f"Description for {name}"

    # Mock the async invoke method
    async def mock_ainvoke(input_data):
        return f"Result from {name}: {input_data}"

    tool.ainvoke = mock_ainvoke
    return tool


# =============================================================================
# MCP Tool Registration Tests
# =============================================================================

class TestMCPToolRegistration:
    """Test registering individual MCP tools."""

    def test_register_mcp_tool_with_prefix(self):
        """Test registering an MCP tool with server prefix."""
        tool = create_mock_mcp_tool("get_time", "Get current time", "time")

        # Clear any existing registration
        tool_name = "time__get_time"
        if tool_name in TOOL_DEFS:
            del TOOL_DEFS[tool_name]
        if tool_name in TOOLS:
            del TOOLS[tool_name]

        # Register the tool
        _register_mcp_tool(tool)

        # Verify it's in TOOL_DEFS
        assert tool_name in TOOL_DEFS
        tool_def = TOOL_DEFS[tool_name]
        assert tool_def.name == tool_name
        assert tool_def.display_name == "Time Get Time"
        assert tool_def.description == "Get current time"
        assert tool_def.category == "mcp_time"
        assert tool_def.icon == "server.rack"
        assert tool_def.color == "teal"

        # Verify it has correct ports
        assert len(tool_def.input_ports) == 1
        assert tool_def.input_ports[0].id == "input"
        assert len(tool_def.output_ports) == 1
        assert tool_def.output_ports[0].id == "output"

        # Verify it's in TOOLS
        assert tool_name in TOOLS
        assert callable(TOOLS[tool_name])

    def test_register_mcp_tool_without_prefix(self):
        """Test registering an MCP tool without server prefix."""
        tool = create_mock_mcp_tool("custom_tool", "Custom tool", server_prefix="")
        tool.name = "custom_tool"  # No prefix

        # Clear any existing registration
        if "custom_tool" in TOOL_DEFS:
            del TOOL_DEFS["custom_tool"]
        if "custom_tool" in TOOLS:
            del TOOLS["custom_tool"]

        # Register the tool
        _register_mcp_tool(tool)

        # Verify it's registered with default category
        assert "custom_tool" in TOOL_DEFS
        assert TOOL_DEFS["custom_tool"].category == "mcp"

    @pytest.mark.asyncio
    async def test_mcp_tool_wrapper_execution(self):
        """Test that the registered tool wrapper executes correctly."""
        tool = create_mock_mcp_tool("echo", "Echo tool", "test")
        tool_name = "test__echo"

        # Clear any existing registration
        if tool_name in TOOL_DEFS:
            del TOOL_DEFS[tool_name]
        if tool_name in TOOLS:
            del TOOLS[tool_name]

        # Register the tool
        _register_mcp_tool(tool)

        # Get the wrapper function
        wrapper = TOOLS[tool_name]

        # Execute it
        state = State()
        inputs = {"input": "hello"}
        result = await wrapper(inputs, state)

        # Verify result
        assert "output" in result
        assert result["output"] == "Result from echo: hello"

    @pytest.mark.asyncio
    async def test_mcp_tool_wrapper_missing_input(self):
        """Test that the wrapper handles missing input."""
        tool = create_mock_mcp_tool("test_tool", server_prefix="test")
        tool_name = "test__test_tool"

        # Clear any existing registration
        if tool_name in TOOL_DEFS:
            del TOOL_DEFS[tool_name]
        if tool_name in TOOLS:
            del TOOLS[tool_name]

        # Register the tool
        _register_mcp_tool(tool)

        # Execute without input
        wrapper = TOOLS[tool_name]
        state = State()
        inputs = {}
        result = await wrapper(inputs, state)

        # Should return error
        assert "error" in result
        assert "No input provided" in result["error"]

    @pytest.mark.asyncio
    async def test_mcp_tool_wrapper_error_handling(self):
        """Test that the wrapper handles tool errors."""
        tool = Mock(spec=BaseTool)
        tool.name = "test__failing_tool"
        tool.description = "A tool that fails"

        # Mock tool that raises error
        async def mock_ainvoke_error(input_data):
            raise ValueError("Tool execution failed")

        tool.ainvoke = mock_ainvoke_error

        # Clear any existing registration
        if tool.name in TOOL_DEFS:
            del TOOL_DEFS[tool.name]
        if tool.name in TOOLS:
            del TOOLS[tool.name]

        # Register the tool
        _register_mcp_tool(tool)

        # Execute it
        wrapper = TOOLS[tool.name]
        state = State()
        inputs = {"input": "test"}
        result = await wrapper(inputs, state)

        # Should return error
        assert "error" in result
        assert "Tool execution failed" in result["error"]


# =============================================================================
# MCP Tool Loading Tests
# =============================================================================

class TestMCPToolLoading:
    """Test loading MCP tools into the workflow registry."""

    @pytest.mark.asyncio
    async def test_load_mcp_tools_into_registry(self):
        """Test loading all MCP tools from servers."""
        # Create mock tools
        mock_tools = [
            create_mock_mcp_tool("get_time", server_prefix="time"),
            create_mock_mcp_tool("convert_time", server_prefix="time"),
            create_mock_mcp_tool("custom_action", server_prefix="custom"),
        ]

        # Mock get_mcp_manager
        with patch("fichero_server.workflows.tools.mcp.get_mcp_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.load_all_tools = AsyncMock(return_value=mock_tools)
            mock_get_manager.return_value = mock_manager

            # Clear existing MCP tools
            mcp_tools = [name for name in TOOL_DEFS if TOOL_DEFS[name].category.startswith("mcp")]
            for name in mcp_tools:
                if name in TOOL_DEFS:
                    del TOOL_DEFS[name]
                if name in TOOLS:
                    del TOOLS[name]

            # Load tools
            count = await load_mcp_tools_into_registry()

            # Verify count
            assert count == 3

            # Verify tools are registered
            assert "time__get_time" in TOOL_DEFS
            assert "time__convert_time" in TOOL_DEFS
            assert "custom__custom_action" in TOOL_DEFS

            # Verify they're in TOOLS
            assert "time__get_time" in TOOLS
            assert "time__convert_time" in TOOLS
            assert "custom__custom_action" in TOOLS

    @pytest.mark.asyncio
    async def test_load_mcp_tools_error_handling(self):
        """Test that loading handles errors gracefully."""
        # Mock get_mcp_manager to raise error
        with patch("fichero_server.workflows.tools.mcp.get_mcp_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.load_all_tools = AsyncMock(side_effect=Exception("Connection failed"))
            mock_get_manager.return_value = mock_manager

            # Should return 0 and not raise
            count = await load_mcp_tools_into_registry()
            assert count == 0

    @pytest.mark.asyncio
    async def test_reload_mcp_tools(self):
        """Test reloading MCP tools clears and reloads."""
        # Register some initial MCP tools
        initial_tools = [
            create_mock_mcp_tool("old_tool", server_prefix="old"),
        ]
        for tool in initial_tools:
            _register_mcp_tool(tool)

        # Verify initial tool is registered
        assert "old__old_tool" in TOOL_DEFS

        # Create new mock tools
        new_tools = [
            create_mock_mcp_tool("new_tool", server_prefix="new"),
        ]

        # Mock get_mcp_manager
        with patch("fichero_server.workflows.tools.mcp.get_mcp_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.load_all_tools = AsyncMock(return_value=new_tools)
            mock_manager.clear_cache = Mock()
            mock_get_manager.return_value = mock_manager

            # Reload tools
            count = await reload_mcp_tools()

            # Verify count
            assert count == 1

            # Verify old tool is removed
            assert "old__old_tool" not in TOOL_DEFS
            assert "old__old_tool" not in TOOLS

            # Verify new tool is added
            assert "new__new_tool" in TOOL_DEFS
            assert "new__new_tool" in TOOLS

            # Verify cache was cleared
            mock_manager.clear_cache.assert_called_once()


# =============================================================================
# MCP Tool Query Tests
# =============================================================================

class TestMCPToolQueries:
    """Test querying MCP tools."""

    def test_get_mcp_tool_names(self):
        """Test getting all MCP tool names."""
        # Register some MCP tools
        tools = [
            create_mock_mcp_tool("tool1", server_prefix="server1"),
            create_mock_mcp_tool("tool2", server_prefix="server2"),
        ]
        for tool in tools:
            _register_mcp_tool(tool)

        # Get MCP tool names
        names = get_mcp_tool_names()

        # Should include our tools
        assert "server1__tool1" in names
        assert "server2__tool2" in names

    def test_get_mcp_tools_by_server(self):
        """Test getting MCP tools from a specific server."""
        # Register tools from different servers
        tools = [
            create_mock_mcp_tool("tool1", server_prefix="server1"),
            create_mock_mcp_tool("tool2", server_prefix="server1"),
            create_mock_mcp_tool("tool3", server_prefix="server2"),
        ]
        for tool in tools:
            _register_mcp_tool(tool)

        # Get tools from server1
        server1_tools = get_mcp_tools_by_server("server1")

        # Should only have server1 tools
        assert "server1__tool1" in server1_tools
        assert "server1__tool2" in server1_tools
        assert "server2__tool3" not in server1_tools

        # Get tools from server2
        server2_tools = get_mcp_tools_by_server("server2")

        # Should only have server2 tools
        assert "server2__tool3" in server2_tools
        assert "server1__tool1" not in server2_tools
