"""
Test Tool Registry Functionality

Tests for tool registration, discovery, and validation functions.
"""

import pytest
from fichero_server.workflows.registry import (
    register_tool,
    get_tool,
    get_tool_def,
    list_tools,
    list_tools_by_category,
    get_categories,
    create_node_from_tool,
)
from fichero_server.workflows.validation import (
    validate_port_connection,
    validate_node_connections,
    validate_workflow_connections,
    get_compatible_tools,
)
from fichero_server.workflows.types import (
    ToolDef,
    PortDef,
    NodeDef,
    EdgeDef,
    WorkflowDef,
    DataType,
    InputMapping,
)


class TestToolRegistration:
    """Test tool registration functionality."""

    def test_register_and_get_tool(self):
        """Test basic tool registration and retrieval."""
        # Create a simple test tool with proper ports
        @register_tool(
            name="test_tool",
            display_name="Test Tool",
            description="A test tool for validation",
            category="test",
            input_ports=[
                PortDef(
                    id="input",
                    name="Input",
                    port_type="input",
                    data_type=DataType.TEXT,
                    required=False  # Make it optional for testing
                )
            ],
            output_ports=[
                PortDef(
                    id="output",
                    name="Output",
                    port_type="output",
                    data_type=DataType.TEXT
                )
            ]
        )
        async def test_tool_function():
            return {"result": "success"}

        # Test retrieval
        tool_func = get_tool("test_tool")
        assert tool_func is not None
        assert tool_func.__name__ == "test_tool_function"

        # Test metadata retrieval
        tool_def = get_tool_def("test_tool")
        assert tool_def is not None
        assert tool_def.name == "test_tool"
        assert tool_def.display_name == "Test Tool"
        assert tool_def.category == "test"

    def test_list_tools(self):
        """Test listing all tools."""
        tools = list_tools()
        assert len(tools) > 0
        
        # Check that our test tool is in the list
        tool_names = [t.name for t in tools]
        assert "test_tool" in tool_names

    def test_list_tools_by_category(self):
        """Test listing tools by category."""
        test_tools = list_tools_by_category("test")
        assert len(test_tools) >= 1
        
        # Check that we get the right tool
        tool_names = [t.name for t in test_tools]
        assert "test_tool" in tool_names

    def test_get_categories(self):
        """Test getting all categories."""
        categories = get_categories()
        assert "test" in categories
        assert "vision" in categories  # Should have built-in tools


class TestNodeCreation:
    """Test node creation from tools."""

    def test_create_node_from_tool(self):
        """Test creating a node from a tool definition."""
        node = create_node_from_tool("test_tool", position_x=100, position_y=200)
        
        assert node is not None
        assert node.tool == "test_tool"
        assert node.position_x == 100
        assert node.position_y == 200
        assert node.id.startswith("test_tool_")
        assert node.label == "Test Tool"
        
        # Check that ports were copied
        assert len(node.input_ports) > 0
        assert len(node.output_ports) > 0

    def test_create_node_from_nonexistent_tool(self):
        """Test creating node from non-existent tool."""
        node = create_node_from_tool("nonexistent_tool")
        assert node is None


class TestPortValidation:
    """Test port connection validation."""

    def test_validate_compatible_connection(self):
        """Test validation of compatible port connection."""
        source_port = PortDef(
            id="output",
            name="Output",
            port_type="output",
            data_type=DataType.TEXT
        )
        
        target_port = PortDef(
            id="input",
            name="Input",
            port_type="input",
            data_type=DataType.TEXT
        )
        
        # Same types should be compatible
        assert validate_port_connection(source_port, target_port) is True

    def test_validate_any_type_connection(self):
        """Test validation with ANY data type."""
        source_port = PortDef(
            id="output",
            name="Output",
            port_type="output",
            data_type=DataType.ANY
        )
        
        target_port = PortDef(
            id="input",
            name="Input",
            port_type="input",
            data_type=DataType.TEXT
        )
        
        # ANY should be compatible with anything
        assert validate_port_connection(source_port, target_port) is True

    def test_validate_incompatible_connection(self):
        """Test validation of incompatible port connection."""
        source_port = PortDef(
            id="output",
            name="Output",
            port_type="output",
            data_type=DataType.FILES
        )
        
        target_port = PortDef(
            id="input",
            name="Input",
            port_type="input",
            data_type=DataType.NUMBER
        )
        
        # Different types should not be compatible
        assert validate_port_connection(source_port, target_port) is False

    def test_validate_files_to_file_connection(self):
        """Test validation of FILES to FILE connection."""
        source_port = PortDef(
            id="output",
            name="Output",
            port_type="output",
            data_type=DataType.FILES
        )
        
        target_port = PortDef(
            id="input",
            name="Input",
            port_type="input",
            data_type=DataType.FILE
        )
        
        # FILES should be compatible with FILE
        assert validate_port_connection(source_port, target_port) is True

    def test_validate_wrong_port_types(self):
        """Test validation with wrong port types."""
        source_port = PortDef(
            id="output",
            name="Output",
            port_type="input",  # Wrong type - should be output
            data_type=DataType.TEXT
        )
        
        target_port = PortDef(
            id="input",
            name="Input",
            port_type="input",
            data_type=DataType.TEXT
        )
        
        # Should fail because source is not an output port
        assert validate_port_connection(source_port, target_port) is False


