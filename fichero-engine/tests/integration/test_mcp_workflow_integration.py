"""
Integration tests for MCP workflow execution.

Tests the complete flow:
1. MCP server configuration
2. Tool loading
3. Workflow registry integration
4. Workflow execution with MCP tools
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from langchain_core.tools import BaseTool

from fichero.workflows.builder import SystemicErrorDetected, build_graph
from fichero.workflows.types import (
    WorkflowDef,
    NodeDef,
    EdgeDef,
    PortDef,
    DataType,
    State,
)
from fichero.workflows.tools.mcp import load_mcp_tools_into_registry
from fichero.workflows.registry import TOOL_DEFS, TOOLS
from fichero.mcp.manager import MCPServerConfig, get_mcp_manager


# =============================================================================
# Test Helpers
# =============================================================================

def create_mock_mcp_tool(name: str, description: str = "", server_prefix: str = "test") -> BaseTool:
    """Create a mock MCP tool."""
    tool = Mock(spec=BaseTool)
    tool.name = f"{server_prefix}__{name}" if server_prefix else name
    tool.description = description or f"Mock MCP tool: {name}"

    # Mock the async invoke method
    async def mock_ainvoke(input_data):
        return f"MCP result: {input_data}"

    tool.ainvoke = mock_ainvoke
    return tool


# =============================================================================
# End-to-End Workflow Tests
# =============================================================================

class TestMCPWorkflowExecution:
    """Test executing workflows with MCP tools."""

    @pytest.mark.asyncio
    async def test_basic_mcp_workflow(self):
        """Test basic workflow with a single MCP tool."""
        # Create mock MCP tool
        mock_tool = create_mock_mcp_tool("echo", "Echo input", "test_server")

        # Mock MCP manager
        with patch("fichero.workflows.tools.mcp.get_mcp_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.load_all_tools = AsyncMock(return_value=[mock_tool])
            mock_get_manager.return_value = mock_manager

            # Clear existing MCP tools
            mcp_tools = [name for name in TOOL_DEFS if TOOL_DEFS[name].category.startswith("mcp")]
            for name in mcp_tools:
                if name in TOOL_DEFS:
                    del TOOL_DEFS[name]
                if name in TOOLS:
                    del TOOLS[name]

            # Load MCP tools into registry
            count = await load_mcp_tools_into_registry()
            assert count == 1
            assert "test_server__echo" in TOOL_DEFS

            # Create workflow with MCP tool
            workflow_def = WorkflowDef(
                id="test_mcp_workflow",
                name="Test MCP Workflow",
                nodes=[
                    NodeDef(
                        id="mcp_node",
                        tool="test_server__echo",
                        input_ports=[
                            PortDef(id="input", name="Input", port_type="input", data_type=DataType.ANY)
                        ],
                        output_ports=[
                            PortDef(id="output", name="Output", port_type="output", data_type=DataType.ANY)
                        ],
                        inputs={"input": "Hello from workflow!"},
                        config={},
                        position_x=0,
                        position_y=0,
                    ),
                ],
                edges=[],
                config={},
            )

            # Build and execute workflow
            app = build_graph(workflow_def)
            initial_state = State()
            config = {"configurable": {"thread_id": "test_mcp_1"}}

            final_state = await app.ainvoke(initial_state, config=config)

            # Verify MCP tool was executed
            assert "outputs" in final_state
            assert "mcp_node" in final_state["outputs"]
            assert "output" in final_state["outputs"]["mcp_node"]
            assert final_state["outputs"]["mcp_node"]["output"] == "MCP result: Hello from workflow!"

    @pytest.mark.asyncio
    async def test_mcp_workflow_with_error(self):
        """Test workflow with MCP tool that errors."""
        # Create mock MCP tool that raises error
        mock_tool = Mock(spec=BaseTool)
        mock_tool.name = "test_server__failing_tool"
        mock_tool.description = "Tool that fails"

        async def mock_ainvoke_error(input_data):
            raise ValueError("MCP tool failed")

        mock_tool.ainvoke = mock_ainvoke_error

        # Mock MCP manager
        with patch("fichero.workflows.tools.mcp.get_mcp_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.load_all_tools = AsyncMock(return_value=[mock_tool])
            mock_get_manager.return_value = mock_manager

            # Clear existing MCP tools
            mcp_tools = [name for name in TOOL_DEFS if TOOL_DEFS[name].category.startswith("mcp")]
            for name in mcp_tools:
                if name in TOOL_DEFS:
                    del TOOL_DEFS[name]
                if name in TOOLS:
                    del TOOLS[name]

            # Load MCP tools
            count = await load_mcp_tools_into_registry()
            assert count == 1

            # Create workflow with failing MCP tool
            workflow_def = WorkflowDef(
                id="test_failing_mcp",
                name="Test Failing MCP",
                nodes=[
                    NodeDef(
                        id="failing_node",
                        tool="test_server__failing_tool",
                        input_ports=[
                            PortDef(id="input", name="Input", port_type="input", data_type=DataType.ANY)
                        ],
                        output_ports=[
                            PortDef(id="output", name="Output", port_type="output", data_type=DataType.ANY)
                        ],
                        inputs={"input": "test"},
                        config={},
                        position_x=0,
                        position_y=0,
                    ),
                ],
                edges=[],
                config={},
            )

            # Build and execute workflow
            app = build_graph(workflow_def)
            initial_state = State()
            config = {"configurable": {"thread_id": "test_mcp_error"}}

            with pytest.raises(SystemicErrorDetected, match="MCP tool failed"):
                await app.ainvoke(initial_state, config=config)

    @pytest.mark.asyncio
    async def test_multiple_mcp_tools_in_workflow(self):
        """Test workflow with multiple independent MCP tools."""
        # Create two mock MCP tools
        mock_tool1 = create_mock_mcp_tool("uppercase", "Convert to uppercase", "text_server")
        mock_tool2 = create_mock_mcp_tool("reverse", "Reverse text", "text_server")

        # Make tool1 return uppercase
        async def mock_uppercase(input_data):
            return str(input_data).upper()

        # Make tool2 return reversed
        async def mock_reverse(input_data):
            return str(input_data)[::-1]

        mock_tool1.ainvoke = mock_uppercase
        mock_tool2.ainvoke = mock_reverse

        # Mock MCP manager
        with patch("fichero.workflows.tools.mcp.get_mcp_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.load_all_tools = AsyncMock(return_value=[mock_tool1, mock_tool2])
            mock_get_manager.return_value = mock_manager

            # Clear existing MCP tools
            mcp_tools = [name for name in TOOL_DEFS if TOOL_DEFS[name].category.startswith("mcp")]
            for name in mcp_tools:
                if name in TOOL_DEFS:
                    del TOOL_DEFS[name]
                if name in TOOLS:
                    del TOOLS[name]

            # Load MCP tools
            count = await load_mcp_tools_into_registry()
            assert count == 2

            # Create workflow with two MCP tools executing in sequence
            workflow_def = WorkflowDef(
                id="test_multiple_mcp",
                name="Test Multiple MCP",
                nodes=[
                    NodeDef(
                        id="uppercase_node",
                        tool="text_server__uppercase",
                        input_ports=[
                            PortDef(id="input", name="Input", port_type="input", data_type=DataType.ANY)
                        ],
                        output_ports=[
                            PortDef(id="output", name="Output", port_type="output", data_type=DataType.ANY)
                        ],
                        inputs={"input": "hello"},
                        config={},
                        position_x=0,
                        position_y=0,
                    ),
                    NodeDef(
                        id="reverse_node",
                        tool="text_server__reverse",
                        input_ports=[
                            PortDef(id="input", name="Input", port_type="input", data_type=DataType.ANY)
                        ],
                        output_ports=[
                            PortDef(id="output", name="Output", port_type="output", data_type=DataType.ANY)
                        ],
                        inputs={"input": "world"},
                        config={},
                        position_x=200,
                        position_y=0,
                    ),
                ],
                # Add edge so they execute sequentially (avoids concurrent update error)
                edges=[
                    EdgeDef(
                        id="edge1",
                        source="uppercase_node",
                        target="reverse_node",
                    ),
                ],
                config={},
            )

            # Build and execute workflow
            app = build_graph(workflow_def)
            initial_state = State()
            config = {"configurable": {"thread_id": "test_mcp_multiple"}}

            final_state = await app.ainvoke(initial_state, config=config)

            # Verify both tools executed independently
            assert "outputs" in final_state
            assert "uppercase_node" in final_state["outputs"]
            assert "reverse_node" in final_state["outputs"]

            # First tool output should be uppercase
            assert final_state["outputs"]["uppercase_node"]["output"] == "HELLO"

            # Second tool output should be reversed (HELLO -> OLLEH)
            assert final_state["outputs"]["reverse_node"]["output"] == "OLLEH"

    @pytest.mark.asyncio
    async def test_mcp_tool_with_complex_input(self):
        """Test MCP tool with complex dict input."""
        # Create mock MCP tool that accepts dict
        mock_tool = Mock(spec=BaseTool)
        mock_tool.name = "json_server__process_json"
        mock_tool.description = "Process JSON data"

        async def mock_process_json(input_data):
            # Return stringified dict
            if isinstance(input_data, dict):
                return f"Processed: {input_data.get('key', 'unknown')}"
            return f"Processed: {input_data}"

        mock_tool.ainvoke = mock_process_json

        # Mock MCP manager
        with patch("fichero.workflows.tools.mcp.get_mcp_manager") as mock_get_manager:
            mock_manager = Mock()
            mock_manager.load_all_tools = AsyncMock(return_value=[mock_tool])
            mock_get_manager.return_value = mock_manager

            # Clear existing MCP tools
            mcp_tools = [name for name in TOOL_DEFS if TOOL_DEFS[name].category.startswith("mcp")]
            for name in mcp_tools:
                if name in TOOL_DEFS:
                    del TOOL_DEFS[name]
                if name in TOOLS:
                    del TOOLS[name]

            # Load MCP tools
            count = await load_mcp_tools_into_registry()
            assert count == 1

            # Create workflow with dict input
            workflow_def = WorkflowDef(
                id="test_complex_input",
                name="Test Complex Input",
                nodes=[
                    NodeDef(
                        id="json_node",
                        tool="json_server__process_json",
                        input_ports=[
                            PortDef(id="input", name="Input", port_type="input", data_type=DataType.ANY)
                        ],
                        output_ports=[
                            PortDef(id="output", name="Output", port_type="output", data_type=DataType.ANY)
                        ],
                        inputs={"input": {"key": "test_value", "nested": {"data": 123}}},
                        config={},
                        position_x=0,
                        position_y=0,
                    ),
                ],
                edges=[],
                config={},
            )

            # Build and execute workflow
            app = build_graph(workflow_def)
            initial_state = State()
            config = {"configurable": {"thread_id": "test_complex"}}

            final_state = await app.ainvoke(initial_state, config=config)

            # Verify complex input was processed
            assert "outputs" in final_state
            assert "json_node" in final_state["outputs"]
            assert final_state["outputs"]["json_node"]["output"] == "Processed: test_value"


# =============================================================================
# MCP Server Configuration Tests
# =============================================================================

class TestMCPServerConfiguration:
    """Test MCP server configuration in workflow context."""

    def test_mcp_server_config_validation(self):
        """Test that MCP server configs are valid for workflow use."""
        # Create stdio config
        stdio_config = MCPServerConfig(
            name="test_stdio",
            transport="stdio",
            command="python",
            args=["-m", "mcp_server_time"],
            tool_name_prefix=True,
            enabled=True,
        )

        # Verify it can be converted to connection
        conn = stdio_config.to_connection()
        assert conn["transport"] == "stdio"
        assert conn["command"] == "python"

        # Create HTTP config
        http_config = MCPServerConfig(
            name="test_http",
            transport="http",
            url="http://localhost:8080/mcp",
            tool_name_prefix=True,
            enabled=True,
        )

        # Verify it can be converted
        conn = http_config.to_connection()
        assert conn["transport"] == "http"
        assert conn["url"] == "http://localhost:8080/mcp"

    @pytest.mark.asyncio
    async def test_mcp_manager_integration(self):
        """Test that MCP manager integrates with workflow system."""
        manager = get_mcp_manager()

        # Add a test server config
        config = MCPServerConfig(
            name="integration_test",
            transport="stdio",
            command="python",
            args=["-m", "test_server"],
            enabled=True,
        )
        manager.add_server(config)

        # Verify it's in the manager
        assert "integration_test" in manager.servers
        assert manager.get_server("integration_test") == config

        # Clean up
        manager.remove_server("integration_test")
