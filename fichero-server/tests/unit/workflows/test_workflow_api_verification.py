#!/usr/bin/env python3
"""
Simple tests for workflow API endpoints without requiring full backend.
"""
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

def test_workflow_api_imports():
    """Test that we can import the workflow API module without errors."""
    print("Testing workflow API imports...")

    try:
        # Test importing the workflows routes module
        from fichero_server.api.routes.workflow import workflows
        print("✅ Successfully imported workflows routes")

        # Check that the router is available
        assert hasattr(workflows, 'router'), "Router should be available"
        print("✅ Router is available")

        # Check that key functions exist
        expected_functions = [
            'list_workflows', 'get_workflow', 'create_workflow',
            'update_workflow', 'delete_workflow', 'import_workflow',
            'export_workflow'
        ]

        for func_name in expected_functions:
            assert hasattr(workflows, func_name), f"Function {func_name} should be available"
            print(f"✅ Function {func_name} is available")

        print("✅ All expected API functions are available")

    except Exception as e:
        print(f"❌ Failed to import workflow API: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_workflow_types():
    """Test that workflow types are properly defined."""
    print("\nTesting workflow types...")

    try:
        from fichero_server.workflows.types import WorkflowDef, NodeDef, EdgeDef

        # Test creating basic workflow components
        node = NodeDef(id="test-node", tool="transcribe")
        assert node.id == "test-node"
        assert node.tool == "transcribe"
        print("✅ NodeDef works correctly")

        edge = EdgeDef(source="node1", target="node2")
        assert edge.source == "node1"
        assert edge.target == "node2"
        print("✅ EdgeDef works correctly")

        workflow = WorkflowDef(
            id="test-workflow",
            name="Test Workflow",
            nodes=[node],
            edges=[edge]
        )
        assert workflow.id == "test-workflow"
        assert len(workflow.nodes) == 1
        assert len(workflow.edges) == 1
        print("✅ WorkflowDef works correctly")

        print("✅ All workflow types work correctly")

    except Exception as e:
        print(f"❌ Failed workflow types test: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_workflow_registry():
    """Test that workflow registry functions exist."""
    print("\nTesting workflow registry...")

    try:
        from fichero_server.workflows.registry import list_tools

        # Test that we can list tools
        tools = list_tools()
        assert len(tools) > 0, "Should have at least one tool"
        print(f"✅ Found {len(tools)} tools in registry")

        # Check for important tools
        tool_names = [t.name for t in tools]
        expected_tools = ["transcribe"]
        for tool in expected_tools:
            assert tool in tool_names, f"Expected tool '{tool}' not found"
            print(f"✅ Tool '{tool}' is available")

        print("✅ Workflow registry works correctly")

    except Exception as e:
        print(f"❌ Failed workflow registry test: {e}")
        import traceback
        traceback.print_exc()
        raise


def main():
    """Run all tests."""
    print("🚀 Starting Workflow API Verification Tests")
    print("=" * 50)

    tests = [
        ("API Imports", test_workflow_api_imports),
        ("Workflow Types", test_workflow_types),
        ("Workflow Registry", test_workflow_registry),
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
        print("🎉 All tests PASSED! Workflow API is properly implemented.")
        return 0
    else:
        print(f"💥 {total - passed} tests failed.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