class TestNodeValidation:
    """Test node connection validation."""

    def test_validate_node_with_required_input(self):
        """Test validation of node with required input."""
        # Create a tool with required input
        tool_def = ToolDef(
            name="required_input_tool",
            display_name="Required Input Tool",
            input_ports=[
                PortDef(
                    id="required_input",
                    name="Required Input",
                    port_type="input",
                    data_type=DataType.TEXT,
                    required=True
                )
            ],
            output_ports=[
                PortDef(
                    id="output",
                    name="Output",
                    port_type="output",
                    data_type=DataType.TEXT
                )
            ]
        )
        
        # Create node without mapping for required input
        node = NodeDef(
            id="test_node",
            tool="required_input_tool",
            input_ports=tool_def.input_ports,
            output_ports=tool_def.output_ports,
            input_mappings=[]  # No mappings
        )
        
        # Should fail validation
        errors = validate_node_connections(node, tool_def)
        assert len(errors) == 1
        assert "Required input port 'required_input'" in errors[0]

    def test_validate_node_with_optional_input(self):
        """Test validation of node with optional input."""
        # Create a tool with optional input
        tool_def = ToolDef(
            name="optional_input_tool",
            display_name="Optional Input Tool",
            input_ports=[
                PortDef(
                    id="optional_input",
                    name="Optional Input",
                    port_type="input",
                    data_type=DataType.TEXT,
                    required=False
                )
            ],
            output_ports=[
                PortDef(
                    id="output",
                    name="Output",
                    port_type="output",
                    data_type=DataType.TEXT
                )
            ]
        )
        
        # Create node without mapping for optional input
        node = NodeDef(
            id="test_node",
            tool="optional_input_tool",
            input_ports=tool_def.input_ports,
            output_ports=tool_def.output_ports,
            input_mappings=[]  # No mappings
        )
        
        # Should pass validation (no errors)
        errors = validate_node_connections(node, tool_def)
        assert len(errors) == 0

    def test_validate_node_with_invalid_mapping(self):
        """Test validation of node with invalid port mapping."""
        tool_def = ToolDef(
            name="mapping_tool",
            display_name="Mapping Tool",
            input_ports=[
                PortDef(
                    id="valid_input",
                    name="Valid Input",
                    port_type="input",
                    data_type=DataType.TEXT,
                    required=False  # Make it optional to avoid the required input error
                )
            ],
            output_ports=[]
        )
        
        # Create node with mapping to non-existent port
        node = NodeDef(
            id="test_node",
            tool="mapping_tool",
            input_ports=tool_def.input_ports,
            output_ports=tool_def.output_ports,
            input_mappings=[
                InputMapping(
                    port_id="nonexistent_port",
                    source_path="$.nodes.prev.output"
                )
            ]
        )
        
        # Should fail validation
        errors = validate_node_connections(node, tool_def)
        assert len(errors) == 1
        assert "Input mapping references unknown port 'nonexistent_port'" in errors[0]


