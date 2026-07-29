#!/usr/bin/env python3
"""
Comprehensive tests for workflow CRUD operations.
"""
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero_server.models import Workflow
from fichero_server.workflows.types import WorkflowDef, NodeDef, EdgeDef


def test_workflow_model_crud():
    """Test basic CRUD operations on the Workflow model."""
    print("Testing Workflow model CRUD operations...")

    try:
        # Create a new workflow
        workflow = Workflow(
            name="Test CRUD Workflow",
            description="A workflow for testing CRUD operations",
            format="nodes",
            provider="openai",
            model="gpt-4o",
            nodes=[
                {
                    "id": "node1",
                    "tool": "transcribe",
                    "position_x": 100,
                    "position_y": 200,
                    "label": "Transcribe Audio"
                },
                {
                    "id": "node2",
                    "tool": "summarize",
                    "position_x": 300,
                    "position_y": 200,
                    "label": "Summarize Text"
                }
            ],
            edges=[
                {
                    "source": "node1",
                    "target": "node2",
                    "source_port": "text",
                    "target_port": "input"
                }
            ]
        )

        # Test creation - check that required fields are set
        assert workflow.id is not None, "Workflow should have an ID after creation"
        assert workflow.name == "Test CRUD Workflow", "Workflow name should match"
        assert workflow.format == "nodes", "Workflow format should be 'nodes'"
        assert len(workflow.nodes) == 2, "Should have 2 nodes"
        assert len(workflow.edges) == 1, "Should have 1 edge"
        print("✅ Workflow creation works correctly")

        # Test reading fields
        assert workflow.provider == "openai", "Provider should be accessible"
        assert workflow.model == "gpt-4o", "Model should be accessible"
        print("✅ Workflow field access works correctly")

        # Test updating fields
        workflow.name = "Updated Test Workflow"
        workflow.description = "Updated description for testing"
        assert workflow.name == "Updated Test Workflow", "Name update should work"
        assert workflow.description == "Updated description for testing", "Description update should work"
        print("✅ Workflow updates work correctly")

        # Test validation
        empty_workflow = Workflow(name="Empty", description="Empty workflow")
        assert len(empty_workflow.nodes) == 0, "Empty workflow should have no nodes"
        assert len(empty_workflow.edges) == 0, "Empty workflow should have no edges"
        print("✅ Workflow validation works correctly")

        print("✅ All Workflow model CRUD operations work correctly")

    except Exception as e:
        print(f"❌ Failed Workflow model CRUD test: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_workflow_types_crud():
    """Test CRUD operations with WorkflowDef types."""
    print("\nTesting WorkflowDef types CRUD operations...")

    try:
        # Test creating a workflow definition
        node1 = NodeDef(
            id="node1",
            tool="transcribe",
            label="Transcribe Audio",
            position_x=100,
            position_y=200
        )

        node2 = NodeDef(
            id="node2",
            tool="summarize",
            label="Summarize Text",
            position_x=300,
            position_y=200
        )

        edge = EdgeDef(
            source="node1",
            target="node2",
            source_port="text",
            target_port="input"
        )

        workflow_def = WorkflowDef(
            id="test-workflow-def",
            name="Test Workflow Definition",
            description="A test workflow definition",
            provider="openai",
            model="gpt-4o",
            nodes=[node1, node2],
            edges=[edge]
        )

        # Test reading properties
        assert workflow_def.id == "test-workflow-def", "ID should match"
        assert workflow_def.name == "Test Workflow Definition", "Name should match"
        assert len(workflow_def.nodes) == 2, "Should have 2 nodes"
        assert len(workflow_def.edges) == 1, "Should have 1 edge"
        print("✅ WorkflowDef creation works correctly")

        # Test finding entry/exit nodes
        entry_nodes = workflow_def.get_entry_nodes()
        exit_nodes = workflow_def.get_exit_nodes()
        assert "node1" in entry_nodes, "node1 should be an entry node"
        assert "node2" in exit_nodes, "node2 should be an exit node"
        print("✅ Entry/exit node detection works correctly")

        # Test updating the workflow
        workflow_def.name = "Updated Workflow Definition"
        assert workflow_def.name == "Updated Workflow Definition", "Update should work"
        print("✅ WorkflowDef updates work correctly")

        print("✅ All WorkflowDef CRUD operations work correctly")

    except Exception as e:
        print(f"❌ Failed WorkflowDef CRUD test: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_tool_registry_operations():
    """Test operations with the tool registry."""
    print("\nTesting tool registry operations...")

    try:
        # Test listing tools
        from fichero_server.workflows.registry import list_tools, get_tool_def, list_tools_by_category

        tools = list_tools()
        assert len(tools) > 0, "Should have at least one tool"
        print(f"✅ Found {len(tools)} tools in registry")

        # Test getting a specific tool
        transcribe_tool = get_tool_def("transcribe")
        assert transcribe_tool is not None, "Transcribe tool should exist"
        assert transcribe_tool.name == "transcribe", "Tool name should match"
        print("✅ Getting specific tool works correctly")

        # Test listing by category
        vision_tools = list_tools_by_category("vision")
        assert len(vision_tools) > 0, "Should have vision tools"
        for tool in vision_tools:
            assert tool.category == "vision", f"Tool {tool.name} should be in vision category"
        print(f"✅ Found {len(vision_tools)} vision tools")

        # Test tool properties
        for tool in tools[:3]:  # Test first 3 tools
            assert hasattr(tool, 'name'), "Tool should have name"
            assert hasattr(tool, 'display_name'), "Tool should have display name"
            assert hasattr(tool, 'category'), "Tool should have category"
            print(f"✅ Tool {tool.name} has all required properties")

        print("✅ All tool registry operations work correctly")

    except Exception as e:
        print(f"❌ Failed tool registry test: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_workflow_conversion():
    """Test conversion between database format and LangGraph format."""
    print("\nTesting workflow conversion...")

    try:
        from fichero_server.api.routes.workflows import _dict_to_node_def, _dict_to_edge_def

        # Create a test workflow in database format
        db_workflow = Workflow(
            id="test-convert-workflow",
            name="Conversion Test Workflow",
            description="Testing conversion functionality",
            format="nodes",
            provider="openai",
            model="gpt-4o",
            nodes=[
                {
                    "id": "transcribe_node",
                    "tool": "transcribe",
                    "label": "Transcribe Audio",
                    "position_x": 100,
                    "position_y": 200,
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "file"}
                    ],
                    "output_ports": [
                        {"id": "text", "name": "text", "port_type": "output", "data_type": "text"}
                    ]
                },
                {
                    "id": "summarize_node",
                    "tool": "summarize",
                    "label": "Summarize Text",
                    "position_x": 300,
                    "position_y": 200,
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "text"}
                    ],
                    "output_ports": [
                        {"id": "summary", "name": "summary", "port_type": "output", "data_type": "text"}
                    ]
                }
            ],
            edges=[
                {
                    "source": "transcribe_node",
                    "target": "summarize_node",
                    "source_port": "text",
                    "target_port": "input"
                }
            ]
        )

        # Test conversion helpers used by workflow routes
        converted_nodes = [_dict_to_node_def(node_dict, enrich_ports=False) for node_dict in db_workflow.nodes]
        converted_edges = [_dict_to_edge_def(edge_dict) for edge_dict in db_workflow.edges]

        assert len(converted_nodes) == 2, "Should convert 2 nodes"
        assert len(converted_edges) == 1, "Should convert 1 edge"
        print("✅ Workflow route conversion helpers run correctly")

        # Verify node conversion
        transcribe_node = next((n for n in converted_nodes if n.id == "transcribe_node"), None)
        assert transcribe_node is not None, "Transcribe node should exist"
        assert transcribe_node.tool == "transcribe", "Node tool should be preserved"
        print("✅ Node conversion works correctly")

        # Verify edge conversion
        edge = converted_edges[0]
        assert edge.source == "transcribe_node", "Edge source should match"
        assert edge.target == "summarize_node", "Edge target should match"
        print("✅ Edge conversion works correctly")

        print("✅ All workflow conversion operations work correctly")

    except Exception as e:
        print(f"❌ Failed workflow conversion test: {e}")
        import traceback
        traceback.print_exc()
        raise


def main():
    """Run all CRUD tests."""
    print("🚀 Starting Workflow CRUD Operations Tests")
    print("=" * 50)

    tests = [
        ("Workflow Model CRUD", test_workflow_model_crud),
        ("WorkflowDef CRUD", test_workflow_types_crud),
        ("Tool Registry Operations", test_tool_registry_operations),
        ("Workflow Conversion", test_workflow_conversion),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n🧪 Running {test_name}...")
        print("-" * 30)

        if test_func():
            passed += 1
            print(f"✅ {test_name} PASSED")
        else:
            print(f"❌ {test_name} FAILED")

    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All CRUD tests PASSED! Workflow operations are working correctly.")
        return 0
    else:
        print(f"💥 {total - passed} tests failed.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
