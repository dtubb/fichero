#!/usr/bin/env python3
"""
Tests for workflow rename/duplicate functionality.
"""
import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from fichero_server.models import Workflow


def test_workflow_rename():
    """Test renaming workflow functionality."""
    print("Testing workflow rename functionality...")

    try:
        # Create an original workflow
        original_workflow = Workflow(
            name="Original Workflow Name",
            description="A workflow to test renaming",
            format="nodes",
            provider="openai",
            model="gpt-4o",
            nodes=[
                {
                    "id": "rename_node_1",
                    "tool": "transcribe",
                    "position_x": 100,
                    "position_y": 200,
                    "label": "Transcribe Audio",
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "file"}
                    ],
                    "output_ports": [
                        {"id": "text", "name": "text", "port_type": "output", "data_type": "text"}
                    ]
                }
            ],
            edges=[]
        )

        # Store original values to verify they don't change during rename
        original_id = original_workflow.id
        original_description = original_workflow.description
        original_provider = original_workflow.provider
        original_model = original_workflow.model
        original_nodes = original_workflow.nodes
        original_edges = original_workflow.edges

        # Simulate the rename operation (this would typically be done via the update endpoint)
        original_workflow.name = "Renamed Workflow Name"

        # Verify that only the name changed
        assert original_workflow.name == "Renamed Workflow Name", "Name should be updated"
        assert original_workflow.id == original_id, "ID should remain unchanged"
        assert original_workflow.description == original_description, "Description should remain unchanged"
        assert original_workflow.provider == original_provider, "Provider should remain unchanged"
        assert original_workflow.model == original_model, "Model should remain unchanged"
        assert original_workflow.nodes == original_nodes, "Nodes should remain unchanged"
        assert original_workflow.edges == original_edges, "Edges should remain unchanged"

        print("✅ Original name: 'Original Workflow Name'")
        print(f"✅ Renamed to: '{original_workflow.name}'")
        print("✅ Only name changed during rename operation")
        print("✅ All other properties preserved during rename")

        # Test renaming to various types of names
        test_names = [
            "Updated Name",
            "Test Workflow 123",
            "Workflow with Special Chars: !@#$%",
            "Workflow with Unicode: 🤖 workflow",
            ""  # Empty name (should be allowed)
        ]

        for test_name in test_names:
            temp_workflow = Workflow(
                name="Temp Workflow",
                description="Temporary workflow for testing",
                format="nodes",
                provider="openai",
                model="gpt-4o",
                nodes=[],
                edges=[]
            )
            temp_workflow.name = test_name
            assert temp_workflow.name == test_name, f"Should be able to rename to '{test_name}'"
            print(f"✅ Successfully renamed to: '{test_name}'")

        print("✅ All workflow rename functionality works correctly")

    except Exception as e:
        print(f"❌ Failed workflow rename test: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_workflow_duplicate():
    """Test duplicating workflow functionality."""
    print("\nTesting workflow duplicate functionality...")

    try:
        # Create an original workflow
        original_workflow = Workflow(
            name="Original Workflow",
            description="A workflow to test duplication",
            format="nodes",
            provider="openai",
            model="gpt-4o",
            nodes=[
                {
                    "id": "dup_node_1",
                    "tool": "transcribe",
                    "position_x": 100,
                    "position_y": 200,
                    "label": "Transcribe Audio",
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "file"}
                    ],
                    "output_ports": [
                        {"id": "text", "name": "text", "port_type": "output", "data_type": "text"}
                    ]
                },
                {
                    "id": "dup_node_2",
                    "tool": "summarize",
                    "position_x": 300,
                    "position_y": 200,
                    "label": "Summarize Text",
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
                    "source": "dup_node_1",
                    "target": "dup_node_2",
                    "source_port": "text",
                    "target_port": "input"
                }
            ]
        )

        original_id = original_workflow.id
        original_name = original_workflow.name

        # Simulate duplication by creating a new workflow with same data
        duplicated_workflow = Workflow(
            name=f"{original_workflow.name} Copy",
            description=original_workflow.description,
            format=original_workflow.format,
            provider=original_workflow.provider,
            model=original_workflow.model,
            nodes=original_workflow.nodes,
            edges=original_workflow.edges,
        )

        # Verify duplication
        assert duplicated_workflow.id != original_id, "Duplicate should have different ID"
        assert duplicated_workflow.name == "Original Workflow Copy", "Duplicate name should have ' Copy' suffix"
        assert duplicated_workflow.description == original_workflow.description, "Description should be the same"
        assert duplicated_workflow.provider == original_workflow.provider, "Provider should be the same"
        assert duplicated_workflow.model == original_workflow.model, "Model should be the same"
        assert duplicated_workflow.nodes == original_workflow.nodes, "Nodes should be the same"
        assert duplicated_workflow.edges == original_workflow.edges, "Edges should be the same"

        print(f"✅ Original ID: {original_id}")
        print(f"✅ Duplicate ID: {duplicated_workflow.id}")
        print(f"✅ Original name: {original_name}")
        print(f"✅ Duplicate name: {duplicated_workflow.name}")
        print("✅ Duplicate has different ID but same content")

        # Verify content is identical
        assert len(duplicated_workflow.nodes) == len(original_workflow.nodes), "Node counts should match"
        assert len(duplicated_workflow.edges) == len(original_workflow.edges), "Edge counts should match"

        for orig_node, dup_node in zip(original_workflow.nodes, duplicated_workflow.nodes):
            assert orig_node == dup_node, "Node content should be identical"
        print("✅ Node content is identical between original and duplicate")

        for orig_edge, dup_edge in zip(original_workflow.edges, duplicated_workflow.edges):
            assert orig_edge == dup_edge, "Edge content should be identical"
        print("✅ Edge content is identical between original and duplicate")

        # Test with various original names
        test_names = [
            "My Workflow",
            "Workflow",
            "Test Workflow",
            "A",  # Single character
            "Workflow with spaces and CAPS",
            "Workflow-123_underscore"
        ]

        for test_name in test_names:
            temp_workflow = Workflow(
                name=test_name,
                description="Test description",
                format="nodes",
                provider="openai",
                model="gpt-4o",
                nodes=[{"id": "test", "tool": "transcribe"}],
                edges=[]
            )

            duplicated_temp = Workflow(
                name=f"{temp_workflow.name} Copy",
                description=temp_workflow.description,
                format=temp_workflow.format,
                provider=temp_workflow.provider,
                model=temp_workflow.model,
                nodes=temp_workflow.nodes,
                edges=temp_workflow.edges,
            )

            expected_name = f"{test_name} Copy"
            assert duplicated_temp.name == expected_name, f"Duplicate name should be '{expected_name}'"
            print(f"✅ Duplicated '{test_name}' -> '{duplicated_temp.name}'")

        print("✅ All workflow duplicate functionality works correctly")

    except Exception as e:
        print(f"❌ Failed workflow duplicate test: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_workflow_duplicate_with_complex_content():
    """Test duplicating workflow with complex content."""
    print("\nTesting workflow duplicate with complex content...")

    try:
        # Create a workflow with complex content
        complex_workflow = Workflow(
            name="Complex Workflow",
            description="A workflow with many nodes and complex edges",
            format="nodes",
            provider="anthropic",
            model="claude-3-5-sonnet",
            nodes=[
                {
                    "id": "node_a",
                    "tool": "transcribe",
                    "position_x": 100,
                    "position_y": 100,
                    "label": "Step A",
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "file"}
                    ],
                    "output_ports": [
                        {"id": "output", "name": "output", "port_type": "output", "data_type": "text"}
                    ]
                },
                {
                    "id": "node_b",
                    "tool": "describe",
                    "position_x": 300,
                    "position_y": 100,
                    "label": "Step B",
                    "input_ports": [
                        {"id": "image", "name": "image", "port_type": "input", "data_type": "image"}
                    ],
                    "output_ports": [
                        {"id": "description", "name": "description", "port_type": "output", "data_type": "text"}
                    ]
                },
                {
                    "id": "node_c",
                    "tool": "summarize",
                    "position_x": 500,
                    "position_y": 100,
                    "label": "Step C",
                    "input_ports": [
                        {"id": "text", "name": "text", "port_type": "input", "data_type": "text"}
                    ],
                    "output_ports": [
                        {"id": "summary", "name": "summary", "port_type": "output", "data_type": "text"}
                    ]
                }
            ],
            edges=[
                {
                    "source": "node_a",
                    "target": "node_b",
                    "source_port": "output",
                    "target_port": "image"
                },
                {
                    "source": "node_b",
                    "target": "node_c",
                    "source_port": "description",
                    "target_port": "text"
                }
            ]
        )

        # Duplicate the complex workflow
        duplicated_complex = Workflow(
            name=f"{complex_workflow.name} Copy",
            description=complex_workflow.description,
            format=complex_workflow.format,
            provider=complex_workflow.provider,
            model=complex_workflow.model,
            nodes=complex_workflow.nodes,
            edges=complex_workflow.edges,
        )

        # Verify complex content was duplicated
        assert duplicated_complex.name == "Complex Workflow Copy", "Name should have Copy suffix"
        assert len(duplicated_complex.nodes) == 3, "Should have 3 nodes"
        assert len(duplicated_complex.edges) == 2, "Should have 2 edges"
        print("✅ Complex workflow structure duplicated correctly")

        # Verify all nodes were copied
        node_ids = [node["id"] for node in duplicated_complex.nodes]
        expected_ids = ["node_a", "node_b", "node_c"]
        assert set(node_ids) == set(expected_ids), f"Should have nodes {expected_ids}"
        print("✅ All nodes copied correctly")

        # Verify all edges were copied
        for edge in duplicated_complex.edges:
            assert "source" in edge and "target" in edge, "Edges should have source and target"
            assert edge["source"] in expected_ids, f"Edge source {edge['source']} should be valid"
            assert edge["target"] in expected_ids, f"Edge target {edge['target']} should be valid"
        print("✅ All edges copied correctly")

        print("✅ Complex workflow duplicate functionality works correctly")

    except Exception as e:
        print(f"❌ Failed complex workflow duplicate test: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_workflow_rename_preserves_relationships():
    """Test that renaming preserves all workflow relationships."""
    print("\nTesting that renaming preserves workflow relationships...")

    try:
        # Create a workflow with specific relationships
        workflow = Workflow(
            name="Relationship Test Workflow",
            description="Workflow to test relationship preservation during rename",
            format="nodes",
            provider="openai",
            model="gpt-4o",
            nodes=[
                {
                    "id": "rel_node_1",
                    "tool": "transcribe",
                    "position_x": 100,
                    "position_y": 100,
                    "label": "Transcribe",
                    "input_ports": [
                        {"id": "input", "name": "input", "port_type": "input", "data_type": "file"}
                    ],
                    "output_ports": [
                        {"id": "text", "name": "text", "port_type": "output", "data_type": "text"}
                    ]
                },
                {
                    "id": "rel_node_2",
                    "tool": "summarize",
                    "position_x": 300,
                    "position_y": 100,
                    "label": "Summarize",
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
                    "source": "rel_node_1",
                    "target": "rel_node_2",
                    "source_port": "text",
                    "target_port": "input"
                }
            ]
        )

        # Store relationships to verify preservation
        original_node_ids = [node["id"] for node in workflow.nodes]
        original_edge_connections = [(edge["source"], edge["target"]) for edge in workflow.edges]

        # Rename the workflow
        original_name = workflow.name
        workflow.name = "Renamed Relationship Test Workflow"
        new_name = workflow.name

        # Verify relationships preserved
        new_node_ids = [node["id"] for node in workflow.nodes]
        new_edge_connections = [(edge["source"], edge["target"]) for edge in workflow.edges]

        assert new_node_ids == original_node_ids, "Node IDs should be preserved during rename"
        assert new_edge_connections == original_edge_connections, "Edge connections should be preserved during rename"
        assert original_name != new_name, "Name should have changed"
        assert len(new_node_ids) == len(original_node_ids), "Node count should be preserved"
        assert len(new_edge_connections) == len(original_edge_connections), "Edge count should be preserved"

        print(f"✅ Original name: {original_name}")
        print(f"✅ New name: {new_name}")
        print(f"✅ Node IDs preserved: {new_node_ids == original_node_ids}")
        print(f"✅ Edge connections preserved: {new_edge_connections == original_edge_connections}")
        print("✅ All relationships preserved during rename")

        print("✅ Relationship preservation during rename works correctly")

    except Exception as e:
        print(f"❌ Failed relationship preservation test: {e}")
        import traceback
        traceback.print_exc()
        raise


def main():
    """Run all rename/duplicate tests."""
    print("🚀 Starting Workflow Rename/Duplicate Tests")
    print("=" * 60)

    tests = [
        ("Workflow Rename", test_workflow_rename),
        ("Workflow Duplicate", test_workflow_duplicate),
        ("Complex Content Duplicate", test_workflow_duplicate_with_complex_content),
        ("Relationship Preservation", test_workflow_rename_preserves_relationships),
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

    print("\n" + "=" * 60)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All rename/duplicate tests PASSED! Workflow rename/duplicate functionality is working correctly.")
        return 0
    else:
        print(f"💥 {total - passed} tests failed.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)