class TestWorkflowValidation:
    """Test workflow connection validation.

    Note: These tests use real tools from the registry since ports are now
    fetched from the registry at validation time (not stored on nodes).
    """

    def test_validate_simple_workflow(self):
        """Test validation of a simple valid workflow."""
        from fichero_server.workflows.types import InputMapping

        # Create a simple workflow with two connected nodes using real tools
        # files -> transcribe: files output connects to files input
        workflow = WorkflowDef(
            id="test_workflow",
            name="Test Workflow",
            nodes=[
                NodeDef(
                    id="node1",
                    tool="files",  # Real tool: outputs files
                ),
                NodeDef(
                    id="node2",
                    tool="transcribe",  # Real tool: takes files input
                    # Add input mapping so validation passes
                    input_mappings=[
                        InputMapping(
                            port_id="files",
                            source_path="$.nodes.node1.files"
                        )
                    ]
                )
            ],
            edges=[
                EdgeDef(
                    source="node1",
                    target="node2",
                    source_port="files",  # files tool output port
                    target_port="files"   # transcribe tool input port
                )
            ]
        )

        # Should be valid - ports are fetched from registry
        errors = validate_workflow_connections(workflow)
        assert len(errors) == 0, f"Unexpected errors: {errors}"

    def test_validate_workflow_with_invalid_edge(self):
        """Test validation of workflow with invalid edge (type mismatch)."""
        # Use inline ports for this test to test type compatibility validation
        # Use a unique tool name that won't be in the registry
        workflow = WorkflowDef(
            id="test_workflow",
            name="Test Workflow",
            nodes=[
                NodeDef(
                    id="node1",
                    tool="_nonexistent_type_test_tool",
                    input_ports=[],
                    output_ports=[
                        PortDef(
                            id="output",
                            name="Output",
                            port_type="output",
                            data_type=DataType.TEXT
                        )
                    ]
                ),
                NodeDef(
                    id="node2",
                    tool="_nonexistent_type_test_tool",
                    input_ports=[
                        PortDef(
                            id="input",
                            name="Input",
                            port_type="input",
                            data_type=DataType.NUMBER  # Wrong type!
                        )
                    ],
                    output_ports=[]
                )
            ],
            edges=[
                EdgeDef(
                    source="node1",
                    target="node2",
                    source_port="output",
                    target_port="input"
                )
            ]
        )

        # Should fail due to incompatible types (plus unknown tool warnings)
        errors = validate_workflow_connections(workflow)
        # Filter to just the type compatibility error
        type_errors = [e for e in errors if "Invalid connection" in e]
        assert len(type_errors) == 1
        assert "Invalid connection" in type_errors[0]

    def test_validate_workflow_with_missing_node(self):
        """Test validation of workflow with missing node reference."""
        # Use a real tool to avoid unknown tool errors
        workflow = WorkflowDef(
            id="test_workflow",
            name="Test Workflow",
            nodes=[
                NodeDef(
                    id="node1",
                    tool="files",  # Real tool
                )
            ],
            edges=[
                EdgeDef(
                    source="node1",
                    target="nonexistent_node",  # This node doesn't exist
                    source_port="files",
                    target_port="input"
                )
            ]
        )

        # Should fail due to missing node
        errors = validate_workflow_connections(workflow)
        missing_node_errors = [e for e in errors if "unknown target node" in e]
        assert len(missing_node_errors) == 1
        assert "Edge references unknown target node" in missing_node_errors[0]


class TestCompatibleTools:
    """Test finding compatible tools."""

    def test_get_compatible_tools_for_text_input(self):
        """Test finding tools compatible with text input."""
        target_port = PortDef(
            id="text_input",
            name="Text Input",
            port_type="input",
            data_type=DataType.TEXT
        )
        
        compatible_tools = get_compatible_tools(target_port)
        
        # Should find tools that output text
        assert len(compatible_tools) > 0
        
        # Check that all returned tools have compatible outputs
        for tool in compatible_tools:
            has_compatible_output = any(
                p.port_type == "output" and 
                (p.data_type == DataType.TEXT or p.data_type == DataType.ANY)
                for p in tool.output_ports
            )
            assert has_compatible_output is True

    def test_get_compatible_tools_for_files_input(self):
        """Test finding tools compatible with files input."""
        target_port = PortDef(
            id="files_input",
            name="Files Input",
            port_type="input",
            data_type=DataType.FILES
        )
        
        compatible_tools = get_compatible_tools(target_port)
        
        # Should find tools that output files
        assert len(compatible_tools) > 0
        
        # Check that all returned tools have compatible outputs
        for tool in compatible_tools:
            has_compatible_output = any(
                p.port_type == "output" and 
                (p.data_type == DataType.FILES or p.data_type == DataType.ANY)
                for p in tool.output_ports
            )
            assert has_compatible_output is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